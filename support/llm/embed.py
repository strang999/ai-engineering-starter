"""embed(): text -> vectors, one call for every route (lesson 10).

    from support.llm import embed
    r = embed(["Скільки днів на повернення?"], kind="query")
    r.vectors[0][:3], r.model, r.dim

Routes (AIEZ_EMBED, default: follows AIEZ_PROVIDER):
  mock    ready-made vectors from data/kb_vectors.npz, made by the real multilingual-e5-small model for the
          course texts (the demo knowledge base and the course questions). A text that is not there: error
          `mock_no_vector`. Free, offline, no install.
  local   multilingual-e5-small on your computer: `uv sync --extra rag-local` (about 470 MB of model).
  openai  text-embedding-3-small. Needs OPENAI_API_KEY and `uv sync --extra openai`.
  gemini  gemini-embedding-2. Needs GEMINI_API_KEY and `uv sync --extra gemini`.
Anthropic has no embeddings API: with AIEZ_PROVIDER=anthropic set AIEZ_EMBED to one of the routes above.

UNTESTED against the live APIs (no key was used); the request shape is checked offline, docs/VERIFIED.md.
Vectors from different routes live in different spaces: never compare a query from one with a base from another.
"""

from __future__ import annotations

import os
import time
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Literal

import numpy as np

from support import config
from support.config import DATA_DIR

ROUTES = ("mock", "local", "openai", "gemini")
DEFAULT_EMBED_MODELS = {
    "mock": "e5-small-fixtures",
    "local": "intfloat/multilingual-e5-small",
    "openai": "text-embedding-3-small",
    "gemini": "gemini-embedding-2",
}
# USD per 1M input tokens (docs/VERIFIED.md, checked 2026-10-24)
EMBED_PRICE_PER_MTOK = {"openai": 0.02, "gemini": 0.20, "local": 0.0, "mock": 0.0}
E5_PREFIX = {"query": "query: ", "passage": "passage: "}     # required by the e5 model family
VECTORS_PATH = DATA_DIR / "kb_vectors.npz"


@dataclass
class EmbedResult:
    status: Literal["ok", "error"]
    vectors: list[list[float]] = field(default_factory=list)
    route: str = "mock"
    model: str = ""
    dim: int = 0
    input_tokens: int = 0           # estimate (characters / 4) where the provider does not report it
    cost_usd: float = 0.0
    latency_ms: int = 0
    error: str | None = None


_collector: ContextVar[list | None] = ContextVar("aiez_embed_collector", default=None)


@contextmanager
def collect_embeds():
    """Collect every EmbedResult made inside the block (run_evals uses it for the embeddings line)."""
    bucket: list[EmbedResult] = []
    token = _collector.set(bucket)
    try:
        yield bucket
    finally:
        _collector.reset(token)


def route() -> str:
    """AIEZ_EMBED if set, else the route that matches AIEZ_PROVIDER (anthropic has none)."""
    chosen = (os.environ.get("AIEZ_EMBED") or "").strip().lower()
    if chosen:
        return chosen
    provider = config.current_provider()
    return provider if provider in ("mock", "openai", "gemini") else "anthropic"


@lru_cache(maxsize=1)
def _fixtures() -> dict[str, np.ndarray]:
    if not VECTORS_PATH.is_file():
        return {}
    data = np.load(VECTORS_PATH, allow_pickle=False)
    return {str(t): v for t, v in zip(data["texts"], data["vecs"])}


