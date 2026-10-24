"""run_evals: one eval set (evals/cases.jsonl) and one command for the whole course.

    uv run python -m support.evals --baseline
    uv run python -m support.evals --baseline --tag own      # only your cases from evals/own.jsonl
    uv run python -m support.evals add-case "текст" --category доставка
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from contextlib import nullcontext
from pathlib import Path

from support import config
from support.card import CARD_SYSTEM, build_card_prompt, make_card
from support.config import ROOT
from support.contract import Ticket
from support.llm import collect_calls
from support.llm.mock import use_scenario
from support.prices import estimate_usd
from support.evals.own import load_own_cases, read_jsonl
from support.rules import make_card_rules

CASES_PATH = ROOT / "evals" / "cases.jsonl"
CASE_CREATED_AT = "2026-10-24T12:00:00+03:00"


def load_cases(path: Path | None = None, *, own: bool = False) -> list[dict]:
    """The course's reference set, evals/cases.jsonl. Rows tagged "own" are skipped, so the tests
    never see a learner's cases. own=True (what run_evals uses): every row plus evals/own.jsonl.

    Raises ValueError with a readable message (bad JSON, a duplicate id, an unreadable encoding)."""
    rows = read_jsonl(path or CASES_PATH)
    if own:
        rows += load_own_cases()
    else:
        rows = [r for r in rows if "own" not in r.get("tags", [])]
    ids = [r["id"] for r in rows]
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    if dupes:
        raise ValueError(f"id кейсів повторюються: {', '.join(dupes)} (свої кейси: own-01, own-02, …)")
    return rows


def select(cases: list[dict], *, kind: str = "card", split: str = "dev", tag: str | None = None) -> list[dict]:
    return [c for c in cases
            if c.get("kind") == kind and c.get("split", "dev") == split
            and (tag is None or tag in c.get("tags", []))]


def runs_dir() -> Path:
    return Path(os.environ.get("AIEZ_RUNS_DIR") or ROOT / "runs")


def ticket_from(case: dict) -> Ticket:
    inp = case["input"]
    return Ticket(ticket_id=inp.get("ticket_id", "T-CASE"), customer_id=inp.get("customer_id", "c-17"),
                  text=inp["text"], created_at=inp.get("created_at", CASE_CREATED_AT))


# --- comparing one result with `expect` ---------------------------------------

TEXT_FIELD = {"card": "draft_reply", "answer": "answer", "agent": "text"}


def _fmt(value) -> str:
    if value is None:
        return "null"
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


def compare(expect: dict, got: dict, *, kind: str = "card") -> list[str]:
    """Listed keys must match exactly; unlisted keys are not checked."""
    problems = []
    text = got.get(TEXT_FIELD.get(kind, "text")) or ""
    for key, want in expect.items():
        if key == "must_contain":
            for part in [want] if isinstance(want, str) else want:
                if part.lower() not in text.lower():
                    problems.append(f"must_contain: {part!r} not in {_fmt(text or None)}")
        elif key == "must_not_contain":
            for part in [want] if isinstance(want, str) else want:
                if part.lower() in text.lower():
                    problems.append(f"must_not_contain: {part!r} found")
        elif key.endswith("_in"):
            name = key[:-3]
            if got.get(name) not in want:
                problems.append(f"{name}: expected one of {_fmt(want)}, got {_fmt(got.get(name))}")
        elif got.get(key) != want:
            shown = "не знаю" if key == "category" and got.get(key) is None else _fmt(got.get(key))
            problems.append(f"{key}: expected {_fmt(want)}, got {shown}")
    return problems


# --- running cases ---------------------------------------------------------------

@dataclass
class CaseResult:
    id: str
    tags: list[str]
    passed: bool
    problems: list[str]
    got: dict
    scored: bool = False        # expect has a category -> counts for coverage/precision
    decided: bool = False       # got a category (not «не знаю»)
    correct: bool = False
    cost_usd: float = 0.0
    latency_ms: int = 0
    calls: list[dict] = field(default_factory=list)


def run_card_case(case: dict, engine: str, variant: str = "A") -> tuple[dict, list]:
    """-> (CardResult as dict, list of ModelResults made for this case)."""
    if engine == "baseline":
        return make_card_rules(ticket_from(case)).model_dump(), []
    if engine == "model":
        scenario = case.get("mock")
        # a "mock" case tests OUR code with a simulated failure: run it on mock even in a live run
        force_mock = config.use_model("mock", "mock-1") if scenario else nullcontext()
        with force_mock, use_scenario(scenario), collect_calls() as calls:
            result = make_card(ticket_from(case), variant=variant)
        return result.model_dump(), calls
    raise ValueError(f"unknown engine {engine!r}")


def evaluate(cases: list[dict], *, engine: str, variant: str = "A", runs: int = 1,
             max_usd: float | None = None) -> list[CaseResult]:
    """Every case `runs` times. With runs > 1 each run is a separate result (same id).
    max_usd: stop before the next case once the money spent reaches it (checked between cases)."""
    results = []
    for case in [c for c in cases for _ in range(runs)]:
        if max_usd is not None and sum(r.cost_usd for r in results) >= max_usd:
            break
        got, calls = run_card_case(case, engine, variant)
        expect = case.get("expect", {})
        problems = compare(expect, got, kind=case.get("kind", "card"))
        scored = expect.get("category") is not None      # null = "must not decide": not in coverage
        decided = got.get("category") is not None
        results.append(CaseResult(
            id=case["id"], tags=case.get("tags", []), passed=not problems, problems=problems, got=got,
            scored=scored, decided=scored and decided,
            correct=scored and decided and got.get("category") == expect["category"],
            cost_usd=sum(c.cost_usd for c in calls), latency_ms=sum(c.latency_ms for c in calls),
            calls=[{"status": c.status, "error": c.error, "stop_reason": c.stop_reason, "model": c.model,
                    "usage": asdict(c.usage), "text": c.text[:2000],
                    "price_known": (c.raw or {}).get("price_known", True)} for c in calls],
        ))
    return results


def percentile(values: list[int], p: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    rank = max(0, min(len(ordered) - 1, round(p / 100 * (len(ordered) - 1))))
    return ordered[rank]


def summary(results: list[CaseResult]) -> dict:
    n = len(results)
    passed = sum(r.passed for r in results)
    scored = [r for r in results if r.scored]
    decided = [r for r in scored if r.decided]
    lat = [r.latency_ms for r in results if r.calls]
    cost = sum(r.cost_usd for r in results)
    tokens = {"in": 0, "out": 0, "cached": 0}
    for r in results:
        for c in r.calls:
            tokens["in"] += c["usage"]["input_tokens"]
            tokens["out"] += c["usage"]["output_tokens"]
            tokens["cached"] += c["usage"]["cached_input_tokens"]
    return {"cases": n, "passed": passed, "scored": len(scored), "decided": len(decided),
            "correct": sum(r.correct for r in decided), "cost_usd": cost,
            "per_case": cost / n if n else 0.0, "per_success": cost / passed if passed else 0.0,
            "p50": percentile(lat, 50), "p95": percentile(lat, 95), "tokens": tokens,
            "errors": sum(1 for r in results if r.got.get("status") == "error")}


def report(results: list[CaseResult], *, run_id: str, kind: str, provider: str, model: str,
           split: str, simulated: bool, measured: bool, runs: int = 1) -> list[str]:
    n = len(results)
    passed = sum(r.passed for r in results)
    scored = [r for r in results if r.scored]
    decided = [r for r in scored if r.decided]
    correct = [r for r in decided if r.correct]
    cost = sum(r.cost_usd for r in results)
    pct = f"{100 * passed / n:.1f}%" if n else "n/a"
    lines = [
        f"run {run_id} · kind={kind} · provider={provider} model={model} · cases {n // runs} ({split})"
        + (f" × {runs} runs" if runs > 1 else ""),
        f"pass {passed}/{n} ({pct}) · "
        + (f"coverage {len(decided)}/{len(scored)} · precision {len(correct)}/{len(decided)}"
           if scored else "coverage n/a · precision n/a"),
    ]
    tail = " (simulated)" if simulated else ("" if measured else " (rules)")
    per_case = cost / n if n else 0.0
    per_success = cost / passed if passed else 0.0
    lines.append(f"cost ${cost:.4f}{tail} · per case ${per_case:.4f} · per success ${per_success:.4f}")
    if measured:
        s = summary(results)
        lines.append(f"latency p50 {s['p50']} ms · p95 {s['p95']} ms")
        lines.append(f"tokens in {s['tokens']['in']} · out {s['tokens']['out']} · cached {s['tokens']['cached']}")
        if s["errors"]:
            first = next(c["error"] for r in results for c in r.calls if c["error"])
            lines.append(f"errors {s['errors']}/{n} (first: {first})")
        unpriced = sorted({c["model"] for r in results for c in r.calls if not c.get("price_known", True)})
        if unpriced:
            lines.append(f"price unknown for {', '.join(unpriced)}: cost shown as $0, add it to support/prices.py")
    else:
        lines.append("latency n/a (rules, not measured)")
    for r in sorted(results, key=lambda r: r.id):
        if not r.passed:
            tag = f" [{r.tags[0]}]" if r.tags else ""
            lines.append(f"FAIL {r.id}{tag} {'; '.join(r.problems)}")
    return lines


def save_run(results: list[CaseResult], meta: dict, lines: list[str]) -> Path:
    folder = runs_dir()
    folder.mkdir(parents=True, exist_ok=True)
    label = re.sub(r"[^\w.-]+", "_", meta["label"])
    path = folder / f"{meta['run_id']}-{label}.json"
    payload = {"meta": meta, "report": lines, "cases": [asdict(r) for r in results]}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def show_path(path: Path) -> str:
    return path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else str(path)


def new_run_id() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")     # seconds: two runs in one minute never share a file


# --- lesson 7: several configurations, a comparison table, a budget before spending ---

ASSUMED_OUTPUT_TOKENS = 150     # a card is ~100-150 tokens of JSON; thinking tokens come on top


def comparison(rows: list[tuple[str, dict]]) -> list[str]:
    width = max(len(name) for name, _ in rows)
    out = [f"{'config':<{width}}  pass      cov     prec    $/case    p50    p95"]
    for name, s in rows:
        cov = f"{s['decided']}/{s['scored']}" if s["scored"] else "n/a"
        prec = f"{s['correct']}/{s['decided']}" if s["decided"] else "n/a"
        out.append(f"{name:<{width}}  {s['passed']:>3}/{s['cases']:<4} {cov:>7} {prec:>7}  "
                   f"${s['per_case']:.5f}  {s['p50']:>5}  {s['p95']:>5}")
    return out


def dry_run(cases: list[dict], configs: list[tuple[str, str]], *, runs: int, variant: str = "A") -> list[str]:
    """Count calls and estimate cost from prices.py. Calls nothing."""
    from support import config as cfg

    calls_per_case = 1
    prompt_tokens = sum(
        (len(CARD_SYSTEM) + len(build_card_prompt(ticket_from(c), variant)[0]["content"])) // 4 + 1
        for c in cases if c["input"]["text"].strip())
    n_calls = sum(1 for c in cases if c["input"]["text"].strip()) * runs * calls_per_case
    lines = [f"dry run · {len(cases)} cases × {runs} runs × {len(configs)} configs · "
             f"{n_calls} calls per config (empty tickets make no call)"]
    total, unknown = 0.0, []
    for provider, model in configs:
        tin, tout = prompt_tokens * runs, n_calls * ASSUMED_OUTPUT_TOKENS
        if provider == "mock":
            price = "$0.0000 (mock)"
        else:
            # price ONE call, then multiply: long-prompt tiers apply per request, never to a sum
            one = estimate_usd(model, tin // max(1, n_calls), ASSUMED_OUTPUT_TOKENS)
            cost = None if one is None else one * n_calls
            if cost is None:
                unknown.append(model)
                price = "price unknown: add it to support/prices.py"
            else:
                total += cost
                price = f"≈ ${cost:.4f}"
            if not cfg.api_key(provider):
                price += " · NO KEY in .env"
        lines.append(f"{provider}:{model} · ~{tin} in / ~{tout} out tokens · {price}")
    lines.append(f"total ≈ ${total:.4f} (output assumed {ASSUMED_OUTPUT_TOKENS} tokens per call) · nothing was called")
    return lines
