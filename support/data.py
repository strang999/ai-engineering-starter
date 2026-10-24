"""Demo data of «Демо-маркет»: orders (money in kopiyky) and tickets."""

from __future__ import annotations

import json
from pathlib import Path

from support.config import DATA_DIR
from support.contract import Ticket


def load_orders(path: Path | None = None) -> list[dict]:
    return json.loads((path or DATA_DIR / "orders.json").read_text(encoding="utf-8"))


def orders_for(customer_id: str, orders: list[dict] | None = None) -> list[dict]:
    """Only this customer's orders. A foreign order looks exactly like a missing one."""
    return [o for o in (orders if orders is not None else load_orders()) if o["customer_id"] == customer_id]


def load_tickets(path: Path | None = None) -> list[Ticket]:
    lines = (path or DATA_DIR / "tickets.jsonl").read_text(encoding="utf-8").splitlines()
    return [Ticket.model_validate_json(line) for line in lines if line.strip()]


def get_ticket(ticket_id: str) -> Ticket:
    for ticket in load_tickets():
        if ticket.ticket_id == ticket_id:
            return ticket
    raise KeyError(f"no ticket {ticket_id} in data/tickets.jsonl")
