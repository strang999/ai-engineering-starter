"""Snippet harness: «every code block runs as printed». Convention: docs/SNIPPETS.md.

    uv run python scripts/check_snippets.py "C:\\path\\to\\Lesson 05.md"   # check one lesson file
    uv run python scripts/check_snippets.py --all                         # repo docs + AIEZ_LESSONS_DIR
    uv run pytest tests/test_snippets.py -q                               # the same, as tests

A block runs when the line right before its opening fence is `<!-- run: lNN -->`
(this tag only) or `<!-- run: lNN+ -->` (this tag and every later one).
The fenced block right after it with the info string `output` is the expected stdout.
"""

from __future__ import annotations

import os
import re
import shlex
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MARKER_RE = re.compile(r"^\s*<!--\s*run:\s*l(\d{2})(\+?)\s*-->\s*$")
FENCE_RE = re.compile(r"^(\s*)(`{3,}|~{3,})\s*([\w+-]*)")
PY_LANGS = {"python", "py"}
CMD_LANGS = {"powershell", "ps1", "pwsh", "shell", "sh", "bash", "console", "text", "cmd"}


@dataclass
class Snippet:
    path: Path
    line: int            # 1-based line of the opening fence
    tag: int
    plus: bool
    lang: str
    code: str
    expected: str | None

    @property
    def id(self) -> str:
        return f"{self.path.name}:{self.line}"


def current_tag() -> int:
    text = (ROOT / "support" / "__init__.py").read_text(encoding="utf-8")
    return int(re.search(r'STARTER_TAG\s*=\s*"l(\d{2})"', text).group(1))


def _read_fence(lines: list[str], i: int) -> tuple[str, str, int] | None:
    """lines[i] opens a fence -> (lang, body, index after the closing fence)."""
    m = FENCE_RE.match(lines[i])
    if not m:
        return None
    fence, lang = m.group(2), m.group(3).lower()
    body = []
    j = i + 1
    while j < len(lines) and not lines[j].strip().startswith(fence):
        body.append(lines[j])
        j += 1
    return lang, "\n".join(body), j + 1


def extract(path: Path) -> list[Snippet]:
    lines = path.read_text(encoding="utf-8").splitlines()
    out: list[Snippet] = []
    i = 0
    while i < len(lines):
        m = MARKER_RE.match(lines[i])
        if not m:
            i += 1
            continue
        j = i + 1
        while j < len(lines) and not lines[j].strip():
            j += 1
        block = _read_fence(lines, j) if j < len(lines) else None
        if block is None:
            raise ValueError(f"{path}:{i + 1}: run marker is not followed by a fenced block")
        lang, code, k = block
        expected = None
        n = k
        while n < len(lines) and not lines[n].strip():
            n += 1
        if n < len(lines):
            nxt = _read_fence(lines, n)
            if nxt and nxt[0] == "output":
                expected, k = nxt[1], nxt[2]
        out.append(Snippet(path, j + 1, int(m.group(1)), bool(m.group(2)), lang, code, expected))
        i = k
    return out


def sources() -> list[Path]:
    files = [ROOT / "README.md", ROOT / "CONTRACT.md", *sorted((ROOT / "docs").glob("*.md"))]
    lessons = ROOT / "lessons"
    if lessons.is_dir():
        files += sorted(lessons.rglob("*.md"))
    for extra in filter(None, os.environ.get("AIEZ_LESSONS_DIR", "").split(os.pathsep)):
        p = Path(extra)
        files += sorted(p.rglob("*.md")) if p.is_dir() else [p]
    return [f for f in files if f.is_file()]


def applies(snippet: Snippet, tag: int) -> bool:
    return snippet.tag == tag or (snippet.plus and tag >= snippet.tag)


def _env() -> dict:
    env = {k: v for k, v in os.environ.items() if not k.startswith("AIEZ_")}
    env.update({"PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8", "AIEZ_PROVIDER": "mock",
                "AIEZ_NO_DOTENV": "1", "PYTHONPATH": str(ROOT)})
    return env


def _command(line: str) -> list[str]:
    line = re.sub(r"^(PS\S*>|>|\$)\s*", "", line.strip())
    parts = shlex.split(line)
    if parts[:2] == ["uv", "run"]:
        parts = parts[2:]
        if parts and parts[0] == "python":
            return [sys.executable, *parts[1:]]
        if parts and parts[0] == "pytest":
            return [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", *parts[1:]]
    raise ValueError(f"only `uv run python ...` and `uv run pytest ...` lines can be checked, got: {line}")


def run(snippet: Snippet) -> tuple[int, str]:
    env = _env()
    if snippet.lang in PY_LANGS:
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp) / "snippet.py"
            script.write_text(snippet.code + "\n", encoding="utf-8")
            proc = subprocess.run([sys.executable, str(script)], cwd=ROOT, env=env, capture_output=True,
                                  text=True, encoding="utf-8", errors="replace", timeout=120)
        return proc.returncode, proc.stdout + (proc.stderr if proc.returncode else "")
    if snippet.lang in CMD_LANGS:
        out, code = [], 0
        for line in snippet.code.splitlines():
            if not line.strip() or line.strip().startswith("#"):
                continue
            proc = subprocess.run(_command(line), cwd=ROOT, env=env, capture_output=True,
                                  text=True, encoding="utf-8", errors="replace", timeout=300)
            out.append(proc.stdout + (proc.stderr if proc.returncode else ""))
            code = code or proc.returncode
        return code, "".join(out)
    raise ValueError(f"cannot run a ```{snippet.lang} block; use python or powershell")


def _normalize(text: str) -> str:
    lines = [ln.rstrip() for ln in text.replace("\r\n", "\n").split("\n")]
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines)


def matches(expected: str, actual: str) -> bool:
    """`...` on its own line = any number of lines; `{*}` inside a line = any text."""
    parts = []
    for line in _normalize(expected).split("\n"):
        if line.strip() == "...":
            parts.append(r"(?:[^\n]*\n)*?")
        else:
            parts.append(".*".join(re.escape(p) for p in line.split("{*}")) + r"\n")
    return re.fullmatch("".join(parts), _normalize(actual) + "\n", re.S) is not None


def check(snippet: Snippet) -> str | None:
    """None if the block runs as printed, else a message."""
    try:
        code, out = run(snippet)
    except (ValueError, subprocess.TimeoutExpired) as exc:
        return str(exc)
    if snippet.expected is None:
        return None if code == 0 else f"exit code {code}\n{out}"
    if not matches(snippet.expected, out):
        return f"output differs (exit {code})\n--- expected\n{_normalize(snippet.expected)}\n--- actual\n{_normalize(out)}"
    return None


def main(argv: list[str]) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    tag = current_tag()
    paths = sources() if "--all" in argv or not argv else [Path(a) for a in argv if a != "--all"]
    failed = total = 0
    for path in paths:
        for sn in extract(path):
            if not applies(sn, tag):
                continue
            total += 1
            problem = check(sn)
            print(("PASS " if problem is None else "FAIL ") + sn.id)
            if problem:
                failed += 1
                print(problem)
    print(f"tag l{tag:02d}: {total - failed}/{total} blocks run as printed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
