"""Plain-code rules: the card without a model (lesson 3), baseline for evals."""

from __future__ import annotations

import re
import unicodedata

from support.contract import CardResult, Ticket

# Cyrillic letters that look like Latin ones in "DEMO" (lesson 4, «чекліст країв»: «dеmо-1042»)
_LOOKALIKES = str.maketrans({"е": "e", "Е": "E", "о": "o", "О": "O", "м": "m", "М": "M"})

# "demo", any spaces/dashes/underscores, exactly 4 digits (not part of a longer number)
_ORDER_FULL = re.compile(r"demo[\s\-_]*(\d{4})", re.I)
_ORDER_SEARCH = re.compile(r"demo[\s\-_]*\d{4}(?!\d)", re.I)


def normalize_order_id(raw: str) -> str | None:
    """'demo 1042', ' DEMO-1042 ', 'dеmо-1042' (Cyrillic е, о) -> 'DEMO-1042'. Anything else -> None."""
    if not isinstance(raw, str):
        return None
    text = _fold(raw).strip()
    if not text or len(text) > 30:
        return None
    m = _ORDER_FULL.fullmatch(text)
    return f"DEMO-{m.group(1)}" if m else None


def _fold(text: str) -> str:
    """NFKC (non-breaking spaces, full-width digits) + Cyrillic look-alikes -> Latin."""
    return unicodedata.normalize("NFKC", text).translate(_LOOKALIKES)


def _first_order_id(text: str) -> str | None:
    """The first order number in a ticket. Several numbers: the first one wins (CONTRACT.md, 11.6)."""
    m = _ORDER_SEARCH.search(_fold(text))
    return normalize_order_id(m.group(0)) if m else None


def make_card_rules(ticket: Ticket) -> CardResult:
    """Card v1: order number or a note that it is missing. No model."""
    if not ticket.text.strip():
        return CardResult(status="empty_input", ticket_id=ticket.ticket_id)
    order_id = _first_order_id(ticket.text)
    return CardResult(
        status="ok",
        ticket_id=ticket.ticket_id,
        order_id=order_id,
        missing=[] if order_id else ["order_id"],
    )
