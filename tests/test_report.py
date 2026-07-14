"""Tests for verdict policy + report rendering (previously untested).
Run: pytest gandalf/test_report.py"""

from __future__ import annotations

from gandalf import report
from gandalf.base import GateOutcome, GateResult

P, W, F = GateOutcome.PASS, GateOutcome.WARN, GateOutcome.FAIL


# --- policy -----------------------------------------------------------------
def test_policy_from_config_precedence():
    p = report.Policy.from_config({"fail_on": "warn", "min_score": 70})
    assert p.fail_on is W and p.min_score == 70
    # CLI overrides file
    p = report.Policy.from_config(
        {"fail_on": "fail"}, cli_fail_on="warn", cli_min_score=50
    )
    assert p.fail_on is W and p.min_score == 50
    # junk min_score is clamped/ignored
    assert report.Policy.from_config({"min_score": "oops"}).min_score == 0
    assert report.Policy.from_config({"min_score": 500}).min_score == 100


def test_decide():
    default = report.Policy()
    assert report.decide(report.Verdict(P, 100), default)[0] is True
    assert (
        report.decide(report.Verdict(W, 80), default)[0] is True
    )  # warn passes by default
    assert report.decide(report.Verdict(F, 50), default)[0] is False
    strict = report.Policy(fail_on=W)
    assert report.decide(report.Verdict(W, 80), strict)[0] is False
    floor = report.Policy(min_score=90)
    assert report.decide(report.Verdict(P, 80), floor)[0] is False
    assert report.decide(report.Verdict(P, 95), floor)[0] is True


# --- rendering smoke --------------------------------------------------------
def _results():
    return [
        GateResult(
            "ruff",
            F,
            0.3,
            "ruff: 3 findings",
            [{"path": "a.py", "line": 5, "message": "x"}],
        ),
        GateResult("gitleaks", P, 1.0, "clean"),
        GateResult("mypy", W, 0.7, "2 type errors"),
    ]


def test_render_terminal_smoke():
    v = report.aggregate(_results())
    out = report.render_terminal("staged", _results(), v, {"summary": "hi"}, {})
    assert "GANDALF" in out and "ruff" in out and "gitleaks" in out
    assert str(v.score) in out


def test_render_html_smoke():
    v = report.aggregate(_results())
    html = report.render_html(
        "staged",
        _results(),
        v,
        {"summary": "**bold** summary", "remediation": ""},
        {"commit": {"short": "abc123", "subject": "fix"}},
    )
    assert html.startswith("<!DOCTYPE html>") and html.rstrip().endswith("</html>")
    assert "ruff" in html and "1 finding" in html  # findings <details>
    assert "<strong>bold</strong>" in html  # markdown rendered
    assert "abc123" in html  # commit metabar


def test_aggregate_edges():
    assert report.aggregate([]).outcome is W
    assert report.aggregate(_results()).outcome is F  # any fail → red


if __name__ == "__main__":
    test_policy_from_config_precedence()
    test_decide()
    test_render_terminal_smoke()
    test_render_html_smoke()
    test_aggregate_edges()
    print("ok")
