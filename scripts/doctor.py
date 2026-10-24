"""Lesson 0 environment check. Run from the repo root:

    uv run python scripts/doctor.py           # all checks, including the tests
    uv run python scripts/doctor.py --save    # same, and writes doctor.txt (UTF-8) to post as proof
    uv run python scripts/doctor.py --skip-tests

Every line is OK, WARN or FAIL. Exit code 1 if anything is FAIL. WARN does not fail:
Python 3.13+ and a missing uv (the pip path) are WARN.
The tests run with PYTHONUTF8=1 set for them, whatever your terminal has.
"""

from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXES = {
    "python": "встанови Python через uv: uv python install 3.12, потім uv sync (на 3.13+ курс теж працює, еталонні прогони зроблені на 3.12)",
    "git": "Windows: winget install --id Git.Git -e, потім закрий і відкрий термінал",
    "uv": "Windows: winget install --id=astral-sh.uv -e (або офіційний PowerShell-інсталятор з docs.astral.sh/uv); "
          "на pip-шляху без uv (requirements.txt, README) цей рядок WARN, це нормально",
    "utf8": "виконай один раз: setx PYTHONUTF8 1, потім закрий і відкрий термінал",
    "root": "відкрий саме папку, де лежить AGENTS.md (після zip-архіву файли часто опиняються на рівень глибше; краще git clone)",
    "path": "клонуй у коротку папку без пробілів і кирилиці, наприклад C:\\dev\\ai-engineering-starter, і не в OneDrive",
    "tests": "прочитай перший FAILED у виводі: uv run pytest -q",
}


def setup_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        enc = (getattr(stream, "encoding", "") or "").lower().replace("-", "")
        if enc != "utf8" and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def run(cmd: list[str], **kw) -> tuple[int, str]:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=kw.pop("timeout", 30), **kw)
        return proc.returncode, (proc.stdout + proc.stderr).strip()
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 127, str(exc)


def check_python(version=None) -> tuple[str, str]:
    v = version or sys.version_info
    text = f"Python {platform.python_version()} ({sys.executable})"
    if (v.major, v.minor) == (3, 12):
        return "OK", text
    # 3.13+ works for the course code (pip path on a corporate laptop); the reference runs are on 3.12
    return ("WARN" if (v.major, v.minor) > (3, 12) else "FAIL"), text


def check_uv() -> tuple[str, str]:
    status, text = check_tool("uv")
    # pip path (corporate laptops): uv is recommended, not required to run the course
    return ("WARN", text) if status == "FAIL" else (status, text)


def check_tool(name: str) -> tuple[str, str]:
    exe = shutil.which(name)
    if not exe:
        return "FAIL", f"{name}: не знайдено в PATH"
    code, out = run([exe, "--version"])
    first = out.splitlines()[0] if out else ""
    return ("OK" if code == 0 else "FAIL"), first or f"{name}: не запускається"


def check_utf8() -> tuple[str, str]:
    env = os.environ.get("PYTHONUTF8", "")
    mode = bool(sys.flags.utf8_mode)
    text = f"PYTHONUTF8={env or '(не задано)'} · utf8_mode={mode}"
    if env == "1" and mode:
        return "OK", text
    return ("WARN" if platform.system() != "Windows" else "FAIL"), text


def check_root() -> tuple[str, str]:
    missing = [n for n in ("AGENTS.md", "pyproject.toml", "support") if not (ROOT / n).exists()]
    if missing:
        return "FAIL", f"у {ROOT} нема: {', '.join(missing)}"
    return "OK", f"корінь проєкту: {ROOT}"


def check_path() -> tuple[str, str]:
    text = str(ROOT)
    problems = []
    if " " in text:
        problems.append("пробіл")
    if not text.isascii():
        problems.append("не-ASCII символи")
    if "onedrive" in text.lower():
        problems.append("OneDrive")
    return ("WARN", f"шлях має {', '.join(problems)}: {text}") if problems else ("OK", "шлях без пробілів і кирилиці")


def check_tests() -> tuple[str, str]:
    env = {**os.environ, "PYTHONUTF8": "1", "AIEZ_PROVIDER": "mock"}
    code, out = run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"],
                    cwd=ROOT, env=env, timeout=600)
    summary = next((ln for ln in reversed(out.splitlines()) if re.search(r"\b(passed|failed|error)", ln)), out[-200:])
    summary = summary.strip("= ").strip()
    return ("OK" if code == 0 else "FAIL"), f"pytest: {summary}"


def main(argv: list[str]) -> int:
    setup_console()
    checks = [
        ("python", check_python),
        ("git", lambda: check_tool("git")),
        ("uv", check_uv),
        ("utf8", check_utf8),
        ("root", check_root),
        ("path", check_path),
    ]
    if "--skip-tests" not in argv:
        checks.append(("tests", check_tests))

    lines = [f"doctor · {platform.system()} {platform.release()} · {ROOT.name}"]
    worst = "OK"
    for key, fn in checks:
        status, text = fn()
        lines.append(f"[{status:<4}] {text}")
        if status != "OK":
            lines.append(f"       що зробити: {FIXES[key]}")
        if status == "FAIL":
            worst = "FAIL"
    lines.append("Усе гаразд." if worst == "OK" else "Є FAIL: виправ рядки вище й запусти doctor знову.")
    report = "\n".join(lines)
    print(report)
    if "--save" in argv:
        (ROOT / "doctor.txt").write_text(report + "\n", encoding="utf-8")
        print("Збережено doctor.txt")
    return 1 if worst == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
