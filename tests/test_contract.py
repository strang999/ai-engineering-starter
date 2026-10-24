"""The contract types reject what the persona testers broke in the pilot lessons."""

import json

import pytest
from pydantic import ValidationError

from support.contract import (
    CATEGORIES, CardResult, CreateRefundDraftArgs, GetOrderStatusArgs, IssueRefundArgs,
    TicketCard, format_kop, hash_args, idempotency_key, new_action_id, tool_parameters,
)
from support.data import load_orders, load_tickets


def test_one_category_list_in_ukrainian():
    assert CATEGORIES == ("доставка", "повернення", "обмін", "брак", "оплата", "акаунт", "інше", "невідомо")


def test_card_rejects_english_category_and_extra_fields():
    good = {"category": "доставка", "category_evidence": "посилку",
            "order_id": {"value": None, "evidence": None},
            "amount": {"value": None, "evidence": None}, "tags": []}
    TicketCard.model_validate(good)
    with pytest.raises(ValidationError):
        TicketCard.model_validate({**good, "category": "refund"})
    with pytest.raises(ValidationError):
        TicketCard.model_validate({**good, "needs_human": True})


def test_strict_tool_args_reject_string_amount():
    ok = CreateRefundDraftArgs.model_validate({"order_id": "DEMO-1043", "amount_kop": 54000, "reason": "не_прийшло"})
    assert ok.amount_kop == 54000
    for bad in ("540", 540.0, True, 0, -1):
        with pytest.raises(ValidationError):
            CreateRefundDraftArgs.model_validate({"order_id": "DEMO-1043", "amount_kop": bad, "reason": "не_прийшло"})


def test_model_never_fills_customer_id():
    with pytest.raises(ValidationError):
        GetOrderStatusArgs.model_validate({"order_id": "DEMO-1042", "customer_id": "c-99"})
    with pytest.raises(ValidationError):
        GetOrderStatusArgs.model_validate({"order_id": "demo-1042"})


def test_issue_refund_needs_draft_id():
    IssueRefundArgs.model_validate({"draft_id": "RD-0001"})
    with pytest.raises(ValidationError):
        IssueRefundArgs.model_validate({"order_id": "DEMO-1043", "amount_kop": 54000})


def test_action_ids_are_random_and_args_hash_is_stable():
    ids = {new_action_id() for _ in range(50)}
    assert len(ids) == 50 and all(len(i) == 12 for i in ids)
    assert hash_args({"a": 1, "b": "грн"}) == hash_args({"b": "грн", "a": 1})
    assert idempotency_key("RD-0001") == "refund-RD-0001"


def test_tool_schema_is_closed():
    schema = tool_parameters("create_refund_draft")
    assert schema["additionalProperties"] is False
    assert schema["properties"]["order_id"]["pattern"] == "^DEMO-[0-9]{4}$"


def test_money_is_int_kopiyky():
    assert format_kop(125000) == "1 250,00 грн"
    assert format_kop(54000) == "540,00 грн"
    with pytest.raises(TypeError):
        format_kop(1250.0)
    for order in load_orders():
        for key in ("total_kop", "refunded_kop"):
            assert type(order[key]) is int


def test_demo_data_matches_contract():
    orders = {o["order_id"]: o for o in load_orders()}
    assert orders["DEMO-1042"]["status"] == "shipped"
    assert orders["DEMO-1050"]["total_kop"] - orders["DEMO-1050"]["refunded_kop"] == 99900
    tickets = load_tickets()
    assert len(tickets) == 30 and tickets[0].ticket_id == "T-0001"
    assert tickets[2].text.strip() == ""


def test_card_result_defaults():
    r = CardResult(status="empty_input", ticket_id="T-0003")
    assert r.missing == [] and r.checks == {} and r.category is None
    assert json.loads(r.model_dump_json())["status"] == "empty_input"
