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
from pathlib import Path

from support.config import ROOT
from support.contract import Ticket
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
            problems.append(f"{key}: expected {_fmt(want)}, got {_fmt(got.get(key))}")
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


def run_card_case(case: dict, engine: str) -> tuple[dict, list]:
    """-> (CardResult as dict, list of ModelResults made for this case)."""
    if engine == "baseline":
        return make_card_rules(ticket_from(case)).model_dump(), []
    raise ValueError(f"unknown engine {engine!r}")


def evaluate(cases: list[dict], *, engine: str) -> list[CaseResult]:
    results = []
    for case in cases:
        got, calls = run_card_case(case, engine)
        expect = case.get("expect", {})
        problems = compare(expect, got, kind=case.get("kind", "card"))
        scored = "category" in expect
        decided = got.get("category") is not None
        results.append(CaseResult(
            id=case["id"], tags=case.get("tags", []), passed=not problems, problems=problems, got=got,
            scored=scored, decided=scored and decided,
            correct=scored and decided and got.get("category") == expect["category"],
            cost_usd=sum(c.cost_usd for c in calls), latency_ms=sum(c.latency_ms for c in calls),
            calls=[{"status": c.status, "error": c.error, "stop_reason": c.stop_reason,
                    "usage": asdict(c.usage), "text": c.text[:2000]} for c in calls],
        ))
    return results


def percentile(values: list[int], p: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    rank = max(0, min(len(ordered) - 1, round(p / 100 * (len(ordered) - 1))))
    return ordered[rank]


def report(results: list[CaseResult], *, run_id: str, kind: str, provider: str, model: str,
           split: str, simulated: bool, measured: bool) -> list[str]:
    n = len(results)
    passed = sum(r.passed for r in results)
    scored = [r for r in results if r.scored]
    decided = [r for r in scored if r.decided]
    correct = [r for r in decided if r.correct]
    cost = sum(r.cost_usd for r in results)
    pct = f"{100 * passed / n:.1f}%" if n else "n/a"
    lines = [
        f"run {run_id} · kind={kind} · provider={provider} model={model} · cases {n} ({split})",
        f"pass {passed}/{n} ({pct}) · "
        + (f"coverage {len(decided)}/{len(scored)} · precision {len(correct)}/{len(decided)}"
           if scored else "coverage n/a · precision n/a"),
    ]
    tail = " (simulated)" if simulated else ("" if measured else " (rules)")
    per_case = cost / n if n else 0.0
    per_success = cost / passed if passed else 0.0
    lines.append(f"cost ${cost:.4f}{tail} · per case ${per_case:.4f} · per success ${per_success:.4f}")
    if measured:
        lat = [r.latency_ms for r in results if r.calls]
        lines.append(f"latency p50 {percentile(lat, 50)} ms · p95 {percentile(lat, 95)} ms")
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
