"""uv run python -m support.evals [--baseline] [--kind card] [--split dev] [--tag edge] [--id c001] [--label NAME]
uv run python -m support.evals add-case "текст" --category доставка --order-id DEMO-1042   (evals/own.jsonl)"""

from __future__ import annotations

import argparse
import sys

from support import config
from support.evals import evaluate, load_cases, new_run_id, report, save_run, select, show_path
from support.evals.own import add_case_main


def main(argv: list[str] | None = None) -> int:
    config.setup_console()
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["add-case"]:
        return add_case_main(argv[1:])
    ap = argparse.ArgumentParser(prog="python -m support.evals", description="Run evals/cases.jsonl + evals/own.jsonl")
    ap.add_argument("--kind", default="card", choices=["card"])
    ap.add_argument("--baseline", action="store_true", help="plain-code rules instead of a model")
    ap.add_argument("--split", default="dev", choices=["dev", "holdout"])
    ap.add_argument("--tag", default=None, help="only cases with this tag; own = only evals/own.jsonl")
    ap.add_argument("--id", action="append", default=[], dest="ids", help="only this case id; repeat")
    ap.add_argument("--label", default=None, help="name for the runs/ file")
    args = ap.parse_args(argv)

    if not args.baseline:
        print("Модельний шлях з'явиться в уроці 6 (тег l06). Зараз запускай: "
              "uv run python -m support.evals --baseline")
        return 2

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
    results = evaluate(cases, engine="baseline")
    lines = report(results, run_id=run_id, kind=args.kind, provider="baseline", model="rules",
                   split=args.split, simulated=False, measured=False)
    print("\n".join(lines))
    meta = {"run_id": run_id, "kind": args.kind, "provider": "baseline", "model": "rules",
            "split": args.split, "tag": args.tag, "label": args.label or "baseline"}
    path = save_run(results, meta, lines)
    print(f"saved {show_path(path)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
