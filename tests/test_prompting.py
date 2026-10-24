"""Lesson 9: prompting techniques (zero / one / few / reason), the examples file, voting."""

import json

import pytest

from support.card import EXAMPLES_PATH, build_card_prompt, load_examples, make_card
from support.config import ROOT
from support.contract import WHY_MAX, Ticket, TicketCard, TicketCardReasoned
from support.evals import evaluate, example_leaks, load_cases, select, vote
from support.evals.__main__ import main as evals_main
from support.llm import collect_calls
from support.llm._common import json_schema
from support.llm.mock import parse_examples

EXAMPLE_FILES = sorted((ROOT / "evals").glob("examples*.jsonl"))


def ticket(text: str, tid: str = "T-9001") -> Ticket:
    return Ticket(ticket_id=tid, customer_id="c-17", text=text, created_at="2026-10-24T12:00:00+03:00")


# --- the examples are labelled demo tickets, never test cases --------------------------

def test_examples_files_are_valid_and_never_a_test_case():
    assert EXAMPLES_PATH in EXAMPLE_FILES
    cases = load_cases()
    for path in EXAMPLE_FILES:
        rows = load_examples(path)
        assert len(rows) >= 3, path.name
        assert len({r["id"] for r in rows}) == len(rows), path.name
        assert example_leaks(rows, cases) == [], f"{path.name}: an example is a copy of a case"


def test_leak_check_ignores_case_spaces_punctuation_and_apostrophes():
    copied = [{"id": "x1", "text": "  дуже дякую,   все чудово! "},
              {"id": "x2", "text": "Кур'єр нахамив, більше у вас не замовлю"},
              {"id": "x3", "text": "Дякую, що швидко відповіли"}]
    assert example_leaks(copied, load_cases()) == [("x1", "c011"), ("x2", "c021")]


