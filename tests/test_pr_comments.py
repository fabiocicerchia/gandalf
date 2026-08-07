"""Tests for PR review comment building. Run: pytest gandalf/test_pr_comments.py"""

from __future__ import annotations

import os

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


def test_message_only_location_still_anchors():
    # mypy carries "a.py:8:" in its text, not in structured fields
    comments, _ = pr_comments.build(_RESULTS, ["a.py", "b.py"])
    assert ("a.py", 8) in {(c["path"], c["line"]) for c in comments}


def test_passing_gate_contributes_nothing():
    _, overflow = pr_comments.build(_RESULTS, ["a.py", "b.py"])
    assert not any("gitleaks" in o for o in overflow)
    # no location anywhere → overflow, nothing dropped
    prose = [GateResult("codeql", GateOutcome.WARN, 0.5, "x", [{"message": "vague"}])]
    inline, over = pr_comments.build(prose, ["a.py"])
    assert not inline and any("vague" in o for o in over)


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


_DIFF = """\
diff --git a/a.py b/a.py
--- a/a.py
+++ b/a.py
@@ -9,3 +11,4 @@ def f():
     ctx
-    gone
+    added at 12
+    added at 13
     ctx
"""


def test_added_lines_tracks_right_hand_numbering():
    assert pr_comments.added_lines(_DIFF) == {"a.py": {12, 13}}
    assert pr_comments.added_lines("") == {}  # unknown, not "nothing added"


def test_diff_restricts_anchors_to_added_lines():
    # line 12 is added → inline; line 3 of b.py is not in the diff at all
    comments, overflow = pr_comments.build(_RESULTS, ["a.py", "b.py"], _DIFF)
    assert [(c["path"], c["line"]) for c in comments] == [("a.py", 12)]
    assert any("b.py" in o for o in overflow)


def test_container_paths_are_rebased_repo_relative():
    results = [
        GateResult(
            "ruff",
            GateOutcome.FAIL,
            0.3,
            "ruff",
            [{"path": "/src/a.py", "message": "long", "line": 12}],
        )
    ]
    comments, _ = pr_comments.build(results, ["a.py"], _DIFF, workdir="/src")
    assert [(c["path"], c["line"]) for c in comments] == [("a.py", 12)]


def test_overflow_is_collapsed():
    v = report.aggregate(_RESULTS)
    body = pr_comments.review_payload(_RESULTS, v, ["a.py"], diff=_DIFF)["body"]
    assert "<details>" in body and body.count("</details>") == 1
    head, rest = body.split("</summary>", 1)
    assert "Other findings — " in head
    assert rest.startswith("\n\n- ")  # blank line, else GitHub won't render the list


def test_body_carries_marker_and_update_stamp():
    v = report.aggregate(_RESULTS)
    p = pr_comments.review_payload(_RESULTS, v, ["a.py", "b.py"])
    assert "Last updated " in p["body"] and "UTC" in p["body"]
    assert pr_comments._ours(p["body"])  # a re-run finds and edits this one
    assert pr_comments._ours(p["comments"][0]["body"])
    assert not pr_comments._ours("someone else's comment")


def _thread(tid, key, resolved=False):
    return {"id": tid, "resolved": resolved, "key": key}


def test_reconcile_resolves_obsolete_and_keeps_current():
    want = [
        {"path": "a.py", "line": 12, "body": "still there"},
        {"path": "a.py", "line": 20, "body": "brand new"},
    ]
    threads = [
        _thread("T1", ("a.py", 12, "still there")),  # unchanged → left alone
        _thread("T2", ("a.py", 99, "fixed")),  # gone → resolve, never delete
        _thread("T3", ("a.py", 20, "brand new"), resolved=True),  # came back
    ]
    stale, new = pr_comments._reconcile(threads, want)
    assert stale == ["T2"]
    # T3 is resolved, so it counts as absent — the finding gets a fresh comment
    assert [c["line"] for c in new] == [20]


def test_post_without_token_is_safe():
    ok, msg = pr_comments.post("", 1, {"event": "COMMENT", "comments": []}, "")
    assert ok is False and "skipped" in msg


def test_brand_defaults_and_override():
    v = report.aggregate(_RESULTS)
    # default branding
    p = pr_comments.review_payload(_RESULTS, v, ["a.py", "b.py"])
    assert p["body"].splitlines()[0].startswith("## 🧙 gandalf — ")
    assert "**gandalf**" in p["comments"][0]["body"]
    # env override rebrands the header + per-finding prefix
    saved = {k: os.environ.get(k) for k in ("GANDALF_PR_TITLE", "GANDALF_PR_ICON")}
    try:
        os.environ["GANDALF_PR_TITLE"] = "acme-bot"
        os.environ["GANDALF_PR_ICON"] = "🚀"
        p = pr_comments.review_payload(_RESULTS, v, ["a.py", "b.py"])
        assert p["body"].splitlines()[0].startswith("## 🚀 acme-bot — ")
        assert "**acme-bot**" in p["comments"][0]["body"]
        assert "gandalf" not in p["body"].splitlines()[0]
    finally:
        for k, val in saved.items():
            os.environ[k] = val if val is not None else ""
            if val is None:
                del os.environ[k]


if __name__ == "__main__":
    test_same_line_findings_merge()
    test_message_only_location_still_anchors()
    test_passing_gate_contributes_nothing()
    test_changed_set_excludes_off_diff_lines()
    test_added_lines_tracks_right_hand_numbering()
    test_diff_restricts_anchors_to_added_lines()
    test_container_paths_are_rebased_repo_relative()
    test_overflow_is_collapsed()
    test_body_carries_marker_and_update_stamp()
    test_review_payload_shape()
    test_reconcile_resolves_obsolete_and_keeps_current()
    test_post_without_token_is_safe()
    test_brand_defaults_and_override()
    print("ok")