def _tokens(texts: list[str]) -> int:
    return max(1, sum(len(t) for t in texts) // 4)


def _fail(r: str, model: str, error: str) -> EmbedResult:
    return EmbedResult(status="error", route=r, model=model, error=error)


def _mock(texts: list[str], kind: str) -> EmbedResult:
    table, vectors, missing = _fixtures(), [], []
    for t in texts:
        v = table.get(E5_PREFIX[kind] + t)
        if v is None:
            missing.append(t)
        else:
            vectors.append(v.tolist())
    if missing:
        shown = missing[0][:60].replace("\n", " ")
        return _fail("mock", DEFAULT_EMBED_MODELS["mock"],
                     f"mock_no_vector: у mock немає готового вектора для «{shown}» ({len(missing)} з {len(texts)} текстів). "
                     "Mock знає тільки тексти курсу. Для своїх текстів: uv sync --extra rag-local і AIEZ_EMBED=local, "
                     "або ключ OpenAI/Gemini і AIEZ_EMBED=openai|gemini")
    return EmbedResult(status="ok", vectors=vectors, route="mock", model=DEFAULT_EMBED_MODELS["mock"],
                       dim=len(vectors[0]) if vectors else 0, input_tokens=_tokens(texts), latency_ms=5)


@lru_cache(maxsize=1)
def _local_model():
    from sentence_transformers import SentenceTransformer       # imported only when you pick the route
    return SentenceTransformer(DEFAULT_EMBED_MODELS["local"])


def _local(texts: list[str], kind: str) -> EmbedResult:
    try:
        model = _local_model()
    except ImportError:
        return _fail("local", DEFAULT_EMBED_MODELS["local"],
                     "not_installed: uv sync --extra rag-local (бібліотека + модель ~470 МБ)")
    vecs = model.encode([E5_PREFIX[kind] + t for t in texts], normalize_embeddings=True)
    return EmbedResult(status="ok", vectors=[v.tolist() for v in vecs], route="local",
                       model=DEFAULT_EMBED_MODELS["local"], dim=int(vecs.shape[1]), input_tokens=_tokens(texts))


def _openai(texts: list[str], kind: str, model: str, timeout_s: float) -> EmbedResult:
    from support.llm._common import error_code
    key = config.api_key("openai")
    if not key:
        return _fail("openai", model, "no_api_key: put OPENAI_API_KEY in .env (never in code)")
    try:
        from openai import OpenAI
    except ImportError:
        return _fail("openai", model, "not_installed: uv sync --extra openai")
    try:
        resp = OpenAI(api_key=key, max_retries=0, timeout=timeout_s).embeddings.create(model=model, input=texts)
    except Exception as exc:                                   # the SDK has its own exception tree
        return _fail("openai", model, error_code(exc))
    used = getattr(getattr(resp, "usage", None), "prompt_tokens", None) or _tokens(texts)
    return EmbedResult(status="ok", vectors=[list(d.embedding) for d in resp.data], route="openai", model=model,
                       dim=len(resp.data[0].embedding), input_tokens=used)


def _gemini(texts: list[str], kind: str, model: str, timeout_s: float) -> EmbedResult:
    from support.llm._common import error_code
    key = config.api_key("gemini")
    if not key:
        return _fail("gemini", model, "no_api_key: put GEMINI_API_KEY in .env (never in code)")
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        return _fail("gemini", model, "not_installed: uv sync --extra gemini")
    task = "RETRIEVAL_QUERY" if kind == "query" else "RETRIEVAL_DOCUMENT"
    try:
        client = genai.Client(api_key=key, http_options=types.HttpOptions(timeout=int(timeout_s * 1000)))
        resp = client.models.embed_content(model=model, contents=texts,
                                           config=types.EmbedContentConfig(task_type=task))
    except Exception as exc:
        return _fail("gemini", model, error_code(exc))
    vectors = [list(e.values or []) for e in resp.embeddings]
    return EmbedResult(status="ok", vectors=vectors, route="gemini", model=model, dim=len(vectors[0]),
                       input_tokens=_tokens(texts))


def embed(texts: list[str], *, kind: Literal["query", "passage"] = "passage",
          model: str | None = None, timeout_s: float = 30.0) -> EmbedResult:
    """Never raises for provider problems: returns status="error" with `error`.
    Raises ValueError only for programmer errors (empty list, empty text, bad kind)."""
    if not isinstance(texts, list) or not texts or any(not isinstance(t, str) or not t.strip() for t in texts):
        raise ValueError("texts must be a non-empty list of non-empty strings")
    if kind not in E5_PREFIX:
        raise ValueError("kind must be 'query' or 'passage'")
    chosen = route()
    started = time.perf_counter()
    if chosen == "mock":
        result = _mock(texts, kind)
    elif chosen == "local":
        result = _local(texts, kind)
    elif chosen in ("openai", "gemini"):
        name = model or DEFAULT_EMBED_MODELS[chosen]
        result = (_openai if chosen == "openai" else _gemini)(texts, kind, name, timeout_s)
    elif chosen == "anthropic":
        result = _fail("anthropic", "", "no_embeddings: у Anthropic нема API ембедингів; задай AIEZ_EMBED=local, "
                                          "openai або gemini")
    else:
        result = _fail(chosen, "", f"unknown_route: {chosen!r}; use one of {', '.join(ROUTES)}")
    if result.status == "ok":
        result.cost_usd = result.input_tokens / 1_000_000 * EMBED_PRICE_PER_MTOK.get(result.route, 0.0)
        result.latency_ms = result.latency_ms or int((time.perf_counter() - started) * 1000)
    bucket = _collector.get()
    if bucket is not None:
        bucket.append(result)
    return result
