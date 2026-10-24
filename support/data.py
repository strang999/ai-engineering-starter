"""Demo data of «Демо-маркет»: orders (money in kopiyky) and tickets."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from datetime import datetime, timedelta
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


# --- SQLite (lesson 4): ticket history in data/support.db --------------------

SCHEMA = """
CREATE TABLE IF NOT EXISTS tickets (
    ticket_id   TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL,
    order_id    TEXT,
    text_hash   TEXT NOT NULL,
    created_at  TEXT NOT NULL          -- ISO 8601 with timezone
);
CREATE INDEX IF NOT EXISTS tickets_order ON tickets(order_id);
"""

REPEAT_MIN_AGE = timedelta(minutes=10)      # younger: the same ticket sent twice, not a repeat
REPEAT_MAX_AGE = timedelta(days=30)         # older: a new story, not a repeat


def db_path() -> Path:
    return Path(os.environ.get("AIEZ_DB") or DATA_DIR / "support.db")


def connect(path: Path | str | None = None) -> sqlite3.Connection:
    """Open (and create if needed) the SQLite file. Use ":memory:" in tests."""
    conn = sqlite3.connect(str(path or db_path()))
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def text_hash(text: str) -> str:
    """We keep a hash, not the ticket text: the history needs no personal data."""
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()[:16]


def save_ticket(conn: sqlite3.Connection, ticket: Ticket, order_id: str | None) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO tickets(ticket_id, customer_id, order_id, text_hash, created_at) VALUES (?, ?, ?, ?, ?)",
        (ticket.ticket_id, ticket.customer_id, order_id, text_hash(ticket.text), ticket.created_at),
    )
    conn.commit()


def count_repeats(conn: sqlite3.Connection, order_id: str, now: datetime) -> int:
    """How many earlier tickets about this order are 10 min .. 30 days old, both bounds inclusive.

    `now` comes from outside, so tests can fix the time (specs/repeat-tickets.md)."""
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware, e.g. datetime.now(timezone.utc)")
    rows = conn.execute("SELECT created_at FROM tickets WHERE order_id = ?", (order_id,)).fetchall()
    count = 0
    for row in rows:
        age = now - datetime.fromisoformat(row["created_at"])
        if REPEAT_MIN_AGE <= age <= REPEAT_MAX_AGE:
            count += 1
    return count
