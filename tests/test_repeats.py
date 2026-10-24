"""Lesson 4: one test per acceptance criterion in specs/repeat-tickets.md."""

from datetime import datetime, timedelta, timezone

import pytest

from support.contract import Ticket
from support.data import connect, count_repeats, save_ticket
from support.rules import make_card_rules, normalize_order_id

NOW = datetime(2026, 10, 24, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def conn():
    c = connect(":memory:")
    yield c
    c.close()


def add(conn, ticket_id: str, order_id: str, age: timedelta) -> None:
    created = (NOW - age).isoformat()
    save_ticket(conn, Ticket(ticket_id=ticket_id, customer_id="c-17", text="текст", created_at=created), order_id)


def test_1_five_minutes_ago_is_not_a_repeat(conn):
    add(conn, "T-A", "DEMO-1042", timedelta(minutes=5))
    assert count_repeats(conn, "DEMO-1042", NOW) == 0
    assert conn.execute("SELECT COUNT(*) FROM tickets").fetchone()[0] == 1


def test_2_exactly_ten_minutes_counts(conn):
    add(conn, "T-A", "DEMO-1042", timedelta(minutes=10))
    assert count_repeats(conn, "DEMO-1042", NOW) == 1


def test_3_exactly_30_days_counts(conn):
    add(conn, "T-A", "DEMO-1042", timedelta(days=30))
    assert count_repeats(conn, "DEMO-1042", NOW) == 1


def test_4_older_than_30_days_does_not_count(conn):
    add(conn, "T-A", "DEMO-1042", timedelta(days=30, seconds=1))
    assert count_repeats(conn, "DEMO-1042", NOW) == 0


def test_5_other_order_does_not_count(conn):
    add(conn, "T-A", "DEMO-1043", timedelta(hours=1))
    assert count_repeats(conn, "DEMO-1042", NOW) == 0


def test_6_cyrillic_lookalikes():
    assert normalize_order_id("d\u0435m\u043e-1042") == "DEMO-1042"
    card = make_card_rules(Ticket(ticket_id="T-0009", customer_id="c-17",
                                  text="d\u0435m\u043e-1042 де воно??", created_at=NOW.isoformat()))
    assert card.order_id == "DEMO-1042"


def test_now_must_have_a_timezone(conn):
    with pytest.raises(ValueError):
        count_repeats(conn, "DEMO-1042", datetime(2026, 10, 24, 12, 0))


def test_several_old_tickets(conn):
    add(conn, "T-A", "DEMO-1042", timedelta(days=1))
    add(conn, "T-B", "DEMO-1042", timedelta(days=2))
    add(conn, "T-C", "DEMO-1042", timedelta(minutes=1))
    assert count_repeats(conn, "DEMO-1042", NOW) == 2
