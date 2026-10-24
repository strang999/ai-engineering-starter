"""Live adapters, checked OFFLINE: request shape and response mapping with fake SDK objects.

No SDK, key or network is needed here. Whether the live APIs accept these requests is
NOT proven by these tests (docs/VERIFIED.md says what is verified and what is not).
"""

from types import SimpleNamespace as NS

import pytest

from support.contract import TicketCard
from support.llm import anthropic_, gemini_, openai_
from support.llm._common import error_code, json_schema

MSGS = [{"role": "user", "content": "Де DEMO-1042?"}]
TOOLS = [{"name": "get_order_status", "description": "Статус замовлення",
          "parameters": {"type": "object", "properties": {"order_id": {"type": "string"}},
                         "required": ["order_id"], "additionalProperties": False}}]
TOOL_TURN = MSGS + [
    {"role": "assistant", "content": "", "tool_calls": [{"id": "c1", "name": "get_order_status", "args": {"order_id": "DEMO-1042"}},
                                                         {"id": "c2", "name": "get_order_status", "args": {"order_id": "DEMO-1043"}}]},
    {"role": "tool", "tool_call_id": "c1", "name": "get_order_status", "content": "shipped", "is_error": False},
    {"role": "tool", "tool_call_id": "c2", "name": "get_order_status", "content": "delivered", "is_error": False},
]


def test_json_schema_is_closed_and_inlined():
    s = json_schema(TicketCard)
    assert "$defs" not in s and "$ref" not in str(s)
    assert s["additionalProperties"] is False
    assert s["properties"]["order_id"]["additionalProperties"] is False
    assert set(s["required"]) == {"category", "category_evidence", "order_id", "amount", "tags"}
    assert "доставка" in s["properties"]["category"]["enum"]


# --- Anthropic -------------------------------------------------------------------

def test_anthropic_request_shape():
    req = anthropic_.build_request(MSGS, system="sys", schema=TicketCard, tools=TOOLS, model="claude-haiku-5-5",
                                   effort="low", max_output_tokens=512)
    assert req["output_config"]["effort"] == "low"
    assert req["output_config"]["format"]["type"] == "json_schema"
    assert req["max_tokens"] == 512 and req["system"] == "sys"
    assert "temperature" not in req
    assert req["tools"][0]["input_schema"]["properties"]["order_id"] and req["tools"][0]["strict"] is True
    assert req["cache_control"] == {"type": "ephemeral"}     # cached tokens are measured


def test_anthropic_cache_switch_and_workspace_header(monkeypatch):
    monkeypatch.setenv("AIEZ_ANTHROPIC_CACHE", "0")
    req = anthropic_.build_request(MSGS, system=None, schema=None, tools=None, model="claude-haiku-5-5",
                                   effort="low", max_output_tokens=512)
    assert "cache_control" not in req
    monkeypatch.delenv("ANTHROPIC_WORKSPACE_ID", raising=False)
    assert anthropic_.client_headers() is None
    monkeypatch.setenv("ANTHROPIC_WORKSPACE_ID", "wrkspc_test")
    assert anthropic_.client_headers() == {"anthropic-workspace-id": "wrkspc_test"}


def test_anthropic_tool_results_go_in_one_user_message():
    out = anthropic_.convert_messages(TOOL_TURN)
    assert [m["role"] for m in out] == ["user", "assistant", "user"]
    assert [b["type"] for b in out[1]["content"]] == ["tool_use", "tool_use"]
    assert [b["tool_use_id"] for b in out[2]["content"]] == ["c1", "c2"]


def anth(stop, content=None, **usage):
    u = NS(input_tokens=usage.get("i", 10), output_tokens=usage.get("o", 5),
           cache_read_input_tokens=usage.get("c", 0), cache_creation_input_tokens=usage.get("w", 0))
    return NS(id="msg_1", stop_reason=stop, content=content or [NS(type="text", text='{"a":1}')], usage=u)


@pytest.mark.parametrize("stop,status", [
    ("end_turn", "ok"), ("tool_use", "tool_call"), ("max_tokens", "truncated"),
    ("model_context_window_exceeded", "truncated"), ("refusal", "refusal"), ("pause_turn", "error"), (None, "error"),
])
def test_anthropic_stop_reasons(stop, status):
    r = anthropic_.to_result(anth(stop), "claude-haiku-5-5", 100)
    assert r.status == status
    assert (r.error is not None) == (status == "error")


def test_anthropic_tool_call_and_usage():
    content = [NS(type="text", text="Перевірю."), NS(type="tool_use", id="tu_1", name="get_order_status", input={"order_id": "DEMO-1042"})]
    r = anthropic_.to_result(anth("tool_use", content, i=100, o=20, c=40), "claude-haiku-5-5", 10)
    assert r.tool_calls[0].name == "get_order_status" and r.tool_calls[0].args == {"order_id": "DEMO-1042"}
    assert (r.usage.input_tokens, r.usage.cached_input_tokens, r.usage.output_tokens) == (100, 40, 20)
    r = anthropic_.to_result(anth("end_turn", i=100, o=20, w=600), "claude-haiku-5-5", 10)
    assert (r.usage.input_tokens, r.usage.cache_write_tokens) == (700, 600)     # writes are input, flagged


# --- OpenAI ------------------------------------------------------------------------

def test_openai_request_shape():
    req = openai_.build_request(TOOL_TURN, system="sys", schema=TicketCard, tools=TOOLS, model="gpt-6-luna",
                                effort="low", max_output_tokens=512)
    assert req["instructions"] == "sys" and req["reasoning"] == {"effort": "low"}
    fmt = req["text"]["format"]
    assert fmt["type"] == "json_schema" and fmt["name"] == "TicketCard" and fmt["strict"] is True
    assert req["tools"][0]["type"] == "function" and req["tools"][0]["strict"] is True
    kinds = [i.get("type", i.get("role")) for i in req["input"]]
    assert kinds == ["user", "function_call", "function_call", "function_call_output", "function_call_output"]


