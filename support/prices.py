"""Model prices: the only place in the repo with a number per token.

USD per 1 million tokens, standard (non-batch) tier, read on the provider's own
pricing page on `checked_at`. Re-check before you trust a cost report: prices change.
Sources and caveats: docs/VERIFIED.md.
"""

from __future__ import annotations

from typing import NamedTuple


class Price(NamedTuple):
    input_per_mtok: float
    output_per_mtok: float
    cached_per_mtok: float
    checked_at: str
    url: str
    cache_write_per_mtok: float | None = None    # None = 1.25 x input (Anthropic's 5-minute cache write)


ANTHROPIC = "https://platform.claude.com/docs/en/about-claude/pricing"
OPENAI = "https://developers.openai.com/api/docs/pricing"
GEMINI = "https://ai.google.dev/gemini-api/docs/pricing"

PRICES: dict[str, Price] = {
    "mock-1": Price(0.0, 0.0, 0.0, "2026-10-24", "support/llm/mock.py"),
    # Anthropic. Haiku 5.5 rates are for prompts up to 100,000 tokens (see LONG_PROMPT below).
    "claude-haiku-5-5": Price(0.10, 0.50, 0.01, "2026-10-24", ANTHROPIC),
    "claude-sonnet-5-5": Price(2.00, 10.00, 0.10, "2026-10-24", ANTHROPIC),
    "claude-opus-5-5": Price(4.00, 20.00, 0.20, "2026-10-24", ANTHROPIC),
    # OpenAI, prompts up to 272K tokens.
    "gpt-6-luna": Price(0.10, 0.50, 0.01, "2026-10-24", OPENAI),
    "gpt-5.6-luna": Price(0.20, 1.20, 0.02, "2026-10-24", OPENAI),
    # Google Gemini, paid tier (a free tier exists; its data may be used to improve Google products).
    "gemini-2.5-flash-lite": Price(0.10, 0.40, 0.01, "2026-10-24", GEMINI),
    "gemini-3.1-flash-lite": Price(0.25, 1.50, 0.025, "2026-10-24", GEMINI),
}

# model -> (prompt tokens above which another price applies, that price)
LONG_PROMPT: dict[str, tuple[int, Price]] = {
    "claude-haiku-5-5": (100_000, Price(0.50, 2.50, 0.05, "2026-10-24", ANTHROPIC)),
}


def price_for(model: str, prompt_tokens: int = 0) -> Price | None:
    long = LONG_PROMPT.get(model)
    if long and prompt_tokens > long[0]:
        return long[1]
    return PRICES.get(model)


CACHE_WRITE_FACTOR = 1.25      # Anthropic: writing a prompt to the 5-minute cache costs 1.25x the input price


def estimate_usd(model: str, input_tokens: int, output_tokens: int, cached_input_tokens: int = 0,
                 *, cache_write_tokens: int = 0) -> float | None:
    """Cost of ONE request. None if we have no price for this model: never pretend it is free.

    Long-prompt tiers (LONG_PROMPT) apply per request: never pass the sum of many calls here,
    price one call and multiply. `cache_write_tokens` is the part of `input_tokens` written to the cache."""
    price = price_for(model, input_tokens + cached_input_tokens)
    if price is None:
        return None
    write = price.cache_write_per_mtok
    if write is None:
        write = price.input_per_mtok * CACHE_WRITE_FACTOR
    return (input_tokens * price.input_per_mtok
            + cache_write_tokens * (write - price.input_per_mtok)
            + cached_input_tokens * price.cached_per_mtok
            + output_tokens * price.output_per_mtok) / 1_000_000
