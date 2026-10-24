"""run_evals: the course's one eval command.

    uv run python -m support.evals --baseline                     # rules, no model (lesson 3, 5)
    uv run python -m support.evals                                # the model, mock by default (lesson 7)
    uv run python -m support.evals --model mock:mock-1 --model anthropic:claude-haiku-5-5 --dry-run
    uv run python -m support.evals --model openai:gpt-6-luna --runs 2 --tag edge --max-usd 0.05
    uv run python -m support.evals --tag own                      # only your cases (evals/own.jsonl)
    uv run python -m support.evals add-case "текст" --category доставка --order-id DEMO-1042
    uv run python -m support.evals --tag context --variant B             # A/B of the context (lesson 9)
    uv run python -m support.evals --prompt few                          # zero | one | few | reason (lesson 9)
    uv run python -m support.evals --prompt few --reverse-examples       # the same 3 examples, reverse order
    uv run python -m support.evals --prompt few --examples evals/examples_bias.jsonl   # 3 of one category
    uv run python -m support.evals --runs 3 --vote                       # majority of 3 runs per case
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from support import config
from support.card import PROMPTS, SHOTS, load_examples, shots
from support.evals import (comparison, dry_run, evaluate, example_leaks, load_cases, new_run_id, report,
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
    ap.add_argument("--variant", default="A", choices=["A", "B"], help="prompt/context variant (lesson 9)")
    ap.add_argument("--prompt", default="zero", choices=list(PROMPTS),
                    help="prompting technique (lesson 9): zero | one (1 example) | few (3) | reason (short `why` field)")
    ap.add_argument("--examples", default=None, help="examples file for --prompt one/few (default evals/examples.jsonl)")
    ap.add_argument("--reverse-examples", action="store_true", help="the same examples in reverse order")
    ap.add_argument("--vote", action="store_true", help="with --runs N: majority category; no majority -> needs_review")
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
    if args.vote and args.runs < 2:
        print("--vote потребує --runs 2 або більше (краще непарне: 3).")
        return 2
    if (args.examples or args.reverse_examples) and not SHOTS[args.prompt]:
        print("--examples і --reverse-examples працюють тільки з --prompt one або few.")
        return 2
    examples, prompt_label = None, args.prompt
    if SHOTS[args.prompt]:
        try:
            pool = load_examples(args.examples)
        except (OSError, ValueError) as exc:
            print(f"Не можу прочитати приклади: {exc}")
            return 2
        for ex_id, case_id in example_leaks(pool, load_cases(own=True)):
            print(f"WARNING: приклад {ex_id} збігається з кейсом {case_id}: прибери його з прикладів")
        examples = shots(args.prompt, pool)
        if args.reverse_examples:
            examples = examples[::-1]
        prompt_label += f" ({', '.join(str(e.get('id', '?')) for e in examples)})"
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
        print("\n".join(dry_run(cases, configs, runs=args.runs, variant=args.variant,
                                 prompt=args.prompt, examples=examples)))
        return 0

    rows, spent, planned = [], 0.0, len(cases) * (1 if args.vote else args.runs)
    for provider, model in configs:
        left = None if args.max_usd is None else args.max_usd - spent
        if left is not None and left <= 0:
            print(f"budget stop: ${spent:.4f} of ${args.max_usd:.4f} spent · {provider}:{model} not run")
            continue
        with config.use_model(provider, model, args.effort):
            results = evaluate(cases, engine="model", runs=args.runs, variant=args.variant,
                               max_usd=left, prompt=args.prompt, examples=examples, vote_runs=args.vote)
            effort = config.current_effort()
        spent += sum(r.cost_usd for r in results)
        if len(results) < planned:
            print(f"budget stop: ${spent:.4f} of ${args.max_usd:.4f} spent · "
                  f"{planned - len(results)} of {planned} cases not run")
        lines = report(results, run_id=run_id, kind=args.kind, provider=provider, model=model,
                       split=args.split, simulated=provider == "mock", measured=True, runs=args.runs,
                       variant=args.variant, prompt=prompt_label, vote_runs=args.vote)
        print("\n".join(lines))
        meta = {"run_id": run_id, "kind": args.kind, "provider": provider, "model": model,
                "effort": effort, "runs": args.runs, "split": args.split,
                "variant": args.variant, "tag": args.tag, "prompt": args.prompt, "vote": args.vote,
                "examples": [e.get("id") for e in examples] if examples else [],
                # one file per config and run: the label never hides provider, model and effort
                "label": (f"{args.label}-" if args.label else "") + f"{provider}-{model}-{effort}"
                + (f"-{args.variant}" if args.variant != "A" else "")
                + (f"-{args.prompt}" if args.prompt != "zero" else "")
                + (f"-{Path(args.examples).stem}" if args.examples else "") + ("-rev" if args.reverse_examples else "")
                + ("-vote" if args.vote else "")}
        mocked = sum(1 for c in cases if c.get("mock")) * args.runs
        if provider == "mock" and args.prompt != "zero":
            print("note: on mock the prompt effect is a fixed teaching rule (CONTRACT.md 11.14); "
                  "a live run measures the real one")
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
