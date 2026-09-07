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
    GateResult("mypy", GateOutcome.WARN, 0.7, "mypy", [{"error": "a.py:8: error: bad"}]),
    GateResult("gitleaks", GateOutcome.PASS, 1.0, "clean", []),
]


def test_same_line_findings_merge() -> None:
    comments, _ = pr_comments.build(_RESULTS, ["a.py", "b.py"])
    at = {(c["path"], c["line"]): c for c in comments}
    assert (a := at[("a.py", 12)])
    assert "E501" in a["body"]
    assert "E502" in a["body"]  # merged
    assert a["side"] == "RIGHT"
    assert ("b.py", 3) in at  # separate line, separate comment


def test_message_only_location_still_anchors() -> None:
    # mypy carries "a.py:8:" in its text, not in structured fields
    comments, _ = pr_comments.build(_RESULTS, ["a.py", "b.py"])
    assert ("a.py", 8) in {(c["path"], c["line"]) for c in comments}


def test_passing_gate_contributes_nothing() -> None:
    _, overflow = pr_comments.build(_RESULTS, ["a.py", "b.py"])
    assert not any("gitleaks" in o for o in overflow)
    # no location anywhere → overflow, nothing dropped
    prose = [GateResult("codeql", GateOutcome.WARN, 0.5, "x", [{"message": "vague"}])]
    inline, over = pr_comments.build(prose, ["a.py"])
    assert not inline
    assert any("vague" in o for o in over)


def test_changed_set_excludes_off_diff_lines() -> None:
    comments, overflow = pr_comments.build(_RESULTS, ["a.py"])  # b.py not in diff
    assert all(c["path"] == "a.py" for c in comments)
    assert any("b.py" in o for o in overflow)


def test_review_payload_shape() -> None:
    v = report.aggregate(_RESULTS)
    p = pr_comments.review_payload(_RESULTS, v, ["a.py", "b.py"])
    assert p["event"] == "COMMENT"  # never REQUEST_CHANGES (own-PR safe)
    assert isinstance(p["comments"], list)
    assert p["comments"]
    assert "gandalf" in p["body"]
    assert "67/100" in p["body"]


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


def test_added_lines_tracks_right_hand_numbering() -> None:
    assert pr_comments.added_lines(_DIFF) == {"a.py": {12, 13}}
    assert pr_comments.added_lines("") == {}  # unknown, not "nothing added"


def test_diff_restricts_anchors_to_added_lines() -> None:
    # line 12 is added → inline; line 3 of b.py is not in the diff at all
    comments, overflow = pr_comments.build(_RESULTS, ["a.py", "b.py"], _DIFF)
    assert [(c["path"], c["line"]) for c in comments] == [("a.py", 12)]
    assert any("b.py" in o for o in overflow)


def test_container_paths_are_rebased_repo_relative() -> None:
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


def test_overflow_is_collapsed() -> None:
    v = report.aggregate(_RESULTS)
    body = pr_comments.review_payload(_RESULTS, v, ["a.py"], diff=_DIFF)["body"]
    assert "<details>" in body
    assert body.count("</details>") == 1
    head, rest = body.split("</summary>", 1)
    assert "Other findings — " in head
    assert rest.startswith("\n\n- ")  # blank line, else GitHub won't render the list


def test_body_carries_marker_and_update_stamp() -> None:
    v = report.aggregate(_RESULTS)
    p = pr_comments.review_payload(_RESULTS, v, ["a.py", "b.py"])
    assert "Last updated " in p["body"]
    assert "UTC" in p["body"]
    assert pr_comments._ours(p["body"])  # a re-run finds and edits this one
    assert pr_comments._ours(p["comments"][0]["body"])
    assert not pr_comments._ours("someone else's comment")


def _thread(tid, key, resolved: bool = False):
    return {"id": tid, "resolved": resolved, "key": key}


def test_reconcile_resolves_obsolete_and_keeps_current() -> None:
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


