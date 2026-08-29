"""The first-run banner: a host with no scanners must be told it needs setup,
not handed a scorecard full of amber about tooling.
"""

from __future__ import annotations

from gandalf import report
from gandalf.base import GateOutcome, GateResult
from gandalf.plugins import unavailable

P, W = GateOutcome.PASS, GateOutcome.WARN


def _missing(n: int) -> list[GateResult]:
    return [unavailable(f"g{i}", "not installed — skipped") for i in range(n)]


def test_no_banner_when_the_run_said_something_useful():
    ran = [GateResult(f"g{i}", P, 1.0, "clean") for i in range(10)]
    assert report.setup_banner(ran, False, False) == ""
    # a third missing is normal on any host — not a setup problem
    assert report.setup_banner(ran + _missing(4), False, True) == ""


def test_banner_when_most_gates_could_not_run():
    results = [GateResult("ruff", P, 1.0, "clean")] + _missing(9)
    out = report.setup_banner(results, False, True)
    assert "Most scanners are unavailable" in out and "9 of 10" in out
    assert "make tools" in out


def test_banner_when_nothing_ran_at_all():
    out = report.setup_banner(_missing(12), False, True)
    assert "No scanners available" in out
    assert "gandalf checked nothing" in out
    assert "not a quality signal" in out


def test_advice_matches_what_is_actually_missing():
    """With the image built, the gap is host-only toolchains — telling the user
    to run `make tools` again would be useless advice."""
    built = report.setup_banner(_missing(5), True, True)
    assert "make tools" not in built and "host-only" in built
    # No docker at all: say so, and note the image is never pulled behind you.
    no_docker = report.setup_banner(_missing(5), False, False)
    assert "install Docker" in no_docker and "never pulled" in no_docker


def test_empty_results_never_banner():
    assert report.setup_banner([], False, False) == ""


def test_verdict_line_does_not_claim_a_zero_score_when_nothing_ran():
    results = _missing(4)
    out = report.render_terminal("wt", results, report.aggregate(results), {}, {})
    assert "NOT RUN" in out and "0/100" not in out


def test_verdict_line_is_normal_when_something_ran():
    results = [GateResult("ruff", P, 1.0, "clean")] + _missing(2)
    out = report.render_terminal("wt", results, report.aggregate(results), {}, {})
    assert "100/100" in out and "GREEN" in out
