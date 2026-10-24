"""Environment, provider defaults and the Windows UTF-8 guard."""

from __future__ import annotations

import os
import sys
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"

# Provider -> default model: the cheapest current model per provider (checked 2026-10-24,
# docs/VERIFIED.md). Mock is the default provider everywhere. Live defaults are UNTESTED
# against the live APIs until someone runs lesson 7 with a key.
DEFAULT_MODELS: dict[str, str] = {
    "mock": "mock-1",
    "anthropic": "claude-haiku-5-5",
    "openai": "gpt-6-luna",
    "gemini": "gemini-2.5-flash-lite",
}

API_KEY_ENV: dict[str, tuple[str, ...]] = {
    "anthropic": ("ANTHROPIC_API_KEY",),
    "openai": ("OPENAI_API_KEY",),
    "gemini": ("GEMINI_API_KEY", "GOOGLE_API_KEY"),
}
PROVIDERS: tuple[str, ...] = tuple(DEFAULT_MODELS)

_override: ContextVar[dict | None] = ContextVar("aiez_model_override", default=None)


def load_dotenv(path: Path | None = None) -> None:
    """Read KEY=VALUE lines from .env. Never overrides variables that are already set."""
    if os.environ.get("AIEZ_NO_DOTENV") == "1":
        return
    path = path or ROOT / ".env"
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and value and key not in os.environ:
            os.environ[key] = value


load_dotenv()


def current_provider() -> str:
    over = _override.get()
    if over and over.get("provider"):
        return over["provider"]
    return (os.environ.get("AIEZ_PROVIDER") or "mock").strip().lower()


def resolve(model: str | None = None) -> tuple[str, str]:
    """(provider, model) for one call: explicit argument > use_model() > AIEZ_MODEL > default."""
    provider = current_provider()
    over = _override.get() or {}
    chosen = model or over.get("model") or (os.environ.get("AIEZ_MODEL") or "").strip()
    return provider, chosen or DEFAULT_MODELS.get(provider, "")


@contextmanager
def use_model(provider: str | None = None, model: str | None = None):
    """Temporarily pick provider/model (run_evals uses this). Does not touch os.environ."""
    token = _override.set({"provider": provider, "model": model})
    try:
        yield
    finally:
        _override.reset(token)


def api_key(provider: str) -> str | None:
    """The key for a live provider, from the environment or .env. Never print or log it."""
    for name in API_KEY_ENV.get(provider, ()):
        value = (os.environ.get(name) or "").strip()
        if value:
            return value
    return None


def runs_dir() -> Path:
    return Path(os.environ.get("AIEZ_RUNS_DIR") or ROOT / "runs")


def utf8_ok() -> bool:
    return bool(sys.flags.utf8_mode)


def setup_console() -> None:
    """Make Ukrainian print() safe even when PYTHONUTF8 is off (cp1252 consoles, piped stdout)."""
    for stream in (sys.stdout, sys.stderr):
        enc = (getattr(stream, "encoding", "") or "").lower().replace("-", "")
        if enc != "utf8" and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    if not utf8_ok():
        # ASCII on purpose: this line must print on any console.
        print("WARNING: Python UTF-8 mode is off. Run once: setx PYTHONUTF8 1 "
              "and reopen the terminal (scripts/doctor.py checks it).", file=sys.stderr)
