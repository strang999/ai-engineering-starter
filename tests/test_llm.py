"""Lesson 6: call_model in mock and live mode, without spending anything."""

import json

from support import config
from support.contract import TicketCard
from support.llm import call_model, collect_calls
from support.llm.__main__ import main as first_call_main
from support.prices import PRICES, estimate_usd

MSG = [{"role": "user", "content": '<ticket id="T-0001">Не отримав посилку, замовлення DEMO-1042</ticket>'}]


def test_live_provider_without_key_is_a_status_not_a_crash(monkeypatch):
    for name in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    for provider in ("anthropic", "openai", "gemini"):
        with config.use_model(provider):
            r = call_model(MSG, schema=TicketCard)
        assert r.status == "error" and r.error.startswith("no_api_key")
        assert r.provider == provider and r.model == config.DEFAULT_MODELS[provider]


def test_unknown_provider(monkeypatch):
    monkeypatch.setenv("AIEZ_PROVIDER", "nope")
    r = call_model(MSG)
    assert r.status == "error" and r.error.startswith("unknown_provider")


def test_calls_log_has_no_ticket_text(tmp_path, monkeypatch):
    monkeypatch.setenv("AIEZ_RUNS_DIR", str(tmp_path))
    call_model(MSG, schema=TicketCard)
    lines = (tmp_path / "calls.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["provider"] == "mock" and entry["status"] == "ok" and entry["simulated_cost"] is True
    assert "посилку" not in lines[0] and "DEMO-1042" not in lines[0]


def test_collect_calls():
    with collect_calls() as calls:
        call_model(MSG)
        call_model(MSG)
    assert len(calls) == 2


def test_prices_are_per_million_tokens():
    assert abs(estimate_usd("claude-haiku-5-5", 100_000, 0) - 0.01) < 1e-12        # 0.10 per MTok
    assert abs(estimate_usd("claude-haiku-5-5", 1000, 1000) - 0.0006) < 1e-12
    assert abs(estimate_usd("claude-haiku-5-5", 200_000, 0) - 0.10) < 1e-12        # over 100K: 0.50 per MTok
    assert estimate_usd("unknown-model", 10, 10) is None              # never pretend a model is free
    # 1000 input tokens of which 800 written to the cache: 200 x 0.10 + 800 x 0.125 per MTok
    assert abs(estimate_usd("claude-haiku-5-5", 1000, 0, cache_write_tokens=800) - 0.00012) < 1e-12
    for model in config.DEFAULT_MODELS.values():
        assert model in PRICES, f"default model {model} has no price"


def test_first_call_cli_saves_json(tmp_path, capsys):
    path = tmp_path / "first-call.json"
    assert first_call_main(["--save", str(path)]) == 0
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["provider"] == "mock" and data["status"] == "ok" and data["parsed"]["order_id"]["value"] == "DEMO-1042"


def test_timeout_scenario_returns_error_status(capsys):
    assert first_call_main(["--scenario", "timeout"]) == 1
    out = capsys.readouterr().out
    assert "status   error" in out and "error timeout" in out


def test_scenario_runs_on_mock_even_with_a_live_provider_in_env(capsys, monkeypatch):
    monkeypatch.setenv("AIEZ_PROVIDER", "anthropic")
    assert first_call_main(["--scenario", "timeout"]) == 1
    out = capsys.readouterr().out
    assert "provider mock · model mock-1" in out and "error timeout" in out
