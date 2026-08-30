"""A gate that could not run is not a quality signal.

The distinction the rest of the suite leans on: `unavailable()` still produces
an amber 0.8 result, so every existing consumer (SARIF, JUnit, badge, the cache)
sees exactly what it saw before — but it carries a marker, and the aggregate
leaves it out of the composite and the verdict.
"""

from __future__ import annotations

from gandalf import report, severity, suppress
from gandalf.base import GateOutcome, GateResult
from gandalf.plugins import did_not_run, unavailable

P, W, F = GateOutcome.PASS, GateOutcome.WARN, GateOutcome.FAIL


def test_unavailable_is_still_an_amber_gate_result():
    """The wire shape is unchanged — only the out-of-band marker is new."""
    r = unavailable("trivy", "trivy unavailable — skipped")
    assert r.outcome is W and r.score == 0.8 and r.name == "trivy"
    assert did_not_run(r)
    assert not did_not_run(GateResult("ruff", W, 0.8, "ruff: 1 issue"))


def test_gate_outcome_gains_no_member():
    """Adding an enum member would break the cache, SARIF's level map, JUnit and
    the badge — all of which map the three outcomes exhaustively."""
    assert [o.value for o in GateOutcome] == ["pass", "warn", "fail"]


def test_unavailable_gates_are_left_out_of_the_score():
    ran = [GateResult("ruff", P, 1.0, "clean"), GateResult("mypy", P, 1.0, "clean")]
    assert report.aggregate(ran).score == 100
    # Three missing scanners must not drag a clean repo to 88.
    with_missing = ran + [unavailable(n, "not installed") for n in ("a", "b", "c")]
    v = report.aggregate(with_missing)
    assert v.score == 100 and v.outcome is P


def test_unavailable_gates_do_not_colour_the_verdict():
    """The reported bug: a scanner that is merely absent must not amber the run."""
    results = [GateResult("ruff", P, 1.0, "clean"), unavailable("trivy", "missing")]
    assert report.aggregate(results).outcome is P


def test_a_gate_that_actually_failed_still_reddens():
    results = [
        GateResult("ruff", F, 0.0, "3 findings"),
        unavailable("trivy", "missing"),
    ]
    v = report.aggregate(results)
    assert v.outcome is F and v.score == 0


def test_nothing_ran_at_all_is_amber_and_scoreless():
    """No score is honest here; inventing 80/100 from the 0.8 sentinels is not."""
    v = report.aggregate([unavailable(n, "not installed") for n in ("a", "b")])
    assert v.outcome is W and v.score == 0


def test_category_with_nothing_run_reports_no_percentage():
    outcome, pct = report._group_outcome_and_pct([unavailable("trivy", "missing")])
    assert pct is None and outcome is W
    _, pct = report._group_outcome_and_pct([GateResult("ruff", P, 1.0, "clean")])
    assert pct == 100


def test_terminal_render_marks_and_counts_them():
    results = [GateResult("ruff", P, 1.0, "clean"), unavailable("trivy", "missing")]
    out = report.render_terminal("wt", results, report.aggregate(results), {}, {})
    assert report._SKIP_EMOJI in out
    assert "1 of 2 gate(s) could not run" in out


def test_html_render_labels_them_not_run():
    results = [GateResult("ruff", P, 1.0, "clean"), unavailable("trivy", "missing")]
    out = report.render_html("wt", results, report.aggregate(results), {}, {})
    assert "NOT RUN" in out and "not run" in out


def test_marker_survives_severity_reweighting():
    r = unavailable("trivy", "missing")
    assert did_not_run(severity.reweight(r))


def test_marker_survives_partial_suppression():
    """A marked result carries no findings, so suppression returns it untouched —
    and a partially-suppressed real gate keeps whatever it had."""
    sup = suppress.build({"rules": ["ruff:E501"]}, None)
    r = GateResult(
        "ruff",
        W,
        0.5,
        "2 issues",
        [{"path": "a.py", "code": "E501"}, {"path": "b.py", "code": "F401"}],
    )
    r._unavailable = False
    assert not did_not_run(sup.apply(r))
    assert sup.apply(unavailable("trivy", "missing")) is not None


# --- out-of-band attributes survive a rebuild -------------------------------
def _decorated() -> GateResult:
    """A result as the runner hands it on: score-carrying fields plus the
    metadata it attaches out of band."""
    r = GateResult("trivy", W, 0.5, "2 vulns", [{"severity": "HIGH", "code": "X"}])
    r._blocking, r._category, r._duration = True, "Dependencies", 1.25
    return r


def test_reweighting_keeps_the_duration():
    """It never did: --severity-weight wrote a null duration for every gate."""
    out = severity.reweight(_decorated())
    assert out._duration == 1.25
    assert out._blocking is True and out._category == "Dependencies"


def test_partial_suppression_keeps_the_duration():
    sup = suppress.build({"rules": ["trivy::*"]}, None)
    r = _decorated()
    r.findings.append({"severity": "LOW", "code": "Y", "path": "b.py"})
    out = sup.apply(r)
    assert out._duration == 1.25 and out._blocking is True


def test_full_suppression_keeps_the_metadata_too():
    sup = suppress.build({"rules": ["trivy"]}, None)
    out = sup.apply(_decorated())
    assert out.outcome is P  # everything muted
    assert out._duration == 1.25 and out._category == "Dependencies"


def test_carry_over_ignores_the_dataclass_fields():
    """Only runner metadata travels — the rebuilt score/summary must stand."""
    from gandalf.plugins import carry_over

    src = _decorated()
    dst = GateResult("trivy", P, 1.0, "rebuilt", [])
    carry_over(src, dst)
    assert dst.score == 1.0 and dst.summary == "rebuilt" and dst.findings == []
    assert dst._duration == 1.25
