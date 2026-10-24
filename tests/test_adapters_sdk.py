"""Live adapters through the REAL provider SDKs, against a local stub HTTP server.

Skipped unless the SDKs are installed:  uv sync --extra anthropic --extra openai --extra gemini
No key, no internet: the stub answers on 127.0.0.1. This proves the SDK accepts our request
and our mapping reads the SDK's response objects. It does NOT prove the live API accepts the
request (schema features, model ids, effort values): see docs/VERIFIED.md.
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from support.card import CARD_SYSTEM, build_card_prompt
from support.contract import TicketCard, tool_parameters
from support.data import get_ticket
from support.llm import parse_into

CARD = json.dumps({"category": "доставка", "category_evidence": "посилку",
                   "order_id": {"value": "DEMO-1042", "evidence": "DEMO-1042"},
                   "amount": {"value": None, "evidence": None}, "tags": []}, ensure_ascii=False)
TOOLS = [{"name": "get_order_status", "description": "Статус замовлення", "parameters": tool_parameters("get_order_status")}]
TOOL_TURN = [
    {"role": "user", "content": "Де DEMO-1042?"},
    {"role": "assistant", "content": "", "tool_calls": [{"id": "c1", "name": "get_order_status", "args": {"order_id": "DEMO-1042"}}]},
    {"role": "tool", "tool_call_id": "c1", "name": "get_order_status", "content": "shipped", "is_error": False},
]


class Stub(BaseHTTPRequestHandler):
    seen: list = []
    status = 200

    def log_message(self, *args):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])) or b"{}")
        Stub.seen.append((self.path, body, dict(self.headers)))
        if Stub.status != 200:
            data = json.dumps({"type": "error", "error": {"type": "rate_limit_error", "message": "slow down",
                                                          "code": Stub.status, "status": "RESOURCE_EXHAUSTED"}}).encode()
            self.send_response(Stub.status)
        else:
            data = json.dumps(self.reply(body), ensure_ascii=False).encode()
            self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def reply(self, body):
        if "/messages" in self.path:
            return {"id": "msg_1", "type": "message", "role": "assistant", "model": body["model"],
                    "content": [{"type": "text", "text": CARD}], "stop_reason": "end_turn", "stop_sequence": None,
                    "usage": {"input_tokens": 120, "output_tokens": 40, "cache_read_input_tokens": 0,
                              "cache_creation_input_tokens": 0}}
        if "/responses" in self.path:
            return {"id": "resp_1", "object": "response", "created_at": 0, "status": "completed", "model": body["model"],
                    "parallel_tool_calls": True, "tool_choice": "auto", "tools": [],
                    "output": [{"type": "message", "id": "m1", "status": "completed", "role": "assistant",
                                "content": [{"type": "output_text", "text": CARD, "annotations": []}]}],
                    "usage": {"input_tokens": 100, "input_tokens_details": {"cached_tokens": 20}, "output_tokens": 30,
                              "output_tokens_details": {"reasoning_tokens": 5}, "total_tokens": 130}}
        return {"candidates": [{"content": {"role": "model", "parts": [{"text": CARD}]}, "finishReason": "STOP"}],
                "usageMetadata": {"promptTokenCount": 100, "candidatesTokenCount": 30, "thoughtsTokenCount": 7}}


@pytest.fixture
def stub(monkeypatch):
    Stub.seen, Stub.status = [], 200
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Stub)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    monkeypatch.setenv("ANTHROPIC_BASE_URL", base)
    monkeypatch.setenv("OPENAI_BASE_URL", base + "/v1")
    yield base
    srv.shutdown()


KW = dict(system=CARD_SYSTEM, schema=TicketCard, tools=None, effort="low", max_output_tokens=1024,
          timeout_s=10, api_key="test-key-not-real")


def card_messages():
    return build_card_prompt(get_ticket("T-0001"))


def test_anthropic_sdk(stub, monkeypatch):
    pytest.importorskip("anthropic")
    from support.llm import anthropic_
    monkeypatch.setenv("ANTHROPIC_WORKSPACE_ID", "wrkspc_test")
    r = anthropic_.complete(card_messages(), model="claude-haiku-5-5", **KW)
    path, body, headers = Stub.seen[-1]
    assert r.status == "ok" and isinstance(parse_into(r, TicketCard).parsed, TicketCard)
    assert path == "/v1/messages" and body["output_config"]["effort"] == "low"
    assert "temperature" not in body
    assert body["cache_control"] == {"type": "ephemeral"}
    assert {k.lower(): v for k, v in headers.items()}["anthropic-workspace-id"] == "wrkspc_test"
    r = anthropic_.complete(TOOL_TURN, model="claude-haiku-5-5", **{**KW, "schema": None, "tools": TOOLS})
    assert r.status == "ok" and Stub.seen[-1][1]["tools"][0]["strict"] is True
    Stub.status = 429
    assert anthropic_.complete(card_messages(), model="claude-haiku-5-5", **KW).error == "rate_limit"


def test_openai_sdk(stub):
    pytest.importorskip("openai")
    from support.llm import openai_
    r = openai_.complete(card_messages(), model="gpt-6-luna", **KW)
    path, body, _ = Stub.seen[-1]
    assert r.status == "ok" and (r.usage.input_tokens, r.usage.cached_input_tokens) == (80, 20)
    assert path == "/v1/responses" and body["text"]["format"]["strict"] is True
    r = openai_.complete(TOOL_TURN, model="gpt-6-luna", **{**KW, "schema": None, "tools": TOOLS})
    assert r.status == "ok" and Stub.seen[-1][1]["input"][-1]["type"] == "function_call_output"
    Stub.status = 429
    assert openai_.complete(card_messages(), model="gpt-6-luna", **KW).error == "rate_limit"


def test_gemini_sdk(stub):
    genai = pytest.importorskip("google.genai")
    from support.llm import gemini_
    from support.llm._common import error_code
    client = genai.Client(api_key="test-key-not-real", http_options={"base_url": stub, "retry_options": {"attempts": 1}})
    req = gemini_.build_request(card_messages(), model="gemini-2.5-flash-lite", **{k: v for k, v in KW.items() if k != "api_key"})
    req["config"]["http_options"]["base_url"] = stub
    r = gemini_.to_result(client.models.generate_content(**req), "gemini-2.5-flash-lite", 1)
    path, body, _ = Stub.seen[-1]
    assert r.status == "ok" and r.usage.output_tokens == 37
    assert path.endswith("gemini-2.5-flash-lite:generateContent") and "responseJsonSchema" in body["generationConfig"]
    req = gemini_.build_request(TOOL_TURN, model="gemini-2.5-flash-lite",
                                **{**{k: v for k, v in KW.items() if k != "api_key"}, "schema": None, "tools": TOOLS})
    req["config"]["http_options"]["base_url"] = stub
    client.models.generate_content(**req)
    assert "functionDeclarations" in json.dumps(Stub.seen[-1][1])
    Stub.status = 429
    with pytest.raises(Exception) as exc:
        client.models.generate_content(**req)
    assert error_code(exc.value) == "rate_limit"
