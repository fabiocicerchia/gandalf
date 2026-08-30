"""The `tests` gate must tell a suite that failed apart from a pytest that was
never installed. A config file in the tree says the repo uses pytest; it does
not say the module is importable, and `python -m pytest` without it exits
non-zero with a message that reads exactly like a red suite.
"""

from __future__ import annotations

import asyncio

from gandalf.base import GateContext, GateOutcome
from gandalf.plugins import discover_gates

GATE = {g.name: g for g in discover_gates()}["tests"]


def _run(workdir: str):
    ctx = GateContext(repo=workdir, workdir=workdir, changed_files=[])
    return asyncio.run(GATE.run(ctx))


def test_missing_pytest_is_amber_not_red(tmp_path, monkeypatch):
    """pyproject.toml present, pytest absent from both the interpreter and PATH."""
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'x'\n")
    monkeypatch.setattr(
        "importlib.util.find_spec", lambda name, *a, **k: None, raising=True
    )
    monkeypatch.setattr("shutil.which", lambda binary, *a, **k: None, raising=True)
    r = _run(str(tmp_path))
    assert r.outcome is GateOutcome.WARN, r.summary
    assert "not installed" in r.summary and "skipped" in r.summary


def test_falls_back_to_the_pytest_binary_when_the_module_is_absent(
    tmp_path, monkeypatch
):
    """A pytest on PATH still runs even when gandalf's own interpreter lacks the
    module — the config file's preference must not strand a usable binary."""
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'x'\n")
    monkeypatch.setattr(
        "importlib.util.find_spec", lambda name, *a, **k: None, raising=True
    )
    monkeypatch.setattr(
        "shutil.which", lambda binary, *a, **k: "/usr/bin/pytest", raising=True
    )
    seen: dict = {}

    async def fake_exec(*argv, **kwargs):
        seen["argv"] = argv
        raise AssertionError("stop before spawning")

    monkeypatch.setattr(asyncio.subprocess, "create_subprocess_exec", fake_exec)
    monkeypatch.setattr("asyncio.create_subprocess_exec", fake_exec)
    try:
        _run(str(tmp_path))
    except AssertionError:
        pass
    assert seen["argv"][0] == "pytest"
