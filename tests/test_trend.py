"""Tests for the score trend log. Run: pytest tests/test_trend.py"""

from __future__ import annotations

from gandalf import trend


def test_previous_score_none_without_file(tmp_path):
    assert trend.previous_score(str(tmp_path / "nope.jsonl"), "abc") is None


def test_previous_score_skips_same_commit(tmp_path):
    path = str(tmp_path / "trend.jsonl")
    trend.record(path, "aaa111", 80, "t1")
    # re-running the same commit isn't "previous"
    assert trend.previous_score(path, "aaa111") is None
    trend.record(path, "bbb222", 90, "t2")
    assert trend.previous_score(path, "bbb222") == 80
    assert trend.previous_score(path, "ccc333") == 90


def test_record_appends_jsonl(tmp_path):
    path = str(tmp_path / "trend.jsonl")
    trend.record(path, "aaa111", 80, "t1")
    trend.record(path, "bbb222", 90, "t2")
    lines = (tmp_path / "trend.jsonl").read_text().splitlines()
    assert len(lines) == 2
