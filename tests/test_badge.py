"""Tests for the shields.io endpoint badge. Run: pytest gandalf/test_badge.py"""

from __future__ import annotations

import json

from gandalf import badge, report
from gandalf.base import GateOutcome


def test_badge_shape_and_serializable() -> None:
    b = badge.to_badge(report.Verdict(GateOutcome.PASS, 92))
    assert b == {
        "schemaVersion": 1,
        "label": "gandalf",
        "message": "92/100",
        "color": "brightgreen",
    }
    json.dumps(b)  # must be JSON-serializable


def test_badge_color_follows_rag() -> None:
    assert badge.to_badge(report.Verdict(GateOutcome.PASS, 100))["color"] == "brightgreen"
    assert badge.to_badge(report.Verdict(GateOutcome.WARN, 70))["color"] == "yellow"
    assert badge.to_badge(report.Verdict(GateOutcome.FAIL, 20))["color"] == "red"


def test_badge_label_is_overridable() -> None:
    b = badge.to_badge(report.Verdict(GateOutcome.PASS, 80), label="my-repo")
    assert b["label"] == "my-repo"


if __name__ == "__main__":
    test_badge_shape_and_serializable()
    test_badge_color_follows_rag()
    test_badge_label_is_overridable()
