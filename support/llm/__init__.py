"""call_model: one provider-neutral call (CONTRACT.md, section «call_model»).

Message shape (provider-neutral):
  {"role": "user" | "assistant", "content": str}
  {"role": "assistant", "content": "", "tool_calls": [{"id", "name", "args"}]}   (L13+)
  {"role": "tool", "tool_call_id": str, "name": str, "content": str, "is_error": bool}  (L13+)
Tool shape: {"name": str, "description": str, "parameters": <JSON schema>}.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

from pydantic import ValidationError

from support import config


@dataclass
class Usage:
    input_tokens: int = 0           # input that was NOT served from cache
    output_tokens: int = 0          # includes thinking tokens where the provider bills them
    cached_input_tokens: int = 0


@dataclass
class ToolCall:
    id: str
    name: str
    args: dict


@dataclass
class ModelResult:
    status: Literal["ok", "tool_call", "refusal", "truncated", "error"]
    text: str = ""
    parsed: object | None = None    # pydantic instance when schema= was given and parsing passed
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)
    cost_usd: float = 0.0           # computed by OUR code: usage x prices.py; no provider returns it
    simulated_cost: bool = False    # True in mock mode
    latency_ms: int = 0
    provider: str = "mock"
    model: str = "mock-1"
    stop_reason: str = ""           # provider's raw value, for the trace
    error: str | None = None        # "timeout", "rate_limit", "spend_cap", "bad_request", "schema_error", ...
    raw: dict | None = None         # saved to runs/ for L08 failure hunting


_FENCE_RE = re.compile(r"^\s*```[a-zA-Z]*\s*\n(.*?)\n?\s*```\s*$", re.S)


def strip_fences(text: str) -> str:
    """'```json\\n{...}\\n```' -> '{...}'. Chat-style models wrap JSON like this all the time."""
    m = _FENCE_RE.match(text)
    return m.group(1) if m else text.strip()


def parse_into(result: ModelResult, schema: type) -> ModelResult:
    """Validate result.text with pydantic. On failure: parsed=None, error='schema_error'."""
    if result.status != "ok":
        return result
    try:
        result.parsed = schema.model_validate_json(strip_fences(result.text))
    except (ValidationError, ValueError) as exc:
        result.parsed = None
        result.error = "schema_error"
        result.raw = {**(result.raw or {}), "schema_error": str(exc)[:500]}
    return result


def call_model(messages: list[dict], *, system: str | None = None,
               schema: type | None = None, tools: list[dict] | None = None,
               model: str | None = None, effort: str = "low",
               max_output_tokens: int = 1024, timeout_s: float = 30.0,
               purpose: str = "card") -> ModelResult:
    """Never raises for provider problems: returns status="error" with `error`.
    Raises ValueError only for programmer errors (bad arguments)."""
    if not isinstance(messages, list) or not messages:
        raise ValueError("messages must be a non-empty list of {'role', 'content'} dicts")
    if effort not in ("low", "medium", "high"):
        raise ValueError("effort must be 'low', 'medium' or 'high'")
    provider, model_id = config.resolve(model)
    if provider != "mock":
        return ModelResult(status="error", provider=provider, model=model_id,
                           error=f"provider_not_available: {provider!r} arrives in lesson 6 (tag l06); use AIEZ_PROVIDER=mock")

    from support.llm import mock
    result = mock.complete(messages, system=system, schema=schema, tools=tools, model=model_id,
                           effort=effort, max_output_tokens=max_output_tokens,
                           timeout_s=timeout_s, purpose=purpose)
    if schema is not None:
        parse_into(result, schema)
    return result


__all__ = ["Usage", "ToolCall", "ModelResult", "call_model", "strip_fences", "parse_into"]
