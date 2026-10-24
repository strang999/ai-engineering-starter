"""Google Gemini adapter (generate_content, Python SDK `google-genai`).

UNTESTED against the live API: no key was used when this was written. The request
shape and the response mapping are checked offline (tests/test_adapters.py) and
against the installed SDK's types. Sources and dates: docs/VERIFIED.md.
Google labels the generate_content pages «Legacy» (2026-10); the call still works and is documented.

    uv sync --extra gemini         # installs the SDK
    .env: AIEZ_PROVIDER=gemini, GEMINI_API_KEY=...
"""

from __future__ import annotations

import time

from support.llm._common import error_code, json_schema

ENV_KEY = "GEMINI_API_KEY"

REFUSAL_REASONS = {"SAFETY", "RECITATION", "BLOCKLIST", "PROHIBITED_CONTENT", "SPII", "IMAGE_SAFETY", "LANGUAGE"}


def convert_messages(messages: list[dict]) -> list[dict]:
    contents: list[dict] = []
    for m in messages:
        role = m["role"]
        if role == "tool":
            contents.append({"role": "tool", "parts": [{"function_response": {
                "id": m.get("tool_call_id"), "name": m.get("name", ""),
                "response": {"result" if not m.get("is_error") else "error": str(m.get("content", ""))}}}]})
        elif role == "assistant" and m.get("tool_calls"):
            parts = [{"text": m["content"]}] if m.get("content") else []
            parts += [{"function_call": {"id": c["id"], "name": c["name"], "args": c["args"]}} for c in m["tool_calls"]]
            contents.append({"role": "model", "parts": parts})
        else:
            contents.append({"role": "model" if role == "assistant" else "user",
                             "parts": [{"text": str(m.get("content", ""))}]})
    return contents


def thinking_config(model: str, effort: str) -> dict | None:
    if model.startswith("gemini-2.5"):
        return {"thinking_budget": 0} if effort == "low" else None    # 0 turns thinking off on 2.5 Flash / Flash-Lite
    if model.startswith("gemini-3"):
        return {"thinking_level": effort.upper()}                      # LOW / MEDIUM / HIGH
    return None


def build_request(messages, *, system, schema, tools, model, effort, max_output_tokens, timeout_s=30.0) -> dict:
    config: dict = {"max_output_tokens": max_output_tokens,
                    # timeout in milliseconds; attempts=1: no SDK retries, retries are call_model's job
                    "http_options": {"timeout": int(timeout_s * 1000), "retry_options": {"attempts": 1}}}
    if system:
        config["system_instruction"] = system
    if schema is not None:
        config["response_mime_type"] = "application/json"
        config["response_json_schema"] = json_schema(schema)
    if tools:
        config["tools"] = [{"function_declarations": [
            {"name": t["name"], "description": t.get("description", ""), "parameters_json_schema": t["parameters"]}
            for t in tools]}]
    think = thinking_config(model, effort)
    if think:
        config["thinking_config"] = think
    return {"model": model, "contents": convert_messages(messages), "config": config}


def _name(value) -> str:
    return getattr(value, "name", None) or (str(value) if value is not None else "")


def to_result(resp, model: str, latency_ms: int):
    from support.llm import ModelResult, ToolCall, Usage

    candidates = getattr(resp, "candidates", None) or []
    block = _name(getattr(getattr(resp, "prompt_feedback", None), "block_reason", None))
    finish = _name(getattr(candidates[0], "finish_reason", None)) if candidates else ""
    calls = [ToolCall(id=c.id or f"gemini-call-{i}", name=c.name, args=dict(c.args or {}))
             for i, c in enumerate(getattr(resp, "function_calls", None) or [])]
    if not candidates:
        status = "refusal" if block else "error"
    elif finish == "MAX_TOKENS":
        status = "truncated"
    elif finish in REFUSAL_REASONS:
        status = "refusal"
    elif finish == "STOP":
        status = "tool_call" if calls else "ok"
    else:
        status = "error"
    try:
        text = resp.text or ""
    except (ValueError, AttributeError):
        text = ""
    u = getattr(resp, "usage_metadata", None)
    cached = (getattr(u, "cached_content_token_count", 0) or 0) if u else 0
    usage = Usage(
        input_tokens=max(0, ((getattr(u, "prompt_token_count", 0) or 0) if u else 0) - cached),
        output_tokens=((getattr(u, "candidates_token_count", 0) or 0) + (getattr(u, "thoughts_token_count", 0) or 0)) if u else 0,
        cached_input_tokens=cached,
    )
    stop = finish or (f"blocked:{block}" if block else "")
    return ModelResult(status=status, text=text, tool_calls=calls, usage=usage, latency_ms=latency_ms,
                       provider="gemini", model=model, stop_reason=stop,
                       error=(stop or "no_candidates") if status == "error" else None,
                       raw={"finish_reason": finish, "block_reason": block})


def complete(messages, *, system, schema, tools, model, effort, max_output_tokens, timeout_s, api_key):
    from support.llm import ModelResult

    try:
        from google import genai
    except ImportError:
        return ModelResult(status="error", provider="gemini", model=model,
                           error="sdk_missing: run `uv sync --extra gemini`")
    req = build_request(messages, system=system, schema=schema, tools=tools, model=model, effort=effort,
                        max_output_tokens=max_output_tokens, timeout_s=timeout_s)
    started = time.perf_counter()
    try:
        client = genai.Client(api_key=api_key, http_options={"retry_options": {"attempts": 1}})
        resp = client.models.generate_content(**req)
    except Exception as exc:  # noqa: BLE001 - every provider failure becomes a status
        return ModelResult(status="error", provider="gemini", model=model, error=error_code(exc),
                           latency_ms=int((time.perf_counter() - started) * 1000),
                           raw={"exception": type(exc).__name__, "message": str(exc)[:300]})
    return to_result(resp, model, int((time.perf_counter() - started) * 1000))
