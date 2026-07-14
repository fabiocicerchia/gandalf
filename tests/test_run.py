"""Tests for the gate runner: bounded concurrency + error isolation.
Run: pytest gandalf/test_run.py"""

from __future__ import annotations

import asyncio

from gandalf import plugins
from gandalf.__main__ import (
    _gate_timeout,
    _resolve_concurrency,
    _run_fixers,
    _run_gates,
)
from gandalf.base import GateContext, GateOutcome, GateResult
from gandalf.config import Config


class _Slow:
    def __init__(self, name, tracker):
        self.name = name
        self.blocking = False
        self._t = tracker

    async def run(self, ctx):
        self._t["live"] += 1
        self._t["peak"] = max(self._t["peak"], self._t["live"])
        await asyncio.sleep(0.02)
        self._t["live"] -= 1
        return GateResult(self.name, GateOutcome.PASS, 1.0, "ok")


class _Broken:
    name = "broken"
    blocking = False

    async def run(self, ctx):
        raise RuntimeError("boom")


_CTX = GateContext(repo=".", workdir=".")


def test_concurrency_is_bounded():
    t = {"live": 0, "peak": 0}
    gates = [_Slow(f"g{i}", t) for i in range(10)]
    res = asyncio.run(_run_gates(gates, _CTX, limit=3))
    assert len(res) == 10 and t["peak"] == 3


def test_unbounded_runs_all_at_once():
    t = {"live": 0, "peak": 0}
    gates = [_Slow(f"g{i}", t) for i in range(6)]
    asyncio.run(_run_gates(gates, _CTX, limit=0))
    assert t["peak"] == 6


def test_broken_gate_degrades_to_warn():
    res = asyncio.run(_run_gates([_Broken()], _CTX, limit=1))
    assert res[0].outcome is GateOutcome.WARN and "boom" in res[0].summary


class _Fixer:
    name = "fixme"
    blocking = False

    async def fix(self, ctx):
        return (True, "did a thing")


class _NoFix:
    name = "nofix"
    blocking = False

    async def run(self, ctx):
        return GateResult(self.name, GateOutcome.PASS, 1.0, "ok")


class _BadFixer:
    name = "badfix"
    blocking = False

    async def fix(self, ctx):
        raise RuntimeError("nope")


def test_run_fixers_collects_and_skips():
    res = asyncio.run(_run_fixers([_Fixer(), _NoFix()], _CTX))
    # only the gate exposing fix() is run
    assert res == [("fixme", True, "did a thing")]


def test_run_fixers_isolates_errors():
    res = asyncio.run(_run_fixers([_BadFixer()], _CTX))
    assert res[0][0] == "badfix" and res[0][1] is False and "nope" in res[0][2]


def test_resolve_concurrency_precedence(monkeypatch):
    monkeypatch.delenv("GANDALF_CONCURRENCY", raising=False)
    assert _resolve_concurrency(5, Config()) == 5  # cli wins
    assert _resolve_concurrency(None, Config({"concurrency": 7})) == 7  # then config
    monkeypatch.setenv("GANDALF_CONCURRENCY", "4")
    assert (
        _resolve_concurrency(None, Config({"concurrency": 7})) == 4
    )  # env beats config


def test_gate_timeout_resolution():
    ts = {"default": 60, "semgrep": 300}
    assert _gate_timeout("semgrep", ts) == 300  # per-gate key wins
    assert _gate_timeout("ruff", ts) == 60  # falls to default
    assert _gate_timeout("ruff", {}) is None  # no section → global default
    assert _gate_timeout("x", {"x": "abc"}) is None  # junk ignored


def test_per_gate_timeout_visible_in_run():
    seen = {}

    class _Probe:
        def __init__(self, n):
            self.name = n
            self.blocking = False

        async def run(self, ctx):
            seen[self.name] = plugins.GATE_TIMEOUT.get()
            return GateResult(self.name, GateOutcome.PASS, 1.0, "ok")

    ts = {"default": 60, "semgrep": 300}
    asyncio.run(
        _run_gates([_Probe("semgrep"), _Probe("ruff")], _CTX, limit=2, timeouts=ts)
    )
    assert seen == {"semgrep": 300, "ruff": 60}


if __name__ == "__main__":
    import os

    os.environ.pop("GANDALF_CONCURRENCY", None)
    test_concurrency_is_bounded()
    test_unbounded_runs_all_at_once()
    test_broken_gate_degrades_to_warn()
    test_run_fixers_collects_and_skips()
    test_run_fixers_isolates_errors()
    test_gate_timeout_resolution()
    test_per_gate_timeout_visible_in_run()
    assert _resolve_concurrency(5, Config()) == 5
    print("ok")
