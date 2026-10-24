"""What the model sees: tokens (lesson 5).

    uv run python -m support.tokens "Хочу повернути гроші за замовлення 1042"

Exact tokens need the optional tokenizer: `uv sync --extra tokens` (tiktoken, o200k_base;
the first run downloads the vocabulary file once). Without it, or offline, the command
prints the same rough estimate the mock uses: characters / 4.
"""

from __future__ import annotations

import math
import sys

from support import config


def exact_tokens(text: str) -> list[str] | None:
    try:
        import tiktoken
        enc = tiktoken.get_encoding("o200k_base")
    except Exception:          # not installed, or no network for the first download
        return None
    return [enc.decode([i]) for i in enc.encode(text)]


def main(argv: list[str]) -> int:
    config.setup_console()
    text = " ".join(argv) if argv else "Хочу повернути гроші за замовлення 1042"
    print(f"Текст: {text}")
    pieces = exact_tokens(text)
    if pieces is None:
        print("Токенайзер: нема, це оцінка (символи / 4, як у mock). Точно: uv sync --extra tokens")
        print(f"Символів: {len(text)} · байтів UTF-8: {len(text.encode('utf-8'))} · "
              f"оцінка токенів: {max(1, math.ceil(len(text) / 4))}")
        return 0
    print("Токенайзер: o200k_base (tiktoken)")
    print(f"Токенів: {len(pieces)}")
    print("Шматки: " + "|".join(pieces))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
