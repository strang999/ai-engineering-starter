"""Lesson 6: one model call, read the ModelResult.

    uv run python -m support.llm                          # mock, ticket T-0001
    uv run python -m support.llm --scenario timeout       # a mock failure: status="error", no crash (always mock)
    uv run python -m support.llm --save runs/first-call.json
    (live: set AIEZ_PROVIDER and the key in .env, then the same command)
"""

from __future__ import annotations

import argparse
import contextlib
import json
import sys
from dataclasses import asdict
from pathlib import Path

from support import config
from support.card import CARD_SYSTEM, build_card_prompt
from support.contract import TicketCard
from support.data import get_ticket
from support.llm import call_model
from support.llm.mock import SCENARIOS, use_scenario


def main(argv: list[str] | None = None) -> int:
    config.setup_console()
    ap = argparse.ArgumentParser(prog="python -m support.llm")
    ap.add_argument("--ticket", default="T-0001")
    ap.add_argument("--scenario", choices=SCENARIOS, default=None, help="mock scenario")
    ap.add_argument("--save", default=None, help="write the ModelResult as JSON, e.g. runs/first-call.json")
    args = ap.parse_args(argv)

    ticket = get_ticket(args.ticket)
    # a scenario is a mock failure: run it on mock even when .env names a live provider
    force_mock = config.use_model("mock", "mock-1") if args.scenario else contextlib.nullcontext()
    with force_mock, use_scenario(args.scenario):
        r = call_model(build_card_prompt(ticket), system=CARD_SYSTEM, schema=TicketCard, purpose="card")

    cost = f"${r.cost_usd:.6f}" + (" (simulated)" if r.simulated_cost else "")
    print(f"ticket   {ticket.ticket_id}")
    print(f"provider {r.provider} · model {r.model}")
    print(f"status   {r.status} · stop_reason {r.stop_reason} · error {r.error}")
    print(f"usage    in {r.usage.input_tokens} · out {r.usage.output_tokens} · cached {r.usage.cached_input_tokens}")
    print(f"cost     {cost} · latency {r.latency_ms} ms · attempts {(r.raw or {}).get('attempts', 1)}")
    if isinstance(r.parsed, TicketCard):
        print("parsed   " + r.parsed.model_dump_json())
    elif r.text:
        print("text     " + r.text[:300])
    if args.save:
        path = Path(args.save)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = asdict(r)
        data["parsed"] = r.parsed.model_dump() if isinstance(r.parsed, TicketCard) else None
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"saved    {path.as_posix()}")
    return 0 if r.status == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
