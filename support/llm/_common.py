"""Helpers shared by the live adapters: JSON schemas and error codes."""

from __future__ import annotations

import copy


def json_schema(model: type) -> dict:
    """Pydantic model -> closed JSON schema with $refs inlined and titles removed.

    Inlining keeps the schema inside what every provider's structured output accepts."""
    schema = model.model_json_schema()
    defs = schema.pop("$defs", {})

    def walk(node):
        if isinstance(node, dict):
            if "$ref" in node:
                name = node["$ref"].split("/")[-1]
                return walk(copy.deepcopy(defs[name]))
            out = {}
            for key, value in node.items():
                if key in ("title", "default"):
                    continue
                # "properties" maps FIELD NAMES to schemas: keep every name, walk only the schemas
                out[key] = {f: walk(v) for f, v in value.items()} if key == "properties" else walk(value)
            if out.get("type") == "object":
                out.setdefault("additionalProperties", False)
                out["required"] = list(out.get("properties", {}))
            return out
        if isinstance(node, list):
            return [walk(x) for x in node]
        return node

    return walk(schema)


def error_code(exc: BaseException) -> str:
    """Map an SDK exception to the contract's error codes without importing any SDK."""
    name = type(exc).__name__
    status = getattr(exc, "status_code", None)
    if status is None and isinstance(getattr(exc, "code", None), int):
        status = exc.code                     # google-genai APIError.code
    text = str(exc).lower()
    if "timeout" in name.lower() or "deadline" in name.lower():
        return "timeout"
    # spend caps come back as 402, 400 or 429 depending on the provider: match them BEFORE rate_limit,
    # because a 429 rate limit is retried and a spend cap must never be (no money appears in a second)
    if status == 402 or any(s in text for s in (
            "insufficient_quota", "credit balance", "credit_balance", "billing",
            "spend limit", "spend_limit", "spending cap", "usage limits", "usage_limit")):
        return "spend_cap"
    if name == "RateLimitError" or status == 429:
        return "rate_limit"
    if name in ("AuthenticationError", "PermissionDeniedError") or status in (401, 403):
        return "auth"
    if "connection" in name.lower():
        return "connection"
    if isinstance(status, int) and status >= 500:
        return "server_error"
    if isinstance(status, int) and 400 <= status < 500:
        return "bad_request"
    return "error"
