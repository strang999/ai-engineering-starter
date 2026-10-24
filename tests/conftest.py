"""Every test runs in mock mode, offline, with no keys and no .env."""

import os

# Set before any `support` import: config.load_dotenv() never overrides existing variables.
os.environ["AIEZ_PROVIDER"] = "mock"
os.environ["AIEZ_NO_DOTENV"] = "1"
os.environ.pop("AIEZ_MODEL", None)
os.environ.pop("AIEZ_MOCK_SCENARIO", None)

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _isolated_runs(tmp_path, monkeypatch):
    """Anything a test writes to runs/ or the SQLite file goes to a temp folder."""
    monkeypatch.setenv("AIEZ_RUNS_DIR", str(tmp_path / "runs"))
    monkeypatch.setenv("AIEZ_DB", str(tmp_path / "support.db"))
