"""run_evals for lesson 10: kind=retrieval (hit@k, no model) and kind=answer (retrieve, ask, check).

    uv run python -m support.evals --kind retrieval --mode all --tag happy
    uv run python -m support.evals --kind retrieval --mode vector --chunk-size 200
    uv run python -m support.evals --kind answer
"""

from __future__ import annotations

import time
from dataclasses import asdict
from contextlib import nullcontext

from support import config
from support.evals import (CaseResult, compare, new_run_id, percentile, save_run, show_path)
from support.llm import collect_calls
from support.llm.embed import collect_embeds, route as embed_route
from support.llm.mock import use_scenario
from support.prices import estimate_usd
from support.rag import RAG_PROMPT_CHARS, SearchError, answer_from_kb, get_index, search_kb

MODES = ("keyword", "vector", "hybrid")


def run_retrieval_case(case: dict, mode: str, k: int, index) -> CaseResult:
    """hit@k: the quote that holds the answer must be inside one of the top-k chunks (not a chunk id:
    ids change every time you re-chunk)."""
    quote = case["expect"]["evidence"]
    started = time.perf_counter()
    error, ids, rank = None, [], None
    try:
        chunks = search_kb(case["input"]["question"], k, mode, index=index)
        ids = [c.id for c in chunks]
        rank = next((i for i, c in enumerate(chunks, start=1) if quote in c.text), None)
    except SearchError as exc:
        error = str(exc)
    problems = [error] if error else ([] if rank else [f"цитата не в top-{k}: знайшло {', '.join(ids) or 'нічого'}"])
    return CaseResult(id=case["id"], tags=case.get("tags", []), passed=not problems, problems=problems,
                      got={"rank": rank, "retrieved": ids, "evidence": quote if rank else None, "error": error},
                      latency_ms=int((time.perf_counter() - started) * 1000))


def run_answer_case(case: dict, mode: str, k: int, index) -> CaseResult:
    scenario = case.get("mock")
    # a "mock" case tests OUR code with a simulated failure: run it on mock even in a live run
    force_mock = config.use_model("mock", "mock-1") if scenario else nullcontext()
    with force_mock, use_scenario(scenario), collect_calls() as calls:
        result = answer_from_kb(case["input"]["question"], k, mode, index=index)
    got = result.model_dump()
    quote = case["expect"].get("evidence")
    if quote is not None:               # the cited chunks must contain the quote, not just exist
        cited = " ".join(c.text for c in index.chunks if c.id in result.sources)
        got["evidence"] = quote if quote in cited else None
    problems = compare(case["expect"], got, kind="answer")
    return CaseResult(
        id=case["id"], tags=case.get("tags", []), passed=not problems, problems=problems, got=got,
        cost_usd=sum(c.cost_usd for c in calls), latency_ms=sum(c.latency_ms for c in calls),
        calls=[{"status": c.status, "error": c.error, "stop_reason": c.stop_reason, "model": c.model,
                "usage": asdict(c.usage), "text": c.text[:2000],
                "price_known": (c.raw or {}).get("price_known", True)} for c in calls])


def evaluate_rag(cases: list[dict], *, kind: str, mode: str, k: int, index) -> list[CaseResult]:
    run = run_retrieval_case if kind == "retrieval" else run_answer_case
    return [run(c, mode, k, index) for c in cases]


def hits(results: list[CaseResult], k: int) -> tuple[int, int]:
    """(hit@1, hit@k) over retrieval results."""
    ranks = [r.got.get("rank") for r in results]
    return sum(1 for x in ranks if x == 1), sum(1 for x in ranks if x is not None and x <= k)


def report_rag(results: list[CaseResult], *, run_id: str, kind: str, mode: str, k: int, index, split: str,
               provider: str, model: str, embeds: list, runs_label: str = "") -> list[str]:
    n = len(results)
    passed = sum(r.passed for r in results)
    pct = f"{100 * passed / n:.1f}%" if n else "n/a"
    route = embeds[0].route if embeds else embed_route()
    head = (f"run {run_id} · kind={kind} · mode {mode} · k {k} · {len(index.chunks)} chunks (до {index.max_chars} знаків)"
            f" · embeddings {route if mode != 'keyword' else 'не потрібні'}")
    if kind == "answer":
        head += f" · provider={provider} model={model}"
    lines = [head + f" · cases {n} ({split})"]
    if kind == "retrieval":
        h1, hk = hits(results, k)
        lines.append(f"pass {passed}/{n} ({pct}) · hit@1 {h1}/{n} · hit@{k} {hk}/{n}")
        emb_cost = sum(e.cost_usd for e in embeds)
        emb_tokens = sum(e.input_tokens for e in embeds)
        lines.append(f"embeddings {len(embeds)} calls · ~{emb_tokens} tokens · ${emb_cost:.5f}"
                     + (" (mock)" if route == "mock" and embeds else ""))
        lat = [r.latency_ms for r in results]
        lines.append(f"latency p50 {percentile(lat, 50)} ms · p95 {percentile(lat, 95)} ms")
    else:
        answered = sum(1 for r in results if r.got.get("found") is True)
        refused = sum(1 for r in results if r.got.get("found") is False)
        review = sum(1 for r in results if r.got.get("status") == "needs_review")
        errors = sum(1 for r in results if r.got.get("status") == "error")
        lines.append(f"pass {passed}/{n} ({pct}) · answered {answered} · refused {refused} · needs_review {review}"
                     + (f" · errors {errors}" if errors else ""))
        cost = sum(r.cost_usd for r in results)
        per_success = cost / passed if passed else 0.0
        lines.append(f"cost ${cost:.4f}" + (" (simulated)" if provider == "mock" else "")
                     + f" · per case ${cost / n if n else 0.0:.4f} · per success ${per_success:.4f}")
        lat = [r.latency_ms for r in results if r.calls]
        lines.append(f"latency p50 {percentile(lat, 50)} ms · p95 {percentile(lat, 95)} ms")
        tin = sum(c["usage"]["input_tokens"] for r in results for c in r.calls)
        tout = sum(c["usage"]["output_tokens"] for r in results for c in r.calls)
        lines.append(f"tokens in {tin} · out {tout}")
        first = next((r.got["error"] for r in results if r.got.get("status") == "error"), None)
        if first:
            lines.append(f"errors {errors}/{n} (first: {first})")
    for r in sorted(results, key=lambda r: r.id):
        if not r.passed:
            tag = f" [{r.tags[0]}]" if r.tags else ""
            lines.append(f"FAIL {r.id}{tag} {'; '.join(r.problems)}")
    return lines


