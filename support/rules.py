"""Plain-code rules: the card without a model (lesson 3), baseline for evals."""

from __future__ import annotations

import re
import unicodedata

from support.contract import CardResult, Category, Ticket

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


# Lesson 5 baseline: keywords only, first match wins, otherwise abstain (None = «не знаю»).
# Deliberately naive: «Не хочу повернення, обміняйте…» lands in «повернення» (the lesson's №4).
_TRIAGE: tuple[tuple[Category, tuple[str, ...]], ...] = (
    ("повернення", ("поверн", "povern")),      # only together with an order number, see below
    ("брак", ("зламан", "розбит", "відклеє", "пошкодж")),
    ("обмін", ("поміня", "обміня")),
    ("оплата", ("списали", "оплата не прох", "помилка e-")),
    ("акаунт", ("пароль", "увійти", "кабінет")),
    ("доставка", ("посилк",)),
)


def triage_rules(text: str) -> Category | None:
    """Category from keywords, or None when the rules are not sure («не знаю»)."""
    low = unicodedata.normalize("NFKC", text).lower()   # not _fold: it would turn Cyrillic «о» into Latin
    if not low.strip():
        return None
    for category, words in _TRIAGE:
        if any(w in low for w in words):
            if category == "повернення" and _first_order_id(text) is None:
                return None          # refund without an order number: let a person or the model decide
            return category
    return None


def make_card_rules(ticket: Ticket) -> CardResult:
    """Card v2: order number or a note that it is missing, plus a category or «не знаю». No model."""
    if not ticket.text.strip():
        return CardResult(status="empty_input", ticket_id=ticket.ticket_id)
    order_id = _first_order_id(ticket.text)
    return CardResult(
        status="ok",
        ticket_id=ticket.ticket_id,
        order_id=order_id,
        category=triage_rules(ticket.text),
        missing=[] if order_id else ["order_id"],
    )


# --- lesson 8: money from text to kopiyky (int). float for money: never. ---------

_CURRENCY = re.compile(r"\s*(грн\.?|гривень|гривні|гривня|uah|₴)\s*$", re.I)
_SPACES = re.compile(r"[\s\u00a0\u202f']")


def parse_amount_kop(raw: str) -> int | None:
    """'1 250,00 грн' -> 125000, '540 грн' -> 54000, '-1250.00' -> -125000, 'півтори тисячі' -> None.

    The sign is kept: whether a negative or zero amount is acceptable is the caller's rule."""
    if not isinstance(raw, str):
        return None
    text = _CURRENCY.sub("", unicodedata.normalize("NFKC", raw).strip())
    sign = -1 if text.startswith("-") else 1
    text = _SPACES.sub("", text.lstrip("+-"))
    if not re.fullmatch(r"[\d.,]+", text or "x"):
        return None
    if "," in text and "." in text:                # the last separator is the decimal one
        dec = "," if text.rfind(",") > text.rfind(".") else "."
        text = text.replace("." if dec == "," else ",", "").replace(dec, ".")
    elif "," in text:
        text = text.replace(",", ".")
    whole, _, frac = text.partition(".")
    if not whole.isdigit() or "." in frac or len(frac) > 2 or (frac and not frac.isdigit()):
        return None                                # '12.345' is ambiguous: refuse, don't guess
    return sign * (int(whole) * 100 + int(frac.ljust(2, "0") or 0))
