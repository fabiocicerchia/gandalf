"""Gate contract — kept byte-compatible with ai-harness/app/gates/base.py so
gate files written for either project drop straight into the other. The only
change here: GateOutcome is inlined (3 lines) instead of imported from an
app package, so gandalf has zero cross-project dependency.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol, runtime_checkable


class GateOutcome(str, Enum):
    PASS = "pass"  # nosec B105 — enum value, not a password
    WARN = "warn"
    FAIL = "fail"


@dataclass
class GateResult:
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
    name: str
    blocking: bool  # if True, a FAIL makes the overall verdict red

    async def run(self, ctx: GateContext) -> GateResult: ...
