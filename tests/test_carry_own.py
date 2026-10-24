"""Course convention: own cases live in evals/own.jsonl and move between lesson branches safely."""

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("carry_own_cases", ROOT / "scripts" / "carry_own_cases.py")
carry = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(carry)


def test_own_cases_file_exists_from_l00():
    assert (ROOT / "evals" / "own.jsonl").is_file()


def test_merge_never_overwrites_and_skips_known_ids():
    current = [{"id": "own-01", "input": {"text": "мій"}}]
    incoming = [{"id": "own-01", "input": {"text": "старий"}}, {"id": "own-02", "input": {"text": "новий"}}]
    new, added, skipped = carry.merge(current, incoming)
    assert [r["id"] for r in new] == ["own-02"] and (added, skipped) == (1, 1)


def test_decode_reads_utf8_bom_utf16_and_a_powershell_append():
    row = json.dumps({"id": "own-01", "input": {"text": "Де посилка?"}}, ensure_ascii=False) + "\n"
    for data in (row.encode("utf-8"), row.encode("utf-8-sig"), row.encode("utf-16")):
        assert carry.parse(carry.decode(data), "x")[0]["input"]["text"] == "Де посилка?"
    mixed = row.encode("utf-8") + row.replace("own-01", "own-02").encode("utf-16-le")   # PowerShell 5.1 >>
    assert [r["id"] for r in carry.parse(carry.decode(mixed), "x")] == ["own-01", "own-02"]


def test_missing_branch_or_file_does_nothing(capsys):
    assert carry.main(["no-such-branch-for-this-test"]) == 0
    assert "нічого не копіюю" in capsys.readouterr().out
