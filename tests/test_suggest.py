"""Tests for machine-applicable fixes → GitHub suggestion blocks.
Run: pytest tests/test_suggest.py"""

from __future__ import annotations

from gandalf import suggest

_SRC = "import os\nimport sys\n\nx = 1  # colr me\nprint( x )\n"


def _repo(tmp_path, text=_SRC, name="a.py"):
    (tmp_path / name).write_text(text)
    return str(tmp_path)


def test_ruff_edits_become_the_new_line(tmp_path):
    root = _repo(tmp_path)
    # ruff's F401 fix deletes line 1 by replacing (1,1)..(2,1) with nothing.
    f = {
        "filename": "a.py",
        "code": "F401",
        "location": {"row": 1, "column": 1},
        "fix": {
            "edits": [
                {
                    "content": "",
                    "location": {"row": 1, "column": 1},
                    "end_location": {"row": 2, "column": 1},
                }
            ]
        },
    }
    assert suggest.for_anchor(root, "a.py", 1, [f]) == (2, "import sys")


def test_two_findings_on_one_line_make_one_suggestion(tmp_path):
    root = _repo(tmp_path)

    def drop(col):
        return {
            "filename": "a.py",
            "fix": {
                "edits": [
                    {
                        "location": {"row": 5, "column": col},
                        "end_location": {"row": 5, "column": col + 1},
                        "content": "",
                    }
                ]
            },
        }

    left, right = drop(7), drop(9)
    # Both hits applied together — one suggestion, not two that go stale.
    assert suggest.for_anchor(root, "a.py", 5, [left, right]) == (5, "print(x)")


def test_conflicting_edits_are_refused(tmp_path):
    root = _repo(tmp_path)
    over = {
        "fix": {
            "edits": [
                {
                    "location": {"row": 5, "column": 1},
                    "end_location": {"row": 5, "column": 8},
                    "content": "print(",
                }
            ]
        }
    }
    assert suggest.for_anchor(root, "a.py", 5, [over, dict(over)]) is None


def test_shellcheck_replacement(tmp_path):
    root = _repo(tmp_path, "echo $foo\n", "s.sh")
    f = {
        "file": "s.sh",
        "line": 1,
        "fix": {
            "replacements": [
                {
                    "line": 1,
                    "endLine": 1,
                    "column": 6,
                    "endColumn": 10,
                    "replacement": '"$foo"',
                }
            ]
        },
    }
    assert suggest.for_anchor(root, "s.sh", 1, [f]) == (1, 'echo "$foo"')


def test_shellcheck_zero_width_insertions(tmp_path):
    """The shape shellcheck actually emits for SC2086: two zero-width inserts,
    one either side of the word, rather than one replacement."""
    root = _repo(tmp_path, "ls $foo\n", "s.sh")
    f = {
        "file": "s.sh",
        "line": 1,
        "code": 2086,
        "fix": {
            "replacements": [
                {
                    "line": 1,
                    "endLine": 1,
                    "column": 4,
                    "endColumn": 4,
                    "insertionPoint": "afterEnd",
                    "replacement": '"',
                },
                {
                    "line": 1,
                    "endLine": 1,
                    "column": 8,
                    "endColumn": 8,
                    "insertionPoint": "beforeStart",
                    "replacement": '"',
                },
            ]
        },
    }
    assert suggest.for_anchor(root, "s.sh", 1, [f]) == (1, 'ls "$foo"')


def test_semgrep_autofix(tmp_path):
    root = _repo(tmp_path)
    f = {
        "path": "a.py",
        "line": 4,
        "start": {"line": 4, "col": 5},
        "end": {"line": 4, "col": 6},
        "extra": {"fix": "2"},
    }
    assert suggest.for_anchor(root, "a.py", 4, [f]) == (4, "x = 2  # colr me")


def test_codespell_correction_is_rebuilt_from_the_line(tmp_path):
    root = _repo(tmp_path)
    f = {"typo": "a.py:4: colr ==> color"}
    assert suggest.for_anchor(root, "a.py", 4, [f]) == (4, "x = 1  # color me")


def test_codespell_ambiguous_correction_is_not_suggested(tmp_path):
    root = _repo(tmp_path)
    assert (
        suggest.for_anchor(
            root, "a.py", 4, [{"typo": "a.py:4: colr ==> color, collar"}]
        )
        is None
    )


