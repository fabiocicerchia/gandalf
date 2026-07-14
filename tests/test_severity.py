"""Tests for severity-weighted scoring. Run: pytest gandalf/test_severity.py"""

from __future__ import annotations

from gandalf import severity as sv
from gandalf.base import GateOutcome, GateResult


def test_of_across_tool_shapes():
    assert sv.of({"issue_severity": "HIGH"}) == "high"  # bandit
    assert sv.of({"Severity": "CRITICAL"}) == "critical"  # trivy
    assert sv.of({"extra": {"severity": "WARNING"}}) == "medium"  # semgrep (nested)
    assert sv.of({"code": "E501"}) == ""  # ruff — no severity


def test_score_orders_by_severity():
    one_crit = sv.score([{"Severity": "CRITICAL"}])
    five_low = sv.score([{"severity": "LOW"}] * 5)
    assert one_crit < five_low  # a single critical hurts more than five lows
    assert sv.score([{"Severity": "CRITICAL"}] * 3) == 0.0  # floors
    assert sv.score([{"code": "E501"}]) is None  # no severities → caller keeps base


def test_reweight_preserves_outcome_and_untouched_gates():
    r = GateResult(
        "trivy",
        GateOutcome.WARN,
        0.9,
        "x",
        [{"Severity": "CRITICAL"}, {"Severity": "LOW"}],
    )
    r._blocking = True
    out = sv.reweight(r)
    assert out.outcome is GateOutcome.WARN  # RAG unchanged
    assert out.score < 0.9 and out._blocking is True  # score weighted, flags kept
    # a gate with no severities is returned unchanged
    r2 = GateResult("ruff", GateOutcome.FAIL, 0.3, "x", [{"code": "E501"}])
    assert sv.reweight(r2) is r2


if __name__ == "__main__":
    test_of_across_tool_shapes()
    test_score_orders_by_severity()
    test_reweight_preserves_outcome_and_untouched_gates()
    print("ok")
