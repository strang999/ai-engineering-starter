"""OpenAI adapter (Responses API, Python SDK `openai`).

UNTESTED against the live API: no key was used when this was written. The request
shape and the response mapping are checked offline (tests/test_adapters.py) and
against the installed SDK's signatures. Sources and dates: docs/VERIFIED.md.

    uv sync --extra openai         # installs the SDK
    .env: AIEZ_PROVIDER=openai, OPENAI_API_KEY=...
"""

from __future__ import annotations

import json
import time

from support.llm._common import error_code, json_schema

ENV_KEY = "OPENAI_API_KEY"


def convert_messages(messages: list[dict]) -> list[dict]:
    items: list[dict] = []
    for m in messages:
        role = m["role"]
        if role == "tool":
            items.append({"type": "function_call_output", "call_id": m["tool_call_id"],
                          "output": str(m.get("content", ""))})
        elif role == "assistant" and m.get("tool_calls"):
            if m.get("content"):
                items.append({"role": "assistant", "content": m["content"]})
            items += [{"type": "function_call", "call_id": c["id"], "name": c["name"],
                       "arguments": json.dumps(c["args"], ensure_ascii=False)} for c in m["tool_calls"]]
        else:
            items.append({"role": role, "content": str(m.get("content", ""))})
    return items


def build_request(messages, *, system, schema, tools, model, effort, max_output_tokens) -> dict:
    req = {"model": model, "input": convert_messages(messages),
           "max_output_tokens": max_output_tokens, "reasoning": {"effort": effort}}
    if system:
        req["instructions"] = system
    if schema is not None:
        req["text"] = {"format": {"type": "json_schema", "name": schema.__name__,
                                  "schema": json_schema(schema), "strict": True}}
    if tools:
        req["tools"] = [{"type": "function", "name": t["name"], "description": t.get("description", ""),
                         "parameters": t["parameters"], "strict": True} for t in tools]
    return req


def to_result(resp, model: str, latency_ms: int):
    from support.llm import ModelResult, ToolCall, Usage

    calls, refusal = [], False
    for item in resp.output or []:
        kind = getattr(item, "type", "")
        if kind == "function_call":
            try:
                args = json.loads(item.arguments or "{}")
            except json.JSONDecodeError:
                args = {"_unparsed": item.arguments}
            calls.append(ToolCall(id=item.call_id, name=item.name, args=args))
        elif kind == "message":
            refusal = refusal or any(getattr(p, "type", "") == "refusal" for p in item.content or [])

    raw_status = getattr(resp, "status", "") or ""
    reason = getattr(getattr(resp, "incomplete_details", None), "reason", None)
    if raw_status == "incomplete":
        status = "refusal" if reason == "content_filter" else "truncated"
    elif raw_status != "completed":
        status = "error"
    elif refusal:
        status = "refusal"
    elif calls:
        status = "tool_call"
    else:
        status = "ok"

    u = resp.usage
    cached = (getattr(getattr(u, "input_tokens_details", None), "cached_tokens", 0) or 0) if u else 0
    usage = Usage(input_tokens=max(0, (u.input_tokens if u else 0) - cached),   # OpenAI counts cache inside input
                  output_tokens=u.output_tokens if u else 0,                      # includes reasoning tokens
                  cached_input_tokens=cached)
    stop = f"{raw_status}:{reason}" if reason else raw_status
    return ModelResult(status=status, text=getattr(resp, "output_text", "") or "", tool_calls=calls, usage=usage,
                       latency_ms=latency_ms, provider="openai", model=model, stop_reason=stop,
                       error=stop if status == "error" else None,
                       raw={"id": getattr(resp, "id", None), "status": raw_status, "reason": reason})


def complete(messages, *, system, schema, tools, model, effort, max_output_tokens, timeout_s, api_key):
    from support.llm import ModelResult

    try:
        import openai
    except ImportError:
        return ModelResult(status="error", provider="openai", model=model,
                           error="sdk_missing: run `uv sync --extra openai`")
    req = build_request(messages, system=system, schema=schema, tools=tools, model=model,
                        effort=effort, max_output_tokens=max_output_tokens)
    client = openai.OpenAI(api_key=api_key, max_retries=0)       # retries are call_model's job
    started = time.perf_counter()
    try:
        resp = client.responses.create(**req, timeout=timeout_s)
    except Exception as exc:  # noqa: BLE001 - every provider failure becomes a status
        return ModelResult(status="error", provider="openai", model=model, error=error_code(exc),
                           latency_ms=int((time.perf_counter() - started) * 1000),
                           raw={"exception": type(exc).__name__, "message": str(exc)[:300]})
    return to_result(resp, model, int((time.perf_counter() - started) * 1000))
