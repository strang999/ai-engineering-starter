"""Lesson 5: a rules baseline with two numbers, coverage and precision, on the same cases the model gets later."""

import re

import pytest

from support.contract import CATEGORIES
from support.evals import evaluate, load_cases, select
from support.rules import triage_rules
from support.tokens import main as tokens_main


@pytest.mark.parametrize("text,expected", [
    ("Не отримав посилку, замовлення DEMO-1042", "доставка"),
    ("Хочу повернути гроші за DEMO-1043", "повернення"),
    ("Хочу повернути гроші", None),                       # no order number: abstain
    ("Не хочу повернення, обміняйте на M, DEMO-1043", "повернення"),   # the known confident error (№4)
    ("Помада прийшла зламана", "брак"),
    ("Дуже дякую, все чудово", None),
    ("   ", None),
])
def test_triage_rules(text, expected):
    assert triage_rules(text) == expected


def test_triage_returns_only_contract_categories_or_none():
    for case in select(load_cases()):
        got = triage_rules(case["input"]["text"])
        assert got is None or got in CATEGORIES


def test_seed_set_shape():
    cases = select(load_cases())
    assert len(cases) >= 30
    assert sum("edge" in c["tags"] for c in cases) >= 5
    assert {c["input"]["customer_id"] for c in cases} <= {"c-17", "c-23", "c-99"}
    for c in cases:
        assert c["expect"].get("category") is None or c["expect"]["category"] in CATEGORIES


def numbers(results):
    scored = [r for r in results if r.scored]
    decided = [r for r in scored if r.decided]
    return len(decided), len(scored), sum(r.correct for r in decided)


def test_quick_win_numbers_on_the_demo_tickets():
    results = evaluate(select(load_cases(), tag="demo"), engine="baseline")
    assert len(results) == 10
    assert numbers(results) == (4, 10, 3)        # «coverage 4/10, precision 3/4»


def test_baseline_numbers_on_the_seed_set():
    seed = [c for c in select(load_cases()) if c["added_in"] <= 5]
    assert numbers(evaluate(seed, engine="baseline")) == (18, 29, 16)


def test_tokens_cli_prints_something(capsys):
    assert tokens_main(["Хочу повернути гроші за замовлення 1042"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("Текст: Хочу повернути")
    assert re.search(r"(Токенів: \d+|оцінка токенів: \d+)", out)
