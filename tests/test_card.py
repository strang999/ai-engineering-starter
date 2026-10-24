"""Lesson 6: make_card asks the model; every ModelResult.status has a branch."""

import pytest

from support.card import build_card_prompt, make_card
from support.contract import Ticket
from support.llm import collect_calls
from support.llm.mock import use_scenario


def ticket(text="Хочу повернути гроші за DEMO-1043, 540 грн", tid="T-0004"):
    return Ticket(ticket_id=tid, customer_id="c-17", text=text, created_at="2026-10-24T12:00:00+03:00")


def test_prompt_lists_fields_and_marks_ticket_as_data():
    content = build_card_prompt(ticket())[0]["content"]
    for word in ("category", "category_evidence", "order_id", "amount", "tags", "невідомо", "дослівн"):
        assert word in content
    assert '<ticket id="T-0004">' in content
    with pytest.raises(ValueError):
        build_card_prompt(ticket(), variant="Z")


def test_make_card_ok():
    r = make_card(ticket())
    assert r.status == "ok" and r.category == "повернення" and r.order_id == "DEMO-1043"


def test_empty_ticket_makes_no_call():
    with collect_calls() as calls:
        r = make_card(ticket("   "))
    assert r.status == "empty_input" and calls == []


@pytest.mark.parametrize("scenario,status", [
    ("refusal", "refusal"), ("truncated", "truncated"), ("timeout", "error"),
    ("spend_cap", "error"), ("malformed_json", "schema_error"), ("wrong_schema", "schema_error"),
    ("fenced_json", "ok"),
])
def test_statuses(scenario, status):
    with use_scenario(scenario):
        assert make_card(ticket()).status == status
