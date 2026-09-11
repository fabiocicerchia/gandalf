"""Tests for gate scheduling: heaviest first. Run: pytest tests/test_schedule.py"""

from __future__ import annotations

from gandalf import schedule


class _Gate:
    """The only two things the scheduler reads off a gate."""

    def __init__(self, name: str, cost: float | str | None = None) -> None:
        self.name = name
        if cost is not None:
            self.cost = cost


def _names(gates: list[_Gate], recorded: dict[str, float] | None = None) -> list[str]:
    return [g.name for g in schedule.order(gates, recorded)]


def test_known_heavy_gates_go_first() -> None:
    """Discovery order is alphabetical, which puts trivy behind bandit. With
    concurrency bounded, that is the whole scan waiting on the tail."""
    gates = [_Gate(n) for n in ("bandit", "ruff", "trivy", "codeql", "yamllint")]
    assert _names(gates) == ["codeql", "trivy", "bandit", "yamllint", "ruff"]


def test_a_measurement_beats_the_prior() -> None:
    """The prior says codeql is the expensive one. This repository has no CodeQL
    database and a very large test suite, and the recorded run knows that."""
    gates = [_Gate("codeql"), _Gate("tests")]
    assert _names(gates, {"codeql": 2.0, "tests": 400.0}) == ["tests", "codeql"]


def test_a_gate_may_declare_its_own_cost() -> None:
    """The plugin-friendly escape hatch: a third-party gate nobody has a prior
    for can say what it costs."""
    assert _names([_Gate("ruff"), _Gate("custom", cost=999)]) == ["custom", "ruff"]
    # ...but a measurement still wins, because it was actually observed.
    assert _names([_Gate("ruff"), _Gate("custom", cost=999)], {"custom": 0.1}) == ["ruff", "custom"]


def test_an_unknown_gate_gets_the_default() -> None:
    assert schedule.cost(_Gate("nobody-has-heard-of-this")) == schedule.DEFAULT_COST


def test_a_nonsense_cost_is_scheduled_not_rejected() -> None:
    """A gate is a plugin; a bad `cost` must degrade to the prior, never raise
    in the middle of building the run."""
    assert schedule.cost(_Gate("ruff", cost="soon")) == schedule._PRIOR["ruff"]


def test_ties_break_by_name_so_the_order_is_reproducible() -> None:
    """Two --debug logs from the same repo should diff to nothing."""
    gates = [_Gate(n) for n in ("zulu", "alpha", "mike")]
    assert _names(gates) == ["alpha", "mike", "zulu"]


def test_ordering_keeps_every_gate() -> None:
    gates = [_Gate(n) for n in ("ruff", "trivy", "mystery")]
    assert sorted(g.name for g in schedule.order(gates)) == ["mystery", "ruff", "trivy"]
