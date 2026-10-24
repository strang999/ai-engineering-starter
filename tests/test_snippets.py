"""«Runs as printed»: every fenced block marked for this tag runs and prints its ```output.

Lesson writers: point AIEZ_LESSONS_DIR at the lesson folder (docs/SNIPPETS.md).
"""

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("check_snippets", ROOT / "scripts" / "check_snippets.py")
snippets = importlib.util.module_from_spec(_spec)
sys.modules["check_snippets"] = snippets
_spec.loader.exec_module(snippets)

TAG = snippets.current_tag()
FOUND = [s for path in snippets.sources() for s in snippets.extract(path) if snippets.applies(s, TAG)]


@pytest.mark.parametrize("snippet", FOUND, ids=[s.id for s in FOUND])
def test_snippet_runs_as_printed(snippet):
    problem = snippets.check(snippet)
    assert problem is None, problem


def test_matcher_wildcards():
    assert snippets.matches("run {*} · kind=card\n...\nlast", "run 20261102-1012 · kind=card\na\nb\nlast\n")
    assert not snippets.matches("pass 3/3", "pass 2/3")
