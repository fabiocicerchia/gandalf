"""The first-run banner: a host with no scanners must be told it needs setup,
not handed a scorecard full of amber about tooling.
"""

from __future__ import annotations

from gandalf import render_text, report
from gandalf.base import GateOutcome, GateResult
from gandalf.plugins import unavailable

P, W = GateOutcome.PASS, GateOutcome.WARN


def _missing(n: int) -> list[GateResult]:
    return [unavailable(f"g{i}", "not installed — skipped") for i in range(n)]


def test_no_banner_when_the_run_said_something_useful() -> None:
    ran = [GateResult(f"g{i}", P, 1.0, "clean") for i in range(10)]
    assert render_text.setup_banner(ran, False, False) == ""
    # a third missing is normal on any host — not a setup problem
    assert render_text.setup_banner(ran + _missing(4), False, True) == ""


def test_banner_when_most_gates_could_not_run() -> None:
    results = [GateResult("ruff", P, 1.0, "clean"), *_missing(9)]
    out = render_text.setup_banner(results, False, True)
    assert "Most scanners are unavailable" in out
    assert "9 of 10" in out
    assert "make tools" in out


def test_banner_when_nothing_ran_at_all() -> None:
    out = render_text.setup_banner(_missing(12), False, True)
    assert "No scanners available" in out
    assert "gandalf checked nothing" in out
    assert "not a quality signal" in out


def test_advice_matches_what_is_actually_missing() -> None:
    """With the image built, the gap is host-only toolchains — telling the user
    to run `make tools` again would be useless advice."""
    built = render_text.setup_banner(_missing(5), True, True)
    assert "make tools" not in built
    assert "host-only" in built
    # No docker at all: say so, and note the image is never pulled behind you.
    no_docker = render_text.setup_banner(_missing(5), False, False)
    assert "install Docker" in no_docker
    assert "never pulled" in no_docker


def test_empty_results_never_banner() -> None:
    assert render_text.setup_banner([], False, False) == ""


def test_verdict_line_does_not_claim_a_zero_score_when_nothing_ran() -> None:
    results = _missing(4)
    out = render_text.render_terminal("wt", results, report.aggregate(results), {}, {})
    assert "NOT RUN" in out
    assert "0/100" not in out


def test_verdict_line_is_normal_when_something_ran() -> None:
    results = [GateResult("ruff", P, 1.0, "clean"), *_missing(2)]
    out = render_text.render_terminal("wt", results, report.aggregate(results), {}, {})
    assert "100/100" in out
    assert "GREEN" in out
