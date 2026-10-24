"""Lesson 1: the browser prototype and its 3 checks, written before the code."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_kb_has_a_checks_section():
    """Loose on purpose: your own KB.md in any format passes, as long as the checks are written down."""
    kb = (ROOT / "KB.md").read_text(encoding="utf-8")
    assert re.search(r"^#+ .*Перевірки", kb, re.M), "KB.md needs a section «Перевірки» with the checks"


def test_prototype_has_no_keys_and_no_external_code():
    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    assert "Номер не надано" in html
    assert not re.search(r"<script[^>]+src=", html), "no external scripts in the prototype"
    for leak in ("sk-", "api_key", "apiKey", "Authorization"):
        assert leak not in html, f"{leak!r} must never be in browser code"
