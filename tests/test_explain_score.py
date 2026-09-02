"""--explain-score: the composite is an unweighted mean, which is simple enough
that nobody could reproduce it without reading report.py. Show the addends.
"""

from __future__ import annotations

from gandalf import render_text, report, severity
from gandalf.base import GateOutcome, GateResult
from gandalf.plugins import unavailable

P, W, F = GateOutcome.PASS, GateOutcome.WARN, GateOutcome.FAIL


def test_lists_every_counted_gate_with_its_contribution():
    results = [
        GateResult("ruff", P, 1.0, "clean"),
        GateResult("mypy", W, 0.5, "2 errors"),
    ]
    out = render_text.explain_score(results, report.aggregate(results))
    assert "75/100" in out
    assert "ruff" in out and "mypy" in out
    # each of two gates contributes half of its score
    assert "50.0" in out and "25.0" in out
    assert "2 gate(s) counted" in out and "mean 0.750" in out


def test_names_the_gates_left_out_and_why():
    results = [GateResult("ruff", P, 1.0, "clean"), unavailable("trivy", "missing")]
    out = render_text.explain_score(results, report.aggregate(results))
    assert "1 not counted (could not run): trivy" in out
    assert "1 gate(s) counted" in out


def test_shows_the_gates_own_score_when_severity_reweighted():
    """The weighted number is the one a user cannot derive from the tool's output,
    so hiding what the gate itself said makes the explanation useless."""
    r = GateResult(
        "trivy", F, 0.9, "vulns", [{"severity": "CRITICAL"}, {"severity": "HIGH"}]
    )
    weighted = severity.reweight(r)
    assert weighted.score != r.score
    out = render_text.explain_score([weighted], report.aggregate([weighted]))
    assert "gate scored 0.90" in out and "severity-weighted" in out


def test_no_note_when_reweighting_changed_nothing():
    r = GateResult("ruff", W, 0.5, "2 issues", [{"message": "no severity here"}])
    same = severity.reweight(r)
    out = render_text.explain_score([same], report.aggregate([same]))
    assert "severity-weighted" not in out


def test_nothing_ran_says_so_rather_than_averaging_nothing():
    results = [unavailable("a", "x"), unavailable("b", "y")]
    out = render_text.explain_score(results, report.aggregate(results))
    assert "nothing to average" in out
    assert "gate(s) counted" not in out


def test_the_arithmetic_shown_is_the_arithmetic_used():
    results = [
        GateResult("a", P, 1.0, ""),
        GateResult("b", W, 0.6, ""),
        GateResult("c", F, 0.2, ""),
        unavailable("d", "missing"),
    ]
    v = report.aggregate(results)
    out = render_text.explain_score(results, v)
    assert f"→ {v.score}/100" in out
    assert v.score == round((1.0 + 0.6 + 0.2) / 3 * 100)
