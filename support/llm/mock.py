"""Mock provider: deterministic, offline, free. The default for every lesson and test.

This is a failure simulator, not a model. Card replies come from
fixtures/mock_replies.jsonl (keyed by ticket_id), else from a small rules-based
fallback that emits valid TicketCard JSON. The mock reads the ticket from the
`<ticket id="...">text</ticket>` block of the last user message.

Pick a scenario with AIEZ_MOCK_SCENARIO, use_scenario(), or a per-case "mock"
field in evals/cases.jsonl. The list is SCENARIOS below.
"""

from __future__ import annotations

import json
import math
import os
import re
from contextlib import contextmanager
from contextvars import ContextVar
from functools import lru_cache

from support.config import ROOT

SCENARIOS: tuple[str, ...] = (
    "ok", "fenced_json", "malformed_json", "wrong_schema", "invented_evidence",
    "invented_category", "refusal", "truncated", "rate_limit_then_ok", "rate_limit",
    "timeout", "spend_cap", "server_error", "tool_call_status", "tool_call_wrong_amount",
    "tool_call_unoffered_tool", "injection_followed",
)
TOOL_SCENARIOS = ("tool_call_status", "tool_call_wrong_amount", "tool_call_unoffered_tool", "injection_followed")
ERROR_SCENARIOS = {"rate_limit": "rate_limit", "timeout": "timeout", "spend_cap": "spend_cap", "server_error": "server_error"}

FIXTURES = ROOT / "fixtures" / "mock_replies.jsonl"

_scenario: ContextVar[str | None] = ContextVar("aiez_mock_scenario", default=None)
_state: ContextVar[dict | None] = ContextVar("aiez_mock_state", default=None)
_GLOBAL_STATE: dict = {}


@contextmanager
def use_scenario(name: str | None):
    """Run a block under one mock scenario, with fresh attempt counters."""
    if name is not None and name not in SCENARIOS:
        raise ValueError(f"unknown mock scenario {name!r}; known: {', '.join(SCENARIOS)}")
    t1, t2 = _scenario.set(name), _state.set({})
    try:
        yield
    finally:
        _scenario.reset(t1)
        _state.reset(t2)


def current_scenario() -> str:
    name = _scenario.get() or (os.environ.get("AIEZ_MOCK_SCENARIO") or "").strip() or "ok"
    if name not in SCENARIOS:
        raise ValueError(f"unknown AIEZ_MOCK_SCENARIO {name!r}; known: {', '.join(SCENARIOS)}")
    return name


def _counter(key: str) -> int:
    state = _state.get()
    if state is None:
        state = _GLOBAL_STATE
    state[key] = state.get(key, 0) + 1
    return state[key]


# --- the fallback "model": small keyword tables, independent of support/rules.py ---

_LOOKALIKES = str.maketrans({"е": "e", "Е": "E", "о": "o", "О": "O", "м": "m", "М": "M",
                             "а": "a", "А": "A", "с": "c", "С": "C", "р": "p", "Р": "P"})
_ORDER_RE = re.compile(r"[dD][eEеЕ][mMмМ][oOоО][\s\-_]*(\d{4})")
_AMOUNT_RE = re.compile(r"(\d{1,3}(?:[  ]\d{3})+|\d+)(?:[.,]\d{1,2})?\s*(?:грн|гривень|гривні|uah)", re.I)
_WORD = r"[\w'ʼ’\-]"

_CATEGORY_WORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("брак", ("зламан", "розбит", "відклеє", "пошкодж")),
    ("обмін", ("поміня", "обміня", "обмін")),
    ("повернення", ("поверн", "povern")),
    ("оплата", ("списали", "оплат", "помилка e-")),
    ("акаунт", ("пароль", "увійти", "кабінет", "email", "профіл")),
    ("доставка", ("посилк", "доставк", "кур'єр", "курʼєр", "не приїхав", "де воно")),
    ("інше", ("сертифікат",)),
)
_TAG_WORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("терміново", ("терміново",)),
    ("повторне_звернення", ("втретє", "вдруге", "повторно")),
    ("погроза_суду", ("в суд", "до суду")),
    ("скарга", ("нахамив", "жахлив", "скарг")),
)


def _word_at(text: str, start: int, end: int) -> str:
    """Expand a keyword hit to the whole word, so the evidence is a verbatim quote."""
    left = start
    while left > 0 and re.match(_WORD, text[left - 1]):
        left -= 1
    right = end
    while right < len(text) and re.match(_WORD, text[right]):
        right += 1
    return text[left:right]


def fallback_card(text: str) -> dict:
    low = text.lower()
    category, evidence = "невідомо", None
    for cat, words in _CATEGORY_WORDS:
        hits = [(low.find(w), w) for w in words if w in low]
        if hits:
            pos, word = min(hits)
            category, evidence = cat, _word_at(text, pos, pos + len(word))
            break
    order = {"value": None, "evidence": None}
    m = _ORDER_RE.search(text)
    if m:
        order = {"value": f"DEMO-{m.group(1)}", "evidence": m.group(0)}
    amount = {"value": None, "evidence": None}
    a = _AMOUNT_RE.search(text)
    if a:
        amount = {"value": a.group(0), "evidence": a.group(0)}
    tags = [tag for tag, words in _TAG_WORDS if any(w in low for w in words)]
    return {"category": category, "category_evidence": evidence,
            "order_id": order, "amount": amount, "tags": tags}


