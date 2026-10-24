"""doctor.py checks work without running the whole suite again."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("doctor", ROOT / "scripts" / "doctor.py")
doctor = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(doctor)


def test_doctor_finds_repo_root_and_python():
    assert doctor.check_root()[0] == "OK"
    status, text = doctor.check_python()
    assert "Python 3." in text and status in ("OK", "WARN", "FAIL")


def test_pip_path_is_warn_not_fail(monkeypatch):
    """Corporate laptops: no uv and a newer Python must not stop the course (WARN, exit code 0)."""
    monkeypatch.setattr(doctor.shutil, "which", lambda name: None)
    assert doctor.check_uv()[0] == "WARN"
    assert doctor.check_tool("git")[0] == "FAIL"
    assert doctor.check_python(SimpleNamespace(major=3, minor=13))[0] == "WARN"
    assert doctor.check_python(SimpleNamespace(major=3, minor=12))[0] == "OK"
    assert doctor.check_python(SimpleNamespace(major=3, minor=11))[0] == "FAIL"


def test_doctor_without_tests_prints_report(capsys):
    doctor.main(["--skip-tests"])
    out = capsys.readouterr().out
    assert out.startswith("doctor · ")
    assert "PYTHONUTF8=" in out
