"""Carry your own eval cases (evals/own.jsonl) from another branch into the current one.

    uv run python scripts/carry_own_cases.py lesson-04

Safer than `git checkout lesson-04 -- evals/own.jsonl`: it never overwrites. Rows from the
other branch are appended only if their id is not here yet; nothing else in the repo changes.
If that branch has no evals/own.jsonl (no own cases yet), it says so and does nothing.
The file is written as UTF-8 even if the old one was saved as UTF-16 by PowerShell 5.1 `>>`.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OWN = "evals/own.jsonl"


def decode(data: bytes) -> str:
    """UTF-8 (with or without BOM), UTF-16 with a BOM, or UTF-8 with lines appended in UTF-16
    by `>>` in Windows PowerShell 5.1: everything Windows editors and shells write by accident."""
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16")
    if b"\x00" not in data:                 # UTF-16 always has zero bytes here; UTF-8 JSON never does
        return data.decode("utf-8-sig")
    bom = data.find(b"\xff\xfe")
    start = bom if bom >= 0 else data.find(b"{\x00")
    if start < 0:
        raise UnicodeDecodeError("utf-8", data, 0, 1, "neither UTF-8 nor UTF-16")
    head = data[:start].decode("utf-8-sig")
    return head + ("" if not head or head.endswith("\n") else "\n") + data[start:].decode("utf-16-le").lstrip("\ufeff")


def parse(text: str, where: str) -> list[dict]:
    rows = []
    for n, line in enumerate(text.splitlines(), 1):
        line = line.strip().lstrip("\ufeff")
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ValueError(f"{where}, рядок {n}: це не JSON ({exc.msg})") from exc
    return rows


def merge(current: list[dict], incoming: list[dict]) -> tuple[list[dict], int, int]:
    """-> (rows to append, how many were added, how many were already here)."""
    have = {r.get("id") for r in current}
    new = [r for r in incoming if r.get("id") not in have]
    return new, len(new), len(incoming) - len(new)


def from_branch(branch: str) -> bytes | None:
    """The file's bytes on `branch`, or None if the branch or the file does not exist."""
    try:
        proc = subprocess.run(["git", "show", f"{branch}:{OWN}"], cwd=ROOT, capture_output=True)
    except OSError:                       # no git in PATH: scripts/doctor.py says how to install it
        return None
    return proc.stdout if proc.returncode == 0 else None


def main(argv: list[str]) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    if len(argv) != 1 or argv[0].startswith("-"):
        print("Як запускати: uv run python scripts/carry_own_cases.py <гілка>, наприклад lesson-04")
        return 2
    branch = argv[0]
    data = from_branch(branch)
    if data is None:
        print(f"У гілці {branch} нема {OWN} (або нема такої гілки). Своїх кейсів там ще нема, нічого не копіюю.")
        return 0
    try:
        incoming = parse(decode(data), f"{branch}:{OWN}")
        path = ROOT / OWN
        current = parse(decode(path.read_bytes()), OWN) if path.is_file() else []
    except (UnicodeDecodeError, ValueError) as exc:
        print(f"Не вдалося прочитати кейси: {exc}. Нічого не змінено.")
        return 1
    new, added, skipped = merge(current, incoming)
    if new:
        path.parent.mkdir(parents=True, exist_ok=True)
        rows = current + new
        path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
                        encoding="utf-8", newline="\n")
    print(f"{OWN}: додано {added}, уже були {skipped}, разом {len(current) + added}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