def test_bad_example_row_is_a_readable_error(tmp_path):
    bad = tmp_path / "examples.jsonl"
    bad.write_text('{"id": "e1", "text": "Привіт", "card": {"category": "refund"}}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="рядок 1"):
        load_examples(bad)


# --- the prompt: zero is today's prompt, examples sit right before the ticket ----------

@pytest.mark.parametrize("variant", ["A", "B"])
def test_zero_is_the_default_prompt(variant):
    t = ticket("Де моя посилка?")
    zero = build_card_prompt(t, variant, "zero")
    assert zero == build_card_prompt(t, variant)
    assert "<example" not in zero[0]["content"] and "- why:" not in zero[0]["content"]


@pytest.mark.parametrize("prompt, n", [("one", 1), ("few", 3)])
def test_examples_go_right_before_the_ticket(prompt, n):
    content = build_card_prompt(ticket("Де моя посилка?"), "B", prompt)[0]["content"]
    assert content.count("<example>") == n
    assert content.index("</examples>") < content.index('<ticket id="T-9001">')
    assert content.index("</fields>") < content.index("<examples>")
    rows = load_examples()[:n]
    assert [e["category"] for e in parse_examples(content)] == [r["card"]["category"] for r in rows]


def test_reason_asks_for_a_short_why_first_and_code_drops_it():
    content = build_card_prompt(ticket("x"), "A", "reason")[0]["content"]
    assert content.index("- why:") < content.index("- category:")
    assert json_schema(TicketCardReasoned)["required"][0] == "why"
    with collect_calls() as calls:
        r = make_card(ticket("Курʼєр нахамив, більше у вас не замовлю", "T-0021"), prompt="reason")
    raw = json.loads(calls[0].text)
    assert list(raw)[0] == "why" and raw["why"]                  # the model wrote it first
    assert type(r.card) is TicketCard                            # ...and code dropped it
    assert '"why"' not in json.dumps(r.model_dump(), ensure_ascii=False)
    assert r.category == "доставка"                              # mock rule 3: «кур'єр» → доставка


def test_reason_never_asks_for_reasoning():
    """Anthropic: a `reasoning` / `thinking` field in JSON output is a common cause of the billed
    `reasoning_extraction` refusal; a short explanation is allowed. Nothing sent may ask for one."""
    content = build_card_prompt(ticket("x"), "A", "reason")[0]["content"].lower()
    sent = json.dumps(json_schema(TicketCardReasoned), ensure_ascii=False).lower()
    for word in ("reasoning", "thinking", "міркуван", "крок за кроком"):
        assert word not in content and word not in sent
    assert "maxlength" not in sent                               # a 400 on Claude structured output


def test_long_why_is_cut_not_a_schema_error():
    card = {"category": "інше", "category_evidence": None, "order_id": {"value": None, "evidence": None},
            "amount": {"value": None, "evidence": None}, "tags": []}
    r = TicketCardReasoned.model_validate_json(json.dumps({"why": "а" * 500, **card}, ensure_ascii=False))
    assert len(r.why) == WHY_MAX == 300


# --- the mock reacts to the prompt (rules: support/llm/mock.py docstring) ---------------

def _passed(prompt: str, **kw) -> dict[str, bool]:
    cases = select(load_cases(), tag="demo")
    return {r.id: r.passed for r in evaluate(cases, engine="model", prompt=prompt, **kw)}


def test_zero_one_few_reason_ladder_on_the_demo_cases():
    got = {p: _passed(p) for p in ("zero", "one", "few", "reason")}
    assert {p: sum(v.values()) for p, v in got.items()} == {"zero": 7, "one": 8, "few": 10, "reason": 8}
    assert [got["zero"][c] for c in ("c011", "c021", "c025")] == [False, False, False]
    assert [got["one"][c] for c in ("c011", "c021", "c025")] == [False, True, False]     # e01 matches «Курʼєр»


def test_order_matters_the_last_matching_example_wins():
    few = load_examples()[:3]
    as_is = _passed("few", examples=few)
    reversed_ = _passed("few", examples=few[::-1])
    assert as_is["c011"] and not reversed_["c011"]               # e03 (інше) last vs e02 (невідомо) last
    assert {k for k in as_is if as_is[k] != reversed_[k]} == {"c011"}


def test_three_examples_of_one_category_pull_ambiguous_tickets():
    biased = load_examples(ROOT / "evals" / "examples_bias.jsonl")
    cases = [c for c in select(load_cases()) if c["id"] in ("c011", "c019", "c021", "c025", "c026", "c006")]
    got = {r.id: r.got["category"] for r in evaluate(cases, engine="model", prompt="few", examples=biased)}
    assert got == {"c006": "обмін", "c011": "обмін", "c019": "обмін", "c021": "обмін", "c025": "обмін",
                   "c026": "обмін"}


def test_examples_never_touch_a_clear_answer():
    cases = select(load_cases())
    zero = {r.id: r.got.get("category") for r in evaluate(cases, engine="model")}
    for examples in (load_examples(), load_examples(ROOT / "evals" / "examples_bias.jsonl")):
        few = {r.id: r.got.get("category") for r in evaluate(cases, engine="model", prompt="few", examples=examples)}
        changed = {i for i in zero if zero[i] != few[i]}
        assert changed and all(zero[i] in ("інше", "невідомо", None) for i in changed)


# --- self-consistency: majority vote over N runs ---------------------------------------

def test_vote_majority_or_needs_review():
    a = {"status": "ok", "category": "інше", "checks": {}}
    b = {"status": "ok", "category": "невідомо", "checks": {}}
    c = {"status": "ok", "category": "доставка", "checks": {}}
    assert vote([a, b, a])["category"] == "інше"
    split = vote([a, b, c])
    assert split["status"] == "needs_review" and split["category"] is None
    assert split["checks"]["vote"].startswith("reject: голоси розійшлись")


def test_vote_runs_give_one_result_per_case():
    cases = select(load_cases(), tag="demo")
    results = evaluate(cases, engine="model", runs=3, vote_runs=True)
    assert len(results) == len(cases)
    assert all(len(r.calls) >= 3 for r in results)


# --- the CLI ---------------------------------------------------------------------------

def test_cli_prompt_flag_and_guards(capsys, tmp_path, monkeypatch):
    monkeypatch.setenv("AIEZ_RUNS_DIR", str(tmp_path))
    assert evals_main(["--prompt", "few", "--tag", "demo", "--label", "t"]) == 0
    out = capsys.readouterr().out
    assert "· prompt few (e01, e02, e03)" in out and "pass 10/10" in out
    data = json.loads(next(tmp_path.glob("*-t-*-few.json")).read_text(encoding="utf-8"))
    assert data["meta"]["prompt"] == "few" and data["meta"]["examples"] == ["e01", "e02", "e03"]
    assert evals_main(["--vote"]) == 2
    assert evals_main(["--examples", "evals/examples_bias.jsonl"]) == 2
    assert "--prompt one або few" in capsys.readouterr().out