def test_normalised_fix_block(tmp_path):
    """The shape a gate writes when only it can read its tool's fix format."""
    root = _repo(tmp_path, "const a = 1\n", "a.js")
    f = {
        "path": "a.js",
        "line": 1,
        "_fix": {
            "edits": [
                {
                    "start_line": 1,
                    "start_column": 12,
                    "end_line": 1,
                    "end_column": 12,
                    "text": ";",
                }
            ]
        },
    }
    assert suggest.for_anchor(root, "a.js", 1, [f]) == (1, "const a = 1;")


def test_a_finding_with_no_fix_suggests_nothing(tmp_path):
    root = _repo(tmp_path)
    assert suggest.for_anchor(root, "a.py", 4, [{"message": "looks wrong"}]) is None
    assert suggest.for_anchor(root, "nope.py", 1, [{"message": "x"}]) is None


def test_a_fix_below_the_comment_is_refused(tmp_path):
    """GitHub applies the block to the line the comment sits on, so a
    replacement computed for another line would overwrite the wrong code."""
    root = _repo(tmp_path)
    f = {
        "fix": {
            "edits": [
                {
                    "location": {"row": 4, "column": 5},
                    "end_location": {"row": 4, "column": 6},
                    "content": "2",
                }
            ]
        }
    }
    assert suggest.for_anchor(root, "a.py", 4, [f]) is not None
    assert suggest.for_anchor(root, "a.py", 3, [f]) is None


def test_multi_line_suggestion_must_stay_inside_the_diff(tmp_path):
    root = _repo(tmp_path)
    f = {
        "fix": {
            "edits": [
                {
                    "location": {"row": 1, "column": 1},
                    "end_location": {"row": 2, "column": 1},
                    "content": "",
                }
            ]
        }
    }
    assert suggest.for_anchor(root, "a.py", 1, [f], anchorable={1, 2}) == (
        2,
        "import sys",
    )
    assert suggest.for_anchor(root, "a.py", 1, [f], anchorable={1}) is None


def test_a_fix_that_changes_nothing_is_not_a_suggestion(tmp_path):
    root = _repo(tmp_path)
    f = {
        "fix": {
            "edits": [
                {
                    "location": {"row": 1, "column": 1},
                    "end_location": {"row": 1, "column": 7},
                    "content": "import",
                }
            ]
        }
    }
    assert suggest.for_anchor(root, "a.py", 1, [f]) is None


def test_edits_off_the_end_of_the_file_are_refused(tmp_path):
    root = _repo(tmp_path)
    f = {
        "fix": {
            "edits": [
                {
                    "location": {"row": 99, "column": 1},
                    "end_location": {"row": 99, "column": 2},
                    "content": "x",
                }
            ]
        }
    }
    assert suggest.for_anchor(root, "a.py", 99, [f]) is None


def test_a_deletion_running_past_the_last_line_is_pulled_back(tmp_path):
    root = _repo(tmp_path, "keep = 1\ndrop = 2\n")
    f = {
        "fix": {
            "edits": [
                {
                    "location": {"row": 2, "column": 1},
                    "end_location": {"row": 3, "column": 1},
                    "content": "",
                }
            ]
        }
    }
    assert suggest.for_anchor(root, "a.py", 2, [f]) == (2, "")


def test_oversized_suggestion_is_dropped(tmp_path):
    root = _repo(tmp_path, "".join(f"line{i}\n" for i in range(200)))
    f = {
        "fix": {
            "edits": [
                {
                    "location": {"row": 1, "column": 1},
                    "end_location": {"row": 100, "column": 1},
                    "content": "one line\n",
                }
            ]
        }
    }
    assert suggest.for_anchor(root, "a.py", 1, [f]) is None


def test_a_fence_in_the_replacement_is_dropped(tmp_path):
    """The block is fenced markdown; a fence inside it would break out of it."""
    root = _repo(tmp_path, "x = 1\n")
    f = {
        "fix": {
            "edits": [
                {
                    "location": {"row": 1, "column": 1},
                    "end_location": {"row": 1, "column": 6},
                    "content": "x = '```'",
                }
            ]
        }
    }
    assert suggest.for_anchor(root, "a.py", 1, [f]) is None


def test_utf16_offsets_survive_an_astral_character():
    source = "// 😀\nconst a = 1\n"
    # JS counts the emoji as two units, so the end of line 2 is offset 17.
    edit = suggest.utf16_edit(source, 17, 17, ";")
    assert edit == {
        "start_line": 2,
        "start_column": 12,
        "end_line": 2,
        "end_column": 12,
        "text": ";",
    }
    assert suggest.utf16_edit(source, 5, 2, "x") is None  # end before start
    assert suggest.utf16_edit(source, 0, 999, "x") is None  # past the end


def test_block_is_a_github_suggestion_fence():
    assert suggest.block("x = 1") == "```suggestion\nx = 1\n```"
