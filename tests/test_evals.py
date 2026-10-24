"""run_evals: one cases.jsonl, one command, a pinned report format."""

import json
import re

from support.evals import compare, evaluate, load_cases, report, select
from support.evals.__main__ import main as evals_main


def test_cases_file_is_valid_and_has_the_lesson_1_checks():
    cases = load_cases()
    ids = [c["id"] for c in cases]
    assert ids[:3] == ["c001", "c002", "c003"]
    for c in cases:
        assert set(c) >= {"id", "added_in", "kind", "split", "tags", "input", "expect"}
        assert c["split"] in ("dev", "holdout")


def test_compare_operators():
    got = {"status": "ok", "order_id": None, "draft_reply": "Дані не завантажились"}
    assert compare({"status": "ok", "order_id": None}, got) == []
    assert compare({"status_in": ["ok", "needs_review"]}, got) == []
    assert compare({"must_contain": "не завантажились"}, got) == []
    assert compare({"must_not_contain": ["замовлень немає"]}, got) == []
    assert compare({"order_id": "DEMO-1042"}, got) == ["order_id: expected DEMO-1042, got null"]


def test_baseline_passes_the_three_lesson_1_checks():
    cases = [c for c in select(load_cases()) if c["added_in"] == 1]
    results = evaluate(cases, engine="baseline")
    assert [r.passed for r in results] == [True, True, True]


def test_report_format_is_pinned():
    results = evaluate(select(load_cases())[:3], engine="baseline")
    lines = report(results, run_id="20261102-1012", kind="card", provider="baseline", model="rules",
                   split="dev", simulated=False, measured=False)
    assert lines[0] == "run 20261102-1012 · kind=card · provider=baseline model=rules · cases 3 (dev)"
    assert re.fullmatch(r"pass \d+/\d+ \(\d+\.\d%\) · (coverage \d+/\d+ · precision \d+/\d+|coverage n/a · precision n/a)", lines[1])
    assert re.fullmatch(r"cost \$\d+\.\d{4}( \(\w+\))? · per case \$\d+\.\d{4} · per success \$\d+\.\d{4}", lines[2])
    assert lines[3].startswith("latency ")


def test_cli_writes_a_run_file(capsys, tmp_path, monkeypatch):
    monkeypatch.setenv("AIEZ_RUNS_DIR", str(tmp_path))
    assert evals_main(["--baseline", "--label", "t"]) == 0
    out = capsys.readouterr().out
    assert "provider=baseline model=rules" in out
    files = list(tmp_path.glob("*-t.json"))
    assert len(files) == 1
    data = json.loads(files[0].read_text(encoding="utf-8"))
    assert data["meta"]["provider"] == "baseline" and data["cases"]


# --- lesson 7: the model path, several configs, a budget first ---------------------

from support import config  # noqa: E402
from support.evals import comparison, dry_run, summary  # noqa: E402
from support.evals.__main__ import parse_configs  # noqa: E402
from support.llm import collect_calls  # noqa: E402


def test_model_run_in_mock_is_deterministic():
    cases = select(load_cases())
    a = summary(evaluate(cases, engine="model"))
    b = summary(evaluate(cases, engine="model"))
    assert a == b
    assert a["cost_usd"] == 0.0 and a["p50"] > 0 and a["tokens"]["in"] > 0


def test_runs_repeat_every_case():
    cases = select(load_cases())[:3]
    assert len(evaluate(cases, engine="model", runs=2)) == 6


def test_dry_run_calls_nothing(tmp_path, monkeypatch):
    monkeypatch.setenv("AIEZ_RUNS_DIR", str(tmp_path))
    with collect_calls() as calls:
        lines = dry_run(select(load_cases()), [("mock", "mock-1"), ("anthropic", "claude-haiku-5-5")], runs=2)
    assert calls == [] and not list(tmp_path.iterdir())
    assert lines[0].startswith("dry run · 30 cases × 2 runs × 2 configs")
    assert any("claude-haiku-5-5" in ln and "≈ $" in ln for ln in lines)


def test_parse_configs():
    assert parse_configs(["anthropic:claude-haiku-5-5", "mock:mock-1"], None) == [
        ("anthropic", "claude-haiku-5-5"), ("mock", "mock-1")]
    assert parse_configs([], None) == [("mock", "mock-1")]
    assert parse_configs(["gpt-6-luna"], "openai") == [("openai", "gpt-6-luna")]


def test_comparison_table_and_cli(capsys):
    rows = [("mock:mock-1", summary(evaluate(select(load_cases())[:5], engine="model")))]
    table = comparison(rows * 2)
    assert table[0].split() == ["config", "pass", "cov", "prec", "$/case", "p50", "p95"]
    assert evals_main(["--model", "mock:mock-1", "--tag", "demo"]) == 0
    out = capsys.readouterr().out
    assert "provider=mock model=mock-1 · cases 10 (dev)" in out and "(simulated)" in out


def test_dry_run_prices_each_call_not_the_sum():
    """Haiku's 100K long-prompt tier applies per request: 14 runs cost 14/13 of 13 runs, not 5x."""
    def usd(runs):
        line = next(ln for ln in dry_run(select(load_cases()), [("anthropic", "claude-haiku-5-5")], runs=runs)
                    if ln.startswith("anthropic:"))
        return float(line.split("≈ $")[1].split()[0])
    assert abs(usd(14) / usd(13) - 14 / 13) < 0.01


