"""Lesson 3: the page talks to POST /api/card; the customer comes from the session."""

from fastapi.testclient import TestClient

from support.server import app

client = TestClient(app)


def test_index_page_is_served():
    r = client.get("/")
    assert r.status_code == 200 and "/api/card" in r.text


def test_api_card_returns_card_result():
    r = client.post("/api/card", json={"text": "Не отримав посилку, замовлення DEMO-1042"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok" and body["order_id"] == "DEMO-1042" and body["missing"] == []


def test_api_card_rejects_customer_id_from_request():
    r = client.post("/api/card", json={"text": "DEMO-1042", "customer_id": "c-99"})
    assert r.status_code == 422          # refused, never trusted
    r = client.post("/api/card", json={"text": "x" * 5000})
    assert r.status_code == 422


def test_card_is_saved_and_repeats_endpoint_answers():
    r = client.post("/api/card", json={"text": "де DEMO-1044?"})
    assert r.status_code == 200
    r = client.get("/api/repeats", params={"order_id": "DEMO-1044"})
    assert r.json() == {"order_id": "DEMO-1044", "repeats": 0}      # the ticket just sent is < 10 min old
    assert client.get("/api/repeats", params={"order_id": "1044"}).status_code == 422


def test_cors_allows_only_local_dev_origins():
    """A Vite app on localhost:5173 can call the service; any other site cannot."""
    pre = {"Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "content-type"}
    r = client.options("/api/card", headers={"Origin": "http://localhost:5173", **pre})
    assert r.status_code == 200 and r.headers["access-control-allow-origin"] == "http://localhost:5173"
    r = client.post("/api/card", json={"text": "DEMO-1042"}, headers={"Origin": "http://127.0.0.1:3000"})
    assert r.headers["access-control-allow-origin"] == "http://127.0.0.1:3000"
    r = client.options("/api/card", headers={"Origin": "https://evil.example", **pre})
    assert "access-control-allow-origin" not in r.headers
