"""Tests for the result cache. Run: pytest tests/test_cache.py"""

from __future__ import annotations

from gandalf import cache
from gandalf.base import GateOutcome, GateResult


def test_content_hash_changes_with_file_content(tmp_path):
    (tmp_path / "a.py").write_text("x = 1\n")
    files = cache.target_files(str(tmp_path), ["a.py"])
    h1 = cache.content_hash(str(tmp_path), files)
    (tmp_path / "a.py").write_text("x = 2\n")
    h2 = cache.content_hash(str(tmp_path), files)
    assert h1 != h2


def test_get_put_roundtrip():
    data: dict = {}
    r = GateResult("ruff", GateOutcome.WARN, 0.8, "ruff: 1 issue", [{"path": "a.py"}])
    cache.put(data, "ruff", "abc123", r)
    got = cache.get(data, "ruff", "abc123")
    assert got == r
    # a different hash (file set changed) is a miss
    assert cache.get(data, "ruff", "different") is None
    # a different gate name is a miss
    assert cache.get(data, "eslint", "abc123") is None


def test_load_save_roundtrip(tmp_path):
    path = str(tmp_path / ".gandalf-cache.json")
    data: dict = {}
    cache.put(
        data, "bandit", "h1", GateResult("bandit", GateOutcome.PASS, 1.0, "clean")
    )
    cache.save(path, data)
    loaded = cache.load(path)
    assert cache.get(loaded, "bandit", "h1").outcome is GateOutcome.PASS


def test_load_missing_file_is_empty(tmp_path):
    assert cache.load(str(tmp_path / "nope.json")) == {}
