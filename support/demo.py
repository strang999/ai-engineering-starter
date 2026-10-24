"""Quick win of lesson 0: the first ticket card, in mock mode, with no key.

    uv run python -m support.demo            # ticket T-0001
    uv run python -m support.demo T-0007     # any ticket from data/tickets.jsonl
"""

from __future__ import annotations

import sys

from support import config
from support.contract import TicketCard
from support.data import get_ticket
from support.llm import call_model

SYSTEM = ("Ти помічник оператора інтернет-магазину «Демо-маркет». "
          "Поверни картку звернення як JSON. Якщо факту нема в тексті, став null.")


def show(value: str | None, evidence: str | None) -> str:
    if value is None:
        return "невідомо"
    return f"{value}  ← «{evidence}»" if evidence else f"{value}  ← без цитати"


def main(argv: list[str]) -> int:
    config.setup_console()
    ticket = get_ticket(argv[0] if argv else "T-0001")
    messages = [{"role": "user", "content": f'<ticket id="{ticket.ticket_id}">{ticket.text}</ticket>'}]
    result = call_model(messages, system=SYSTEM, schema=TicketCard, purpose="card")

    print("Демо-маркет · картка звернення")
    print(f"Звернення {ticket.ticket_id} ({ticket.customer_id}): {ticket.text}")
    card = result.parsed
    if isinstance(card, TicketCard):
        print(f"категорія:  {show(card.category, card.category_evidence)}")
        print(f"замовлення: {show(card.order_id.value, card.order_id.evidence)}")
        print(f"сума:       {show(card.amount.value, card.amount.evidence)}")
        print(f"теги:       {', '.join(card.tags) or 'нема'}")
    else:
        print(f"картки нема: status={result.status} error={result.error}")
    cost = f"${result.cost_usd:.4f}" + (" (simulated)" if result.simulated_cost else "")
    print(f"status={result.status} · provider={result.provider} model={result.model} · "
          f"tokens {result.usage.input_tokens}→{result.usage.output_tokens} · cost {cost} · {result.latency_ms} ms")
    return 0 if result.status == "ok" and result.parsed is not None else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
