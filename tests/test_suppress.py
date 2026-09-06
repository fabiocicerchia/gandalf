"""Tests for finding suppression + baseline. Run: pytest gandalf/test_suppress.py"""

from __future__ import annotations

from gandalf import suppress
from gandalf.base import GateOutcome, GateResult

_F = [
    {"path": "a.py", "code": "E501", "message": "line too long"},
    {"path": "b.py", "code": "F401", "message": "unused import os"},
    {"path": "tests/t.py", "code": "E501", "message": "line too long"},
]


def _res(findings=None):
    return GateResult("ruff", GateOutcome.FAIL, 0.4, "ruff: 3", findings or list(_F))


def test_fingerprint_line_insensitive() -> None:
    a = suppress.fingerprint("ruff", {"path": "a.py", "code": "E501", "message": "x", "line": 1})
    b = suppress.fingerprint("ruff", {"path": "a.py", "code": "E501", "message": "x", "line": 99})
    assert a == b  # line excluded from the fingerprint
    c = suppress.fingerprint("ruff", {"path": "a.py", "code": "E501", "message": "y"})
    assert a != c


def test_rule_matching_and_wildcards() -> None:
    assert suppress.Suppressor(rules=["ruff:E501"]).apply(_res()).findings == [_F[1]]
    # gate-only rule mutes everything
    out = suppress.Suppressor(rules=["ruff"]).apply(_res())
    assert out.outcome is GateOutcome.PASS
    assert out.findings == []
    # path glob
    out = suppress.Suppressor(rules=["ruff::tests/*"]).apply(_res())
    assert [f["path"] for f in out.findings] == ["a.py", "b.py"]
    # non-matching gate leaves it alone
    assert suppress.Suppressor(rules=["bandit:E501"]).apply(_res()).findings == _F


def test_partial_is_never_worse() -> None:
    out = suppress.Suppressor(rules=["ruff:E501"]).apply(_res())
    assert out.outcome is GateOutcome.FAIL  # outcome unchanged
    assert out.score >= 0.4  # score only rises
    assert "suppressed" in out.summary


def test_baseline_roundtrip(tmp_path) -> None:
    path = str(tmp_path / "bl.json")
    n = suppress.write_baseline(path, [_res()], "now")
    assert n == 3
    loaded = suppress.load_baseline(path)
    assert len(loaded) == 3
    out = suppress.Suppressor(baseline=loaded).apply(_res())
    assert out.outcome is GateOutcome.PASS
    assert out.findings == []


def test_inactive_suppressor_is_identity() -> None:
    r = _res()
    assert suppress.Suppressor().apply(r) is r


if __name__ == "__main__":
    import tempfile
    from pathlib import Path

    test_fingerprint_line_insensitive()
    test_rule_matching_and_wildcards()
    test_partial_is_never_worse()
    test_inactive_suppressor_is_identity()
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "bl.json"
        suppress.write_baseline(str(p), [_res()], "now")
        assert len(suppress.load_baseline(str(p))) == 3
