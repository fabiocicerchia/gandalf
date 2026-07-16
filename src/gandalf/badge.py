"""Render a verdict as a shields.io endpoint badge — the JSON schema
https://shields.io/badges/endpoint-badge consumes to draw an SVG, so gandalf
never has to render pixels itself. Point a README at:
  https://img.shields.io/endpoint?url=<raw-URL-to-the-written-JSON>
"""

from __future__ import annotations

from .base import GateOutcome
from .report import Verdict

# shields.io named colors, keyed by RAG outcome
_COLOR = {
    GateOutcome.PASS: "brightgreen",
    GateOutcome.WARN: "yellow",
    GateOutcome.FAIL: "red",
}


def to_badge(verdict: Verdict, label: str = "gandalf") -> dict:
    return {
        "schemaVersion": 1,
        "label": label,
        "message": f"{verdict.score}/100",
        "color": _COLOR[verdict.outcome],
    }
