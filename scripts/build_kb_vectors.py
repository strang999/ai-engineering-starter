"""Rebuild data/kb_vectors.npz: real multilingual-e5-small vectors for the course texts.

The mock embedding route (support/llm/embed.py) reads this file, so lesson 10 runs offline without a
470 MB model. Run it again after you change data/kb/*.md, evals/cases.jsonl or the lists below:

    uv sync --extra rag-local
    uv run python scripts/build_kb_vectors.py

Keys are the exact strings the model saw, including the `query: ` / `passage: ` prefix.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from support.llm.embed import DEFAULT_EMBED_MODELS, E5_PREFIX, VECTORS_PATH  # noqa: E402
from support.rag.chunk import KB_DIR, load_chunks  # noqa: E402

CHUNK_SIZES = (800, 200, 120)        # the default, and the two the lesson tries
# questions the lesson asks outside cases.jsonl
EXTRA_QUERIES = [
    "що означає помилка E-217", "E-218", "E-217", "скільки днів на повернення", "return policy",
    "how long do I have to return an item", "коли повернуть гроші", "повернення товару",
    "Чи можна повернути крем, якщо я його вже відкрила", "Чи можна додати промокод після оплати",
]


def case_questions() -> list[str]:
    rows = [json.loads(line) for line in (ROOT / "evals" / "cases.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    return [r["input"]["question"] for r in rows if r.get("kind") in ("retrieval", "answer")]


def main() -> int:
    from sentence_transformers import SentenceTransformer

    texts: list[str] = []
    for size in CHUNK_SIZES:
        texts += [E5_PREFIX["passage"] + c.passage for c in load_chunks(KB_DIR, size)]
    texts += [E5_PREFIX["passage"] + c.passage for c in load_chunks(KB_DIR / "archive", 800)]
    texts += [E5_PREFIX["query"] + q for q in case_questions() + EXTRA_QUERIES]
    texts = sorted(set(texts))
    model = SentenceTransformer(DEFAULT_EMBED_MODELS["local"])
    vecs = model.encode(texts, normalize_embeddings=True).astype(np.float32)
    np.savez_compressed(VECTORS_PATH, texts=np.array(texts), vecs=vecs)
    print(f"{len(texts)} texts, {vecs.shape[1]} dims -> {VECTORS_PATH.relative_to(ROOT)} "
          f"({VECTORS_PATH.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
