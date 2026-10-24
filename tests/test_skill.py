"""Lesson 2: one skill, the same text for Codex (.agents) and Claude Code (.claude)."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_pre_commit_skill_is_the_same_for_both_tools():
    a = (ROOT / ".agents" / "skills" / "pre-commit-check" / "SKILL.md").read_text(encoding="utf-8")
    b = (ROOT / ".claude" / "skills" / "pre-commit-check" / "SKILL.md").read_text(encoding="utf-8")
    assert a == b
    head = a.split("---")[1]
    assert "name: pre-commit-check" in head
    assert "description:" in head and "Спрацьовує" in head
    assert "uv run pytest -q" in a and "STATE.md" in a
    assert "Сам нічого не коміть" in a
    assert "evals/own.jsonl" in a       # own cases never block a commit (course convention)
