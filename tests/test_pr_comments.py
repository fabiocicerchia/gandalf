"""Tests for PR review comment building. Run: pytest gandalf/test_pr_comments.py"""

from __future__ import annotations

from gandalf import pr_comments, report
from gandalf.base import GateOutcome, GateResult

_RESULTS = [
    GateResult(
        "ruff",
        GateOutcome.FAIL,
        0.3,
        "ruff",
        [
            {
                "filename": "a.py",
                "code": "E501",
                "message": "long",
                "location": {"row": 12},
            },
            {
                "filename": "a.py",
                "code": "E502",
                "message": "backslash",
                "location": {"row": 12},
            },
            {"path": "b.py", "rule_id": "F401", "message": "unused", "line": 3},
        ],
    ),
    GateResult(
        "mypy", GateOutcome.WARN, 0.7, "mypy", [{"error": "a.py:8: error: bad"}]
    ),
    GateResult("gitleaks", GateOutcome.PASS, 1.0, "clean", []),
]


def test_same_line_findings_merge():
    comments, _ = pr_comments.build(_RESULTS, ["a.py", "b.py"])
    at = {(c["path"], c["line"]): c for c in comments}
    assert (a := at[("a.py", 12)])
    assert "E501" in a["body"] and "E502" in a["body"]  # merged
    assert a["side"] == "RIGHT"
    assert ("b.py", 3) in at  # separate line, separate comment


def test_unanchorable_and_passing_go_to_overflow():
    _, overflow = pr_comments.build(_RESULTS, ["a.py", "b.py"])
    # mypy finding has no structured line → overflow; passing gate contributes nothing
    assert any("mypy" in o for o in overflow)
    assert not any("gitleaks" in o for o in overflow)


def test_changed_set_excludes_off_diff_lines():
    comments, overflow = pr_comments.build(_RESULTS, ["a.py"])  # b.py not in diff
    assert all(c["path"] == "a.py" for c in comments)
    assert any("b.py" in o for o in overflow)


def test_review_payload_shape():
    v = report.aggregate(_RESULTS)
    p = pr_comments.review_payload(_RESULTS, v, ["a.py", "b.py"])
    assert p["event"] == "COMMENT"  # never REQUEST_CHANGES (own-PR safe)
    assert isinstance(p["comments"], list) and p["comments"]
    assert "gandalf" in p["body"] and "67/100" in p["body"]


def test_post_without_token_is_safe():
    ok, msg = pr_comments.post("", 1, {"event": "COMMENT", "comments": []}, "")
    assert ok is False and "skipped" in msg


if __name__ == "__main__":
    test_same_line_findings_merge()
    test_unanchorable_and_passing_go_to_overflow()
    test_changed_set_excludes_off_diff_lines()
    test_review_payload_shape()
    test_post_without_token_is_safe()
    print("ok")
