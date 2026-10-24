"""Lesson 3: the card logic moved from index.html to Python, one test per check."""

import pytest

from support.contract import Ticket
from support.rules import make_card_rules, normalize_order_id


def card(text: str):
    return make_card_rules(Ticket(ticket_id="T-TEST", customer_id="c-17", text=text, created_at="2026-10-24T12:00:00+03:00"))


def test_check_1_number_found():
    r = card("Не отримав посилку, замовлення DEMO-1042")
    assert (r.status, r.order_id, r.missing) == ("ok", "DEMO-1042", [])


def test_check_2_number_missing():
    r = card("Не отримав посилку")
    assert (r.status, r.order_id, r.missing) == ("ok", None, ["order_id"])


def test_check_3_empty_input():
    for text in ("", "   ", "\n\t "):
        assert card(text).status == "empty_input"


@pytest.mark.parametrize("raw,expected", [
    ("DEMO-1042", "DEMO-1042"),
    ("demo-1042", "DEMO-1042"),
    ("DEMO 1042", "DEMO-1042"),
    (" Demo_1042 ", "DEMO-1042"),
    ("DEMO\u00a01042", "DEMO-1042"),
    ("1042", None),
    ("DEMO-104", None),
    ("DEMO-10420", None),
    ("DEMO-1042" + " " * 30, "DEMO-1042"),
    ("x" * 31, None),
    ("", None),
])
def test_normalize_order_id(raw, expected):
    assert normalize_order_id(raw) == expected


def test_number_inside_text_and_longer_numbers():
    assert card("де замовлення demo 1042?").order_id == "DEMO-1042"
    assert card("номер DEMO-10420").order_id is None
    assert card("DEMO-1042 і DEMO-1043").order_id == "DEMO-1042"   # first one wins
