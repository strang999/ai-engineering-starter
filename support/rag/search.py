"""Lesson 10: three ways to search the chunks, and the RRF that merges two of them.

    from support.rag import search_kb
    [c.id for c in search_kb("Скільки днів є, щоб повернути товар?", k=3, mode="hybrid")]
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import numpy as np
from rank_bm25 import BM25Okapi

from support.llm.embed import EmbedResult, embed
from support.rag.chunk import DEFAULT_MAX_CHARS, Chunk, load_chunks

MODES = ("keyword", "vector", "hybrid")
RRF_K = 60       # Elastic's default rank constant


class SearchError(Exception):
    """The search could not run (no embeddings, ...). The text is for the learner."""


def tokens(text: str) -> list[str]:
    """Words cut to their first 6 letters: crude, but Ukrainian endings mostly merge («посилку» = «посилка»)."""
    return [w[:6] for w in re.findall(r"\w+", text.lower())]


@dataclass
class Index:
    chunks: list[Chunk]
    bm25: BM25Okapi
    max_chars: int = DEFAULT_MAX_CHARS
    _vecs: np.ndarray | None = field(default=None, repr=False)
    embed_route: str | None = None

    def doc_vectors(self) -> np.ndarray:
        """Embed every chunk once, on first use (the title goes into the text)."""
        if self._vecs is None:
            result = embed([c.passage for c in self.chunks], kind="passage")
            self._vecs = _matrix(result)
            self.embed_route = result.route
        return self._vecs


def _matrix(result: EmbedResult) -> np.ndarray:
    if result.status != "ok":
        raise SearchError(result.error or "embed failed")
    m = np.array(result.vectors, dtype=np.float32)
    return m / np.linalg.norm(m, axis=1, keepdims=True)           # unit length: dot product = cosine


def build_index(kb_dir: Path | None = None, max_chars: int = DEFAULT_MAX_CHARS) -> Index:
    chunks = load_chunks(kb_dir, max_chars)
    return Index(chunks, BM25Okapi([tokens(c.passage) for c in chunks]), max_chars)


@lru_cache(maxsize=8)
def _cached(kb_dir: str | None, max_chars: int, route: str) -> Index:
    """One index per (folder, chunk size, embedding route): switching the route never reuses old vectors."""
    return build_index(Path(kb_dir) if kb_dir else None, max_chars)


def get_index(kb_dir: Path | None = None, max_chars: int = DEFAULT_MAX_CHARS) -> Index:
    from support.llm.embed import route
    return _cached(str(kb_dir) if kb_dir else None, max_chars, route())


def keyword_search(index: Index, question: str, k: int = 3) -> list[Chunk]:
    scores = index.bm25.get_scores(tokens(question))
    top = scores.argsort()[::-1][:k]
    return [index.chunks[i] for i in top if scores[i] > 0]      # no shared word: no result, not a random one


def vector_search(index: Index, question: str, k: int = 3) -> list[Chunk]:
    q = _matrix(embed([question], kind="query"))[0]
    scores = index.doc_vectors() @ q
    top = scores.argsort()[::-1][:k]
    return [index.chunks[i] for i in top]


def hybrid_search(index: Index, question: str, k: int = 3) -> list[Chunk]:
    """Reciprocal rank fusion: each list gives a chunk 1 / (60 + place); the sums are sorted."""
    fused: dict[str, float] = {}
    for ranked in (keyword_search(index, question, 20), vector_search(index, question, 20)):
        for rank, chunk in enumerate(ranked, start=1):
            fused[chunk.id] = fused.get(chunk.id, 0) + 1 / (RRF_K + rank)
    by_id = {c.id: c for c in index.chunks}
    return [by_id[cid] for cid in sorted(fused, key=lambda cid: fused[cid], reverse=True)[:k]]


def search_kb(question: str, k: int = 3, mode: str = "hybrid", *, index: Index | None = None) -> list[Chunk]:
    """The k best chunks of the knowledge base for a question. An empty question searches nothing.

    Raises SearchError when the mode needs embeddings and they are not available (see support.llm.embed)."""
    if mode not in MODES:
        raise ValueError(f"mode must be one of {', '.join(MODES)}")
    if not question.strip():
        return []
    index = index or get_index()
    return {"keyword": keyword_search, "vector": vector_search, "hybrid": hybrid_search}[mode](index, question, k)