def mode_table(rows: list[tuple[str, list[CaseResult]]], k: int) -> list[str]:
    out = [f"mode      hit@1    hit@{k}"]
    for mode, results in rows:
        n = len(results)
        h1, hk = hits(results, k)
        out.append(f"{mode:<9} {h1:>3}/{n:<4} {hk:>3}/{n:<4}".rstrip())
    return out


def dry_run_answer(cases: list[dict], configs: list[tuple[str, str]], *, k: int, index) -> list[str]:
    """Count calls and estimate cost. Calls nothing. The prompt is the fixed text plus k average chunks."""
    avg = sum(len(c.text) for c in index.chunks) / max(1, len(index.chunks))
    tin_call = int((RAG_PROMPT_CHARS + k * avg) / 4) + 40
    n_calls = sum(1 for c in cases if c["input"]["question"].strip())
    lines = [f"dry run · {len(cases)} cases · {n_calls} answer calls per config + 1 embedding call per question"]
    total = 0.0
    for provider, model in configs:
        if provider == "mock":
            price = "$0.0000 (mock)"
        else:
            one = estimate_usd(model, tin_call, 150)
            price = "price unknown: add it to support/prices.py" if one is None else f"≈ ${one * n_calls:.4f}"
            total += 0.0 if one is None else one * n_calls
            if not config.api_key(provider):
                price += " · NO KEY in .env"
        lines.append(f"{provider}:{model} · ~{tin_call * n_calls} in / ~{150 * n_calls} out tokens · {price}")
    lines.append(f"total ≈ ${total:.4f} (output assumed 150 tokens per call; embeddings not counted) · nothing was called")
    return lines


def main_rag(args, cases: list[dict], configs: list[tuple[str, str]]) -> int:
    """Called by support.evals.__main__ for --kind retrieval | answer."""
    import sys

    from support.rag.search import build_index

    run_id = new_run_id()
    if args.kind == "answer" and args.baseline:
        print("--baseline: для kind=answer нема правил без моделі; для пошуку є --kind retrieval --baseline (за словами).")
        return 2
    if args.kind == "retrieval" and args.baseline:
        args.mode = "keyword"
    from pathlib import Path
    index = build_index(Path(args.kb) if args.kb else None, args.chunk_size)
    if args.dry_run:
        if args.kind == "retrieval":
            print(f"dry run · {len(cases)} cases · retrieval: 0 model calls, "
                  f"{0 if args.mode == 'keyword' else len(index.chunks) + len(cases)} texts to embed · nothing was called")
        else:
            print("\n".join(dry_run_answer(cases, configs, k=args.k, index=index)))
        return 0

    modes = list(MODES) if args.mode == "all" else [args.mode]
    if args.mode == "all" and args.kind != "retrieval":
        print("--mode all працює тільки з --kind retrieval.")
        return 2
    table, provider, model = [], configs[0][0], configs[0][1]
    for mode in modes:
        with collect_embeds() as embeds, config.use_model(provider, model, args.effort):
            results = evaluate_rag(cases, kind=args.kind, mode=mode, k=args.k, index=index)
        lines = report_rag(results, run_id=run_id, kind=args.kind, mode=mode, k=args.k, index=index,
                           split=args.split, provider=provider, model=model, embeds=embeds)
        print("\n".join(lines))
        meta = {"run_id": run_id, "kind": args.kind, "mode": mode, "k": args.k, "chunk_size": args.chunk_size,
                "provider": provider, "model": model, "split": args.split, "tag": args.tag,
                "label": (f"{args.label}-" if args.label else "") + f"{args.kind}-{mode}-k{args.k}-c{args.chunk_size}"}
        print(f"saved {show_path(save_run(results, meta, lines))}")
        table.append((mode, results))
    if len(table) > 1:
        print()
        print("\n".join(mode_table(table, args.k)))
    return 0
