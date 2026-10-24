"""call_model: one provider-neutral call (CONTRACT.md, section «call_model»).

Message shape (provider-neutral):
  {"role": "user" | "assistant", "content": str}
  {"role": "assistant", "content": "", "tool_calls": [{"id", "name", "args"}]}   (L13+)
  {"role": "tool", "tool_call_id": str, "name": str, "content": str, "is_error": bool}  (L13+)
Tool shape: {"name": str, "description": str, "parameters": <JSON schema>}.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Literal

from pydantic import ValidationError

from support import config, prices


@dataclass
class Usage:
    input_tokens: int = 0           # input that was NOT served from cache
    output_tokens: int = 0          # includes thinking tokens where the provider bills them
    cached_input_tokens: int = 0
    cache_write_tokens: int = 0     # part of input_tokens written to the cache (Anthropic bills it at 1.25x input)


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


RETRY_ON = ("timeout", "rate_limit")     # lesson 6: one retry, only for temporary errors (lesson 17 replaces it)
RETRY_SLEEP_S = 1.0

_collector: ContextVar[list | None] = ContextVar("aiez_call_collector", default=None)


@contextmanager
def collect_calls():
    """Collect every ModelResult made inside the block (run_evals uses it for cost and latency)."""
    bucket: list[ModelResult] = []
    token = _collector.set(bucket)
    try:
        yield bucket
    finally:
        _collector.reset(token)


def _adapter(provider: str):
    if provider == "mock":
        from support.llm import mock
        return mock
    if provider == "anthropic":
        from support.llm import anthropic_
        return anthropic_
    if provider == "openai":
        from support.llm import openai_
        return openai_
    if provider == "gemini":
        from support.llm import gemini_
        return gemini_
    return None


def _once(provider, messages, **kw) -> ModelResult:
    adapter = _adapter(provider)
    model_id = kw["model"]
    if adapter is None:
        return ModelResult(status="error", provider=provider, model=model_id,
                           error=f"unknown_provider: {provider!r}; use one of {', '.join(config.PROVIDERS)}")
    if provider == "mock":
        return adapter.complete(messages, **kw)
    key = config.api_key(provider)
    if not key:
        names = " or ".join(config.API_KEY_ENV[provider])
        return ModelResult(status="error", provider=provider, model=model_id,
                           error=f"no_api_key: put {names} in .env (never in code)")
    kw.pop("purpose", None)
    return adapter.complete(messages, api_key=key, **kw)


def _log(result: ModelResult, *, purpose: str, messages: list[dict], system: str | None, attempts: int) -> None:
    """One line per call in runs/calls.jsonl: ids, sizes and a hash, never the ticket text."""
    if os.environ.get("AIEZ_LOG_CALLS", "1") == "0":
        return
    prompt = json.dumps([system, messages], ensure_ascii=False, sort_keys=True)
    line = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "provider": result.provider, "model": result.model, "purpose": purpose,
        "status": result.status, "error": result.error, "stop_reason": result.stop_reason,
        "attempts": attempts, "usage": asdict(result.usage), "cost_usd": result.cost_usd,
        "simulated_cost": result.simulated_cost, "price_known": (result.raw or {}).get("price_known", True),
        "latency_ms": result.latency_ms, "input_chars": len(prompt), "output_chars": len(result.text),
        "input_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:12],
    }
    folder = config.runs_dir()
    folder.mkdir(parents=True, exist_ok=True)
    with (folder / "calls.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(line, ensure_ascii=False) + "\n")


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
    kw = dict(system=system, schema=schema, tools=tools, model=model_id, effort=effort,
              max_output_tokens=max_output_tokens, timeout_s=timeout_s, purpose=purpose)

    total_latency, attempts = 0, 0
    while True:
        attempts += 1
        result = _once(provider, messages, **dict(kw))
        total_latency += result.latency_ms
        if result.status == "error" and result.error in RETRY_ON and attempts == 1:
            if provider != "mock":
                time.sleep(RETRY_SLEEP_S)
            continue
        break
    result.latency_ms = total_latency
    result.raw = {**(result.raw or {}), "attempts": attempts}

    if provider == "mock":
        result.cost_usd, result.simulated_cost = 0.0, True
    else:
        cost = prices.estimate_usd(result.model, result.usage.input_tokens, result.usage.output_tokens,
                                   result.usage.cached_input_tokens,
                                   cache_write_tokens=result.usage.cache_write_tokens)
        result.cost_usd = cost or 0.0
        result.raw["price_known"] = cost is not None
    if schema is not None:
        parse_into(result, schema)

    _log(result, purpose=purpose, messages=messages, system=system, attempts=attempts)
    bucket = _collector.get()
    if bucket is not None:
        bucket.append(result)
    return result


__all__ = ["Usage", "ToolCall", "ModelResult", "call_model", "collect_calls", "strip_fences", "parse_into"]