def test_max_usd_stops_between_cases(monkeypatch):
    import support.evals as ev
    monkeypatch.setattr(ev, "run_card_case", lambda case, engine, variant="A": ({"status": "ok"}, []))
    cases = select(load_cases())[:10]
    results = ev.evaluate(cases, engine="model", max_usd=0.0)
    assert results == []
    assert len(ev.evaluate(cases, engine="model", max_usd=None)) == 10


def test_label_with_several_models_writes_one_file_each(tmp_path, monkeypatch):
    monkeypatch.setenv("AIEZ_RUNS_DIR", str(tmp_path))
    assert evals_main(["--model", "mock:mock-1", "--model", "mock:mock-2", "--tag", "demo", "--label", "cmp"]) == 0
    names = sorted(p.name for p in tmp_path.glob("*-cmp-*.json"))
    assert len(names) == 2 and names[0].endswith("-cmp-mock-mock-1-low.json")


def test_mock_cases_run_on_mock_in_a_live_run(monkeypatch):
    for name in ("ANTHROPIC_API_KEY",):
        monkeypatch.delenv(name, raising=False)
    case = {"id": "x1", "kind": "card", "mock": "refusal", "input": {"text": "Де DEMO-1044?"}, "expect": {"status": "refusal"}}
    with config.use_model("anthropic", "claude-haiku-5-5"):
        assert evaluate([case], engine="model")[0].passed      # no key, still the mock scenario


def test_effort_override_reaches_the_call():
    with config.use_model("mock", None, "medium"):
        assert config.current_effort() == "medium"
    assert config.current_effort() == "low"


# --- course convention: own cases in evals/own.jsonl, never in the tests ----------------

import os  # noqa: E402
from pathlib import Path  # noqa: E402

from support.evals import new_run_id  # noqa: E402
from support.evals.own import load_own_cases, next_own_id  # noqa: E402

OWN_ROWS = [
    {"id": "own-01", "input": {"text": "Де моя посилка? DEMO-1042"}, "expect": {"order_id": "DEMO-1042"}},
    {"id": "own-02", "tags": ["own"], "input": {"ticket_id": "T-0901", "customer_id": "c-17", "text": "Привіт"},
     "expect": {"category": None}},
]


def write_own(rows, encoding="utf-8") -> Path:
    path = Path(os.environ["AIEZ_OWN_CASES"])
    path.write_bytes("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows).encode(encoding))
    return path


def test_own_cases_go_to_run_evals_never_to_the_tests(capsys):
    write_own(OWN_ROWS)
    assert all("own" not in c["tags"] for c in load_cases())
    own = [c for c in load_cases(own=True) if "own" in c["tags"]]
    assert [c["id"] for c in own] == ["own-01", "own-02"]
    assert own[0]["input"]["customer_id"] == "c-17" and own[0]["kind"] == "card" and own[0]["split"] == "dev"
    assert evals_main(["--baseline", "--tag", "own"]) == 0
    assert "cases 2 (dev)" in capsys.readouterr().out


def test_own_rows_left_in_cases_jsonl_are_skipped_by_tests(tmp_path):
    path = tmp_path / "cases.jsonl"
    path.write_text(json.dumps({**OWN_ROWS[1], "id": "c999"}, ensure_ascii=False) + "\n", encoding="utf-8")
    assert load_cases(path) == [] and len(load_cases(path, own=True)) == 1


def test_powershell_utf16_append_is_read_with_a_warning(capsys):
    path = write_own(OWN_ROWS[:1])
    with path.open("ab") as f:        # what `>>` in Windows PowerShell 5.1 appends: UTF-16 LE, CRLF
        f.write((json.dumps(OWN_ROWS[1], ensure_ascii=False) + "\r\n").encode("utf-16-le"))
    assert [c["id"] for c in load_own_cases()] == ["own-01", "own-02"]
    assert "UTF-16" in capsys.readouterr().err
    write_own(OWN_ROWS, encoding="utf-16")              # a whole file in UTF-16 with a BOM
    assert len(load_own_cases()) == 2


def test_unreadable_cases_file_is_a_message_not_a_traceback(capsys):
    Path(os.environ["AIEZ_OWN_CASES"]).write_bytes('{"id": "own-01", "input": {"text": "Привіт"}}'.encode("cp1251"))
    assert evals_main(["--baseline"]) == 2
    assert "Не можу прочитати кейси" in capsys.readouterr().out


def test_add_case_writes_utf8_with_the_next_id(capsys):
    assert evals_main(["add-case", "Де моя посилка? DEMO-1042", "--category", "доставка", "--order-id", "DEMO-1042"]) == 0
    assert evals_main(["add-case", "Поверніть 540 грн", "--amount-kop", "54000", "--category", "null"]) == 0
    assert evals_main(["add-case", "Привіт", "--category", "продукти"]) == 2      # not a contract category
    rows = [json.loads(line) for line in Path(os.environ["AIEZ_OWN_CASES"]).read_text(encoding="utf-8").splitlines()]
    assert [r["id"] for r in rows] == ["own-01", "own-02"] and rows[0]["tags"] == ["own"]
    assert rows[0]["expect"] == {"category": "доставка", "order_id": "DEMO-1042"}
    assert rows[1]["expect"] == {"category": None, "amount_kop": 54000}
    assert rows[0]["input"] == {"ticket_id": "T-OWN01", "customer_id": "c-17", "text": "Де моя посилка? DEMO-1042"}
    assert next_own_id(rows) == "own-03"


def test_id_filter_and_run_id_with_seconds(capsys):
    assert evals_main(["--baseline", "--id", "c001", "--id", "c003"]) == 0
    assert "cases 2 (dev)" in capsys.readouterr().out
    assert re.fullmatch(r"\d{8}-\d{6}", new_run_id())