def oai(status="completed", output=None, reason=None, i=50, o=10, cached=0, text='{"a":1}'):
    u = NS(input_tokens=i, output_tokens=o, input_tokens_details=NS(cached_tokens=cached))
    return NS(id="resp_1", status=status, incomplete_details=NS(reason=reason) if reason else None,
              output=output if output is not None else [NS(type="message", content=[NS(type="output_text", text=text)])],
              output_text=text, usage=u)


def test_openai_statuses():
    assert openai_.to_result(oai(), "m", 1).status == "ok"
    assert openai_.to_result(oai("incomplete", reason="max_output_tokens"), "m", 1).status == "truncated"
    assert openai_.to_result(oai("incomplete", reason="content_filter"), "m", 1).status == "refusal"
    assert openai_.to_result(oai("failed"), "m", 1).status == "error"
    refusal = [NS(type="message", content=[NS(type="refusal", refusal="Ні.")])]
    assert openai_.to_result(oai(output=refusal, text=""), "m", 1).status == "refusal"


def test_openai_tool_call_and_cached_tokens():
    fc = [NS(type="function_call", call_id="call_1", name="get_order_status", arguments='{"order_id": "DEMO-1042"}')]
    r = openai_.to_result(oai(output=fc, text="", i=100, cached=60), "gpt-6-luna", 1)
    assert r.status == "tool_call" and r.tool_calls[0].args == {"order_id": "DEMO-1042"}
    assert (r.usage.input_tokens, r.usage.cached_input_tokens) == (40, 60)   # cache is inside input_tokens


# --- Gemini ------------------------------------------------------------------------

def test_gemini_request_shape():
    req = gemini_.build_request(TOOL_TURN, system="sys", schema=TicketCard, tools=TOOLS,
                                model="gemini-2.5-flash-lite", effort="low", max_output_tokens=512, timeout_s=30)
    cfg = req["config"]
    assert cfg["response_mime_type"] == "application/json" and "response_json_schema" in cfg
    assert cfg["http_options"] == {"timeout": 30000, "retry_options": {"attempts": 1}}
    assert cfg["thinking_config"] == {"thinking_budget": 0}
    assert cfg["tools"][0]["function_declarations"][0]["name"] == "get_order_status"
    assert [c["role"] for c in req["contents"]] == ["user", "model", "tool", "tool"]
    assert gemini_.thinking_config("gemini-3.1-flash-lite", "medium") == {"thinking_level": "MEDIUM"}


def gem(finish="STOP", text='{"a":1}', calls=None, block=None, candidates=True):
    u = NS(prompt_token_count=100, candidates_token_count=10, thoughts_token_count=5, cached_content_token_count=30)
    return NS(candidates=[NS(finish_reason=NS(name=finish))] if candidates else [],
              prompt_feedback=NS(block_reason=NS(name=block)) if block else None,
              function_calls=calls, text=text, usage_metadata=u)


def test_gemini_statuses_and_usage():
    r = gemini_.to_result(gem(), "gemini-2.5-flash-lite", 1)
    assert r.status == "ok"
    assert (r.usage.input_tokens, r.usage.cached_input_tokens, r.usage.output_tokens) == (70, 30, 15)
    assert gemini_.to_result(gem("MAX_TOKENS"), "m", 1).status == "truncated"
    assert gemini_.to_result(gem("SAFETY"), "m", 1).status == "refusal"
    assert gemini_.to_result(gem(candidates=False, block="SAFETY"), "m", 1).status == "refusal"
    assert gemini_.to_result(gem("MALFORMED_FUNCTION_CALL"), "m", 1).status == "error"
    call = [NS(id=None, name="get_order_status", args={"order_id": "DEMO-1042"})]
    r = gemini_.to_result(gem(calls=call, text=""), "m", 1)
    assert r.status == "tool_call" and r.tool_calls[0].id == "gemini-call-0"


# --- errors ------------------------------------------------------------------------

def fake_exc(name, status=None, message=""):
    cls = type(name, (Exception,), {})
    exc = cls(message)
    if status is not None:
        exc.status_code = status
    return exc


@pytest.mark.parametrize("exc,code", [
    (fake_exc("APITimeoutError"), "timeout"),
    (fake_exc("RateLimitError", 429), "rate_limit"),
    (fake_exc("RateLimitError", 429, "You exceeded your current quota: insufficient_quota"), "spend_cap"),
    (fake_exc("BadRequestError", 400, "Your credit balance is too low"), "spend_cap"),
    (fake_exc("AuthenticationError", 401), "auth"),
    (fake_exc("APIConnectionError"), "connection"),
    (fake_exc("InternalServerError", 503), "server_error"),
    (fake_exc("BadRequestError", 400, "bad schema"), "bad_request"),
    # spend caps as providers send them today: never "rate_limit" (that one is retried) or "bad_request"
    (fake_exc("RateLimitError", 429, "rate_limit_error: enforced_spend_limit_reached"), "spend_cap"),
    (fake_exc("BadRequestError", 400, "You have reached your specified API usage limits"), "spend_cap"),
    (fake_exc("RateLimitError", 429, "project_spend_limit_exceeded"), "spend_cap"),
    (fake_exc("RateLimitError", 429, "credit_balance_exhausted"), "spend_cap"),
    (fake_exc("ClientError", 402, "Payment required"), "spend_cap"),
])
def test_error_codes(exc, code):
    assert error_code(exc) == code
