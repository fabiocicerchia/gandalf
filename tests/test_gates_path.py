"""GANDALF_GATES_PATH is a trust boundary: it imports and executes arbitrary
Python, and a gate loaded through it can replace a built-in. The replacement is
legitimate — it is how you swap a scanner — but it must never be silent.
"""

from __future__ import annotations

import os

from gandalf import plugins

PLUGIN = """
from gandalf.base import GateContext, GateOutcome, GateResult


class FakeGitleaks:
    name = "gitleaks"
    blocking = True

    async def run(self, ctx):
        return GateResult(self.name, GateOutcome.PASS, 1.0, "clean")
"""


def _with_path(tmp_path, monkeypatch, body: str, name: str = "plug.py"):
    (tmp_path / name).write_text(body)
    monkeypatch.setitem(os.environ, "GANDALF_GATES_PATH", str(tmp_path))
    return {g.name: g for g in plugins.discover_gates()}


def test_overriding_a_builtin_is_announced(tmp_path, monkeypatch, capsys):
    gates = _with_path(tmp_path, monkeypatch, PLUGIN)
    # the override still takes effect — this is a supported extension point
    assert type(gates["gitleaks"]).__name__ == "FakeGitleaks"
    err = capsys.readouterr().err
    assert "gitleaks" in err and "overridden" in err
    assert "GANDALF_GATES_PATH" in err


def test_a_new_gate_is_not_announced(tmp_path, monkeypatch, capsys):
    body = PLUGIN.replace('name = "gitleaks"', 'name = "wholly_novel_gate"')
    gates = _with_path(tmp_path, monkeypatch, body)
    assert "wholly_novel_gate" in gates
    assert "overridden" not in capsys.readouterr().err


def test_builtin_gates_never_warn_about_each_other(monkeypatch, capsys):
    monkeypatch.delenv("GANDALF_GATES_PATH", raising=False)
    plugins.discover_gates()
    assert capsys.readouterr().err == ""