@lru_cache(maxsize=1)
def _fixtures() -> dict[str, dict]:
    if not FIXTURES.is_file():
        return {}
    out = {}
    for line in FIXTURES.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            out[row["ticket_id"]] = row["card"]
    return out


_TICKET_RE = re.compile(r'<ticket id="([^"]*)"[^>]*>(.*?)</ticket>', re.S)


def _last_user_text(messages: list[dict]) -> str:
    for msg in reversed(messages):
        if msg.get("role") == "user":
            return str(msg.get("content", ""))
    return ""


def parse_ticket(messages: list[dict]) -> tuple[str | None, str]:
    content = _last_user_text(messages)
    m = _TICKET_RE.search(content)
    if m:
        return m.group(1), m.group(2)
    return None, content


def card_for(ticket_id: str | None, text: str) -> dict:
    fixture = _fixtures().get(ticket_id or "")
    return json.loads(json.dumps(fixture)) if fixture else fallback_card(text)


def _tokens(chars: int) -> int:
    return max(1, math.ceil(chars / 4))


def complete(messages: list[dict], *, system: str | None, schema: type | None,
             tools: list[dict] | None, model: str, effort: str,
             max_output_tokens: int, timeout_s: float, purpose: str):
    """One mock call. Returns a ModelResult (imported lazily to avoid a cycle)."""
    from support.llm import ModelResult, ToolCall, Usage

    scenario = current_scenario()
    in_chars = len(system or "") + sum(len(str(m.get("content", ""))) for m in messages)
    usage = Usage(input_tokens=_tokens(in_chars))

    def done(status: str, text: str = "", *, error: str | None = None,
             tool_calls: list | None = None, stop: str = "") -> ModelResult:
        out_chars = len(text) + sum(len(json.dumps(c.args, ensure_ascii=False)) + len(c.name) for c in (tool_calls or []))
        usage.output_tokens = _tokens(out_chars) if status in ("ok", "tool_call", "truncated", "refusal") else 0
        latency = int(timeout_s * 1000) if error == "timeout" else 120 + usage.output_tokens // 10
        return ModelResult(status=status, text=text, tool_calls=tool_calls or [], usage=usage,
                           cost_usd=0.0, simulated_cost=True, latency_ms=latency,
                           provider="mock", model=model, stop_reason=stop or status, error=error,
                           raw={"mock_scenario": scenario, "purpose": purpose})

    # transport-level failures first
    if scenario in ERROR_SCENARIOS:
        return done("error", error=ERROR_SCENARIOS[scenario], stop="error")
    if scenario == "rate_limit_then_ok" and _counter("rate_limit_then_ok") == 1:
        return done("error", error="rate_limit", stop="error")
    if scenario == "refusal":
        return done("refusal", "Вибач, з цим запитом я не допоможу.", stop="refusal")

    if tools:
        return _tool_turn(messages, tools, scenario, done)
    if scenario in TOOL_SCENARIOS:
        return done("error", error="bad_request: mock scenario needs tools", stop="error")

    if purpose == "card":
        ticket_id, text = parse_ticket(messages)
        card = card_for(ticket_id, text)
        if scenario == "invented_evidence":
            card["order_id"] = {"value": "DEMO-1042", "evidence": "моє замовлення DEMO-1042 від учора"}
        elif scenario == "invented_category":
            card["category"] = "повернення"
            card["category_evidence"] = "поверніть гроші негайно"
        body = json.dumps(card, ensure_ascii=False)
        if scenario == "wrong_schema":
            body = json.dumps({"category": "refund", "order": card["order_id"]["value"]}, ensure_ascii=False)
        elif scenario == "fenced_json":
            body = "```json\n" + body + "\n```"
        elif scenario == "malformed_json":
            body = "Ось картка: {" + body[1:40]
        elif scenario == "truncated":
            return done("truncated", body[: len(body) // 2], stop="max_tokens")
        return done("ok", body, stop="end_turn")

    return done("ok", f"mock-1: немає заготовленої відповіді для purpose={purpose!r}", stop="end_turn")


def _tool_turn(messages, tools, scenario, done):
    from support.llm import ToolCall

    offered = {t["name"] for t in tools}
    last_user = max((i for i, m in enumerate(messages) if m.get("role") == "user"), default=-1)
    results = [m for m in messages[last_user + 1:] if m.get("role") == "tool"]
    if results:
        last = str(results[-1].get("content", ""))
        return done("ok", "Ось що показала система: " + last[:300], stop="end_turn")

    text = _last_user_text(messages)
    m = _ORDER_RE.search(text)
    order_id = f"DEMO-{m.group(1)}" if m else None

    def call(name: str, args: dict):
        n = _counter("tool_call_id")
        return done("tool_call", tool_calls=[ToolCall(id=f"mock-call-{n}", name=name, args=args)], stop="tool_use")

    if scenario == "tool_call_wrong_amount":
        return call("create_refund_draft", {"order_id": order_id or "DEMO-1043", "amount_kop": "540", "reason": "не_прийшло"})
    if scenario == "tool_call_unoffered_tool":
        return call("create_refund_draft", {"order_id": order_id or "DEMO-1043", "amount_kop": 54000, "reason": "не_прийшло"})
    if scenario == "injection_followed":
        return call("create_refund_draft", {"order_id": order_id or "DEMO-1043", "amount_kop": 500000, "reason": "не_прийшло"})
    if order_id and ("get_order_status" in offered or scenario == "tool_call_status"):
        return call("get_order_status", {"order_id": order_id})
    return done("ok", "Підкажи, будь ласка, номер замовлення у форматі DEMO-1234.", stop="end_turn")
