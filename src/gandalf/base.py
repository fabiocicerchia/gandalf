"""Gate contract — kept byte-compatible with ai-harness/app/gates/base.py so
gate files written for either project drop straight into the other. The only
change here: GateOutcome is inlined (3 lines) instead of imported from an
app package, so gandalf has zero cross-project dependency.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable


class GateOutcome(StrEnum):
    """The traffic light. A str enum so it serialises straight into the JSON
    report and the cache without a converter on either side."""

    PASS = "pass"  # noqa: S105 — an enum value, not a password
    WARN = "warn"
    FAIL = "fail"


@dataclass
class GateResult:
    """What one gate reports back.

    `score` is 0.0..1.0 and the outcome is separate on purpose: a gate can score
    poorly without being red, and the policy that turns scores into a verdict
    lives in report.py, not in the gate.
    """

    name: str
    outcome: GateOutcome
    score: float  # 0.0 (fail) .. 1.0 (clean)
    summary: str = ""
    findings: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class GateContext:
    """Everything a gate needs to run against a working tree."""

    repo: str
    workdir: str  # path to the checked-out worktree
    changed_files: list[str] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class Gate(Protocol):
    """The whole contract a gate file has to satisfy.

    A Protocol rather than a base class, so a gate written for the sibling
    project drops in here without changing what it inherits from. `blocking`
    is what separates a gate that can fail the run from one that only informs.
    """

    name: str
    blocking: bool  # if True, a FAIL makes the overall verdict red

    async def run(self, ctx: GateContext) -> GateResult: ...
