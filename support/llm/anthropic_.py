"""Anthropic adapter (Messages API, Python SDK `anthropic`).

UNTESTED against the live API: no key was used when this was written. The request
shape and the response mapping are checked offline (tests/test_adapters.py) and
against the installed SDK's signatures. Sources and dates: docs/VERIFIED.md.

    uv sync --extra anthropic      # installs the SDK
    .env: AIEZ_PROVIDER=anthropic, ANTHROPIC_API_KEY=...
          ANTHROPIC_WORKSPACE_ID=...   only for a key that is not scoped to a workspace
          AIEZ_ANTHROPIC_CACHE=0       turns prompt caching off (on by default)
"""

from __future__ import annotations

import os
import time

from support.llm._common import error_code, json_schema

ENV_KEY = "ANTHROPIC_API_KEY"

# stop_reason -> ModelResult.status, one table (CONTRACT.md, section 5)
STOP_STATUS = {
    "end_turn": "ok",
    "stop_sequence": "ok",
    "tool_use": "tool_call",
    "max_tokens": "truncated",
    "model_context_window_exceeded": "truncated",
    "refusal": "refusal",
    "pause_turn": "error",           # server tool paused the turn; we do not use server tools
}


def convert_messages(messages: list[dict]) -> list[dict]:
    out: list[dict] = []
    for m in messages:
        role = m["role"]
        if role == "tool":
            block = {"type": "tool_result", "tool_use_id": m["tool_call_id"],
                     "content": str(m.get("content", "")), "is_error": bool(m.get("is_error"))}
            if out and out[-1]["role"] == "user" and isinstance(out[-1]["content"], list) \
                    and all(b.get("type") == "tool_result" for b in out[-1]["content"]):
                out[-1]["content"].append(block)      # all results of one turn go in ONE user message
            else:
                out.append({"role": "user", "content": [block]})
        elif role == "assistant" and m.get("tool_calls"):
            blocks = [{"type": "text", "text": m["content"]}] if m.get("content") else []
            blocks += [{"type": "tool_use", "id": c["id"], "name": c["name"], "input": c["args"]} for c in m["tool_calls"]]
            out.append({"role": "assistant", "content": blocks})
        else:
            out.append({"role": role, "content": str(m.get("content", ""))})
    return out


def build_request(messages, *, system, schema, tools, model, effort, max_output_tokens) -> dict:
    output_config: dict = {"effort": effort}       # Haiku 5.5 defaults to "medium": we set it explicitly
    if schema is not None:
        output_config["format"] = {"type": "json_schema", "schema": json_schema(schema)}
    req = {"model": model, "max_tokens": max_output_tokens,
           "messages": convert_messages(messages), "output_config": output_config}
    if system:
        req["system"] = system
    if tools:
        req["tools"] = [{"name": t["name"], "description": t.get("description", ""),
                         "input_schema": t["parameters"], "strict": True} for t in tools]
    if os.environ.get("AIEZ_ANTHROPIC_CACHE", "1") != "0":
        # automatic prompt caching: the API caches the longest reusable prefix; prompts shorter than
        # the model's minimum (512 tokens on Haiku 5.5) are simply not cached, no error
        req["cache_control"] = {"type": "ephemeral"}
    return req                                     # no temperature: removed in API version 2026-10-21


def client_headers() -> dict | None:
    """A key that is not scoped to a workspace must name one: ANTHROPIC_WORKSPACE_ID in .env (optional)."""
    workspace = (os.environ.get("ANTHROPIC_WORKSPACE_ID") or "").strip()
    return {"anthropic-workspace-id": workspace} if workspace else None


def to_result(resp, model: str, latency_ms: int):
    from support.llm import ModelResult, ToolCall, Usage

    stop = resp.stop_reason or ""
    status = STOP_STATUS.get(stop, "error")
    text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
    calls = [ToolCall(id=b.id, name=b.name, args=dict(b.input))
             for b in resp.content if getattr(b, "type", "") == "tool_use"]
    u = resp.usage
    written = getattr(u, "cache_creation_input_tokens", 0) or 0
    usage = Usage(
        input_tokens=(u.input_tokens or 0) + written,     # cache writes are uncached input, billed at 1.25x
        output_tokens=u.output_tokens or 0,
        cached_input_tokens=getattr(u, "cache_read_input_tokens", 0) or 0,
        cache_write_tokens=written,
    )
    error = None
    if status == "error":
        error = stop or "no_stop_reason"
    return ModelResult(status=status, text=text, tool_calls=calls, usage=usage, latency_ms=latency_ms,
                       provider="anthropic", model=model, stop_reason=stop, error=error,
                       raw={"id": getattr(resp, "id", None), "stop_reason": stop})


def complete(messages, *, system, schema, tools, model, effort, max_output_tokens, timeout_s, api_key):
    from support.llm import ModelResult

    try:
        import anthropic
    except ImportError:
        return ModelResult(status="error", provider="anthropic", model=model,
                           error="sdk_missing: run `uv sync --extra anthropic`")
    req = build_request(messages, system=system, schema=schema, tools=tools, model=model,
                        effort=effort, max_output_tokens=max_output_tokens)
    client = anthropic.Anthropic(api_key=api_key, max_retries=0,   # retries are call_model's job
                                 default_headers=client_headers())
    started = time.perf_counter()
    try:
        resp = client.messages.create(**req, timeout=timeout_s)
    except Exception as exc:  # noqa: BLE001 - every provider failure becomes a status
        return ModelResult(status="error", provider="anthropic", model=model, error=error_code(exc),
                           latency_ms=int((time.perf_counter() - started) * 1000),
                           raw={"exception": type(exc).__name__, "message": str(exc)[:300]})
    return to_result(resp, model, int((time.perf_counter() - started) * 1000))

