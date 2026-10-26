"""Mock mode: deterministic, offline, every scenario returns a status instead of raising."""

import pytest

from support.contract import TicketCard
from support.llm import call_model, strip_fences
from support.llm.mock import SCENARIOS, use_scenario

MSG = [{"role": "user", "content": '<ticket id="T-0004">Хочу повернути гроші за DEMO-1043, 540 грн</ticket>'}]


def card_call():
    return call_model(MSG, schema=TicketCard, purpose="card")


def test_ok_is_deterministic():
    a, b = card_call(), card_call()
    assert a.status == "ok" and a.parsed is not None
    assert a.text == b.text and a.latency_ms == b.latency_ms
    assert a.parsed.category == "повернення" and a.parsed.order_id.value == "DEMO-1043"
    assert a.cost_usd == 0.0 and a.simulated_cost


@pytest.mark.parametrize("scenario,status,error", [
    ("fenced_json", "ok", None),
    ("malformed_json", "ok", "schema_error"),
    ("wrong_schema", "ok", "schema_error"),
    ("refusal", "refusal", None),
    ("truncated", "truncated", None),
    ("rate_limit", "error", "rate_limit"),
    ("timeout", "error", "timeout"),
    ("spend_cap", "error", "spend_cap"),
    ("server_error", "error", "server_error"),
])
def test_scenarios_return_statuses(scenario, status, error):
    with use_scenario(scenario):
        r = card_call()
    assert r.status == status
    assert r.error == error
    if error == "schema_error":
        assert r.parsed is None


def test_one_retry_only_for_temporary_errors():
    """Lesson 6: one retry on timeout / rate_limit, none on anything else."""
    with use_scenario("rate_limit_then_ok"):
        r = card_call()
    assert r.status == "ok" and r.raw["attempts"] == 2
    with use_scenario("rate_limit"):
        r = card_call()
    assert r.error == "rate_limit" and r.raw["attempts"] == 2
    with use_scenario("spend_cap"):
        r = card_call()
    assert r.error == "spend_cap" and r.raw["attempts"] == 1


def test_invented_scenarios_keep_valid_schema():
    with use_scenario("invented_evidence"):
        r = card_call()
    assert r.parsed.order_id.evidence not in MSG[0]["content"]
    with use_scenario("invented_category"):
        r = card_call()
    assert r.parsed.category_evidence not in MSG[0]["content"]


def test_tool_scenarios():
    tools = [{"name": "get_order_status", "description": "", "parameters": {}}]
    with use_scenario("tool_call_wrong_amount"):
        r = call_model(MSG, tools=tools, purpose="agent")
    assert r.status == "tool_call" and r.tool_calls[0].args["amount_kop"] == "540"
    with use_scenario("tool_call_unoffered_tool"):
        r = call_model(MSG, tools=tools, purpose="agent")
    assert r.tool_calls[0].name == "create_refund_draft"


def test_all_scenarios_are_known_and_bad_name_raises():
    assert len(SCENARIOS) == 20
    with pytest.raises(ValueError):
        with use_scenario("nope"):
            pass


def test_strip_fences():
    assert strip_fences('```json\n{"a": 1}\n```') == '{"a": 1}'
    assert strip_fences(' {"a": 1} ') == '{"a": 1}'


def test_bad_arguments_raise():
    with pytest.raises(ValueError):
        call_model([])
    with pytest.raises(ValueError):
        call_model(MSG, effort="turbo")
