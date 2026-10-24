"""run_evals: the course's one eval command.

    uv run python -m support.evals --baseline                     # rules, no model (lesson 3, 5)
    uv run python -m support.evals                                # the model, mock by default (lesson 7)
    uv run python -m support.evals --model mock:mock-1 --model anthropic:claude-haiku-5-5 --dry-run
    uv run python -m support.evals --model openai:gpt-6-luna --runs 2 --tag edge --max-usd 0.05
    uv run python -m support.evals --tag own                      # only your cases (evals/own.jsonl)
    uv run python -m support.evals add-case "текст" --category доставка --order-id DEMO-1042
"""

from __future__ import annotations

import argparse
import sys

from support import config
from support.evals import (comparison, dry_run, evaluate, load_cases, new_run_id, report,
                           save_run, select, show_path, summary)
from support.evals.own import add_case_main


def parse_configs(models: list[str], provider: str | None) -> list[tuple[str, str]]:
    """'anthropic:claude-haiku-5-5' or a bare model id (then --provider / AIEZ_PROVIDER)."""
    if not models:
        with config.use_model(provider):
            return [config.resolve()]
    out = []
    for item in models:
        prov, sep, model = item.partition(":")
        if not sep:
            prov, model = provider or config.current_provider(), item
        out.append((prov.strip().lower(), model.strip()))
    return out


def main(argv: list[str] | None = None) -> int:
    config.setup_console()
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["add-case"]:
        return add_case_main(argv[1:])
    ap = argparse.ArgumentParser(prog="python -m support.evals", description="Run evals/cases.jsonl + evals/own.jsonl")
    ap.add_argument("--kind", default="card", choices=["card"])
    ap.add_argument("--baseline", action="store_true", help="plain-code rules instead of a model")
    ap.add_argument("--provider", default=None, help="mock | anthropic | openai | gemini")
    ap.add_argument("--model", action="append", default=[], help="model id or provider:model; repeat to compare")
    ap.add_argument("--effort", default=None, choices=["low", "medium", "high"])
    ap.add_argument("--runs", type=int, default=1, help="run every case N times")
    ap.add_argument("--split", default="dev", choices=["dev", "holdout"])
    ap.add_argument("--tag", default=None, help="only cases with this tag; own = only evals/own.jsonl")
    ap.add_argument("--id", action="append", default=[], dest="ids", help="only this case id; repeat")
    ap.add_argument("--dry-run", action="store_true", help="count calls and estimate cost, call nothing")
    ap.add_argument("--max-usd", type=float, default=None, help="stop the run once this much money is spent")
    ap.add_argument("--label", default=None, help="name for the runs/ file")
    args = ap.parse_args(argv)

    try:
        cases = select(load_cases(own=True), kind=args.kind, split=args.split, tag=args.tag)
    except ValueError as exc:
        print(f"Не можу прочитати кейси: {exc}")
        return 2
    if args.ids:
        cases = [c for c in cases if c["id"] in set(args.ids)]
    if not cases:
        print("Немає кейсів для цього фільтра.")
        return 2
    run_id = new_run_id()

    if args.baseline:
        results = evaluate(cases, engine="baseline")
        lines = report(results, run_id=run_id, kind=args.kind, provider="baseline", model="rules",
                       split=args.split, simulated=False, measured=False)
        print("\n".join(lines))
        meta = {"run_id": run_id, "kind": args.kind, "provider": "baseline", "model": "rules",
                "split": args.split, "tag": args.tag, "label": args.label or "baseline"}
        print(f"saved {show_path(save_run(results, meta, lines))}")
        return 0

    configs = parse_configs(args.model, args.provider)
    if args.dry_run:
        print("\n".join(dry_run(cases, configs, runs=args.runs)))
        return 0

    rows, spent, planned = [], 0.0, len(cases) * args.runs
    for provider, model in configs:
        left = None if args.max_usd is None else args.max_usd - spent
        if left is not None and left <= 0:
            print(f"budget stop: ${spent:.4f} of ${args.max_usd:.4f} spent · {provider}:{model} not run")
            continue
        with config.use_model(provider, model, args.effort):
            results = evaluate(cases, engine="model", runs=args.runs, max_usd=left)
            effort = config.current_effort()
        spent += sum(r.cost_usd for r in results)
        if len(results) < planned:
            print(f"budget stop: ${spent:.4f} of ${args.max_usd:.4f} spent · "
                  f"{planned - len(results)} of {planned} cases not run")
        lines = report(results, run_id=run_id, kind=args.kind, provider=provider, model=model,
                       split=args.split, simulated=provider == "mock", measured=True, runs=args.runs)
        print("\n".join(lines))
        meta = {"run_id": run_id, "kind": args.kind, "provider": provider, "model": model,
                "effort": effort, "runs": args.runs, "split": args.split, "tag": args.tag,
                # one file per config and run: the label never hides provider, model and effort
                "label": (f"{args.label}-" if args.label else "") + f"{provider}-{model}-{effort}"}
        mocked = sum(1 for c in cases if c.get("mock")) * args.runs
        if provider != "mock" and mocked:
            print(f"mock cases: {mocked} ran on mock (a simulated failure tests our code, not the model)")
        print(f"saved {show_path(save_run(results, meta, lines))}")
        rows.append((f"{provider}:{model}", summary(results)))
    if len(rows) > 1:
        print()
        print("\n".join(comparison(rows)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