def test_post_without_token_is_safe() -> None:
    ok, msg = pr_comments.post("", 1, {"event": "COMMENT", "comments": []}, "")
    assert ok is False
    assert "skipped" in msg


def test_brand_defaults_and_override() -> None:
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


# --- one-click fixes ---------------------------------------------------------
# A finding whose tool ships the replacement text becomes a ```suggestion block
# on the comment, so the reviewer commits the fix from the PR page.


def _fixable(row, col, end_col, content, **extra):
    return {
        "filename": "a.py",
        "code": "F401",
        "message": "fix me",
        "location": {"row": row, "column": col},
        "fix": {
            "edits": [
                {
                    "content": content,
                    "location": {"row": row, "column": col},
                    "end_location": {"row": row, "column": end_col},
                }
            ]
        },
        **extra,
    }


def _tree(
    tmp_path,
    text: str = "one\ntwo\nthree\nfour\nfive\nsix\nseven\neight\nnine\nten\neleven\nprint( x )\ny = 2\nz = 3\n",
):
    (tmp_path / "a.py").write_text(text)
    return str(tmp_path)


def _fail(findings):
    return [GateResult("ruff", GateOutcome.FAIL, 0.3, "ruff", findings)]


def test_comment_carries_the_tools_own_fix(tmp_path) -> None:
    root = _tree(tmp_path)
    results = _fail([_fixable(12, 7, 8, "")])  # drop the space in `print( x )`
    (comment,) = pr_comments.build(results, ["a.py"], _DIFF, workdir=root)[0]
    assert comment["body"].endswith("```suggestion\nprint(x )\n```")
    assert "start_line" not in comment  # single line: no range needed


def test_multi_line_fix_makes_the_comment_span_the_range(tmp_path) -> None:
    root = _tree(tmp_path)
    joined = {
        "filename": "a.py",
        "message": "join these",
        "location": {"row": 12, "column": 1},
        "fix": {
            "edits": [
                {
                    "content": "joined",
                    "location": {"row": 12, "column": 1},
                    "end_location": {"row": 13, "column": 6},
                }
            ]
        },
    }
    (comment,) = pr_comments.build(_fail([joined]), ["a.py"], _DIFF, workdir=root)[0]
    # lines 12-13 are both added by _DIFF, so GitHub will take the range
    assert (comment["start_line"], comment["line"]) == (12, 13)
    assert comment["start_side"] == comment["side"] == "RIGHT"
    assert comment["body"].endswith("```suggestion\njoined\n```")


def test_a_fix_reaching_outside_the_diff_is_left_as_prose(tmp_path) -> None:
    """GitHub rejects a comment whose range leaves the diff, and a rejected
    comment is a lost finding — so the prose stands on its own instead."""
    root = _tree(tmp_path)
    spill = {
        "filename": "a.py",
        "message": "reaches line 14",
        "location": {"row": 13, "column": 1},
        "fix": {
            "edits": [
                {
                    "content": "x",
                    "location": {"row": 13, "column": 1},
                    "end_location": {"row": 14, "column": 1},
                }
            ]
        },
    }
    (comment,) = pr_comments.build(_fail([spill]), ["a.py"], _DIFF, workdir=root)[0]
    assert comment["line"] == 13
    assert "start_line" not in comment
    assert "```suggestion" not in comment["body"]  # 14 is not in the diff


def test_findings_without_a_fix_are_unchanged(tmp_path) -> None:
    root = _tree(tmp_path)
    comments, _ = pr_comments.build(_RESULTS, ["a.py", "b.py"], _DIFF, workdir=root)
    assert all("```suggestion" not in c["body"] for c in comments)


def test_summary_counts_the_applicable_fixes(tmp_path) -> None:
    root = _tree(tmp_path)
    results = _fail([_fixable(12, 7, 8, "")])
    v = report.aggregate(results)
    body = pr_comments.review_payload(results, v, ["a.py"], diff=_DIFF, workdir=root)["body"]
    assert "1 carries a suggested fix" in body
