"""Tests for verdict policy + report rendering (previously untested).
Run: pytest gandalf/test_report.py"""

from __future__ import annotations

from gandalf import render_html, render_text, report
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
    out = render_text.render_terminal("staged", _results(), v, {"summary": "hi"}, {})
    assert "GANDALF" in out and "ruff" in out and "gitleaks" in out
    assert str(v.score) in out


def test_render_html_smoke():
    v = report.aggregate(_results())
    html = render_html.render_html(
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


def test_format_delta():
    assert report.format_delta(None) == ""
    assert report.format_delta(5) == " (+5 vs prev)"
    assert report.format_delta(-3) == " (-3 vs prev)"
    assert report.format_delta(0) == " (+0 vs prev)"


def test_render_terminal_shows_delta():
    v = report.aggregate(_results())
    out = render_text.render_terminal(
        "staged", _results(), v, {"summary": "hi"}, {"score_delta": -7}
    )
    assert "(-7 vs prev)" in out


def test_render_html_shows_delta():
    v = report.aggregate(_results())
    html = render_html.render_html(
        "staged", _results(), v, {"summary": "hi"}, {"score_delta": 4}
    )
    assert "(+4 vs prev)" in html


def test_render_html_has_rag_filter_buttons():
    v = report.aggregate(_results())
    out = render_html.render_html("staged", _results(), v, {"summary": "hi"})
    assert 'data-filter="fail"' in out
    assert 'data-filter="pass"' in out
    assert 'class="filter-btn active" data-filter="all"' in out


def test_diff_html_empty_is_blank():
    assert render_html._diff_html("") == ""
    assert render_html._diff_html("   \n") == ""


def test_diff_html_colors_added_and_removed_lines():
    diff = "@@ -1,2 +1,2 @@\n-old line\n+new line\n context\n"
    out = render_html._diff_html(diff)
    assert '<span class="diff-hunk">@@ -1,2 +1,2 @@</span>' in out
    assert '<span class="diff-del">-old line</span>' in out
    assert '<span class="diff-add">+new line</span>' in out
    assert "<details" in out and "View raw diff" in out


def test_diff_html_ignores_file_header_markers():
    diff = "--- a/x.py\n+++ b/x.py\n@@ -1 +1 @@\n-old\n+new\n"
    out = render_html._diff_html(diff)
    assert '<span class="diff-del">--- a/x.py</span>' not in out
    assert '<span class="diff-add">+++ b/x.py</span>' not in out


def test_render_html_embeds_diff_view():
    v = report.aggregate(_results())
    out = render_html.render_html(
        "staged", _results(), v, {"summary": "hi"}, diff="+added line\n"
    )
    assert '<details class="diff-view">' in out and "added line" in out


def test_render_html_without_diff_omits_diff_view():
    v = report.aggregate(_results())
    out = render_html.render_html("staged", _results(), v, {"summary": "hi"})
    assert '<details class="diff-view">' not in out


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
