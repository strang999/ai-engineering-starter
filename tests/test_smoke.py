"""Lesson 0: the project runs end to end in mock mode, without a key."""

import re
import tomllib
from pathlib import Path

from support import STARTER_TAG
from support.contract import CONTRACT_VERSION
from support.demo import main as demo_main


def test_demo_prints_first_card_in_mock_mode(capsys):
    assert demo_main([]) == 0
    out = capsys.readouterr().out
    assert "T-0001" in out
    assert "замовлення: DEMO-1042" in out
    assert "provider=mock model=mock-1" in out
    assert "(simulated)" in out


def test_versions():
    assert CONTRACT_VERSION == "1.2"
    assert STARTER_TAG.startswith("l")


def test_requirements_txt_matches_the_lock_for_the_pip_path():
    """pip path (no uv): requirements.txt is `uv export` of this tag's uv.lock, regenerated on every tag."""
    root = Path(__file__).resolve().parent.parent
    pinned = dict(re.findall(r"^([A-Za-z0-9_.-]+)==([^\s;]+)", (root / "requirements.txt").read_text(encoding="utf-8"), re.M))
    lock = {p["name"]: p["version"] for p in tomllib.loads((root / "uv.lock").read_text(encoding="utf-8"))["package"]
            if "version" in p}
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    for dep in project["dependencies"] + ["pytest"]:
        name = re.match(r"[A-Za-z0-9_.-]+", dep).group(0).lower()
        assert name in pinned, f"{name} missing from requirements.txt: run uv export (README, pip path)"
    for name, version in pinned.items():
        assert lock.get(name) == version, f"requirements.txt has {name}=={version}, uv.lock has {lock.get(name)}"
