"""Gate: the `quality-gate-review` skill as a blocking go/no-go judge.

The skill scores a change against six quality gates and returns GO / REVIEW /
NO-GO. Here that verdict IS the gate outcome: GO→pass, REVIEW→warn, NO-GO→fail.
Blocking, because a NO-GO ("critical gate broken, or overall < 60") is exactly
the kind of thing that should redden the whole run.
"""

from __future__ import annotations

from gandalf import skills
from gandalf.base import GateContext, GateResult

_TASK = (
    "Score the six gates 0-5, compute the overall 0-100, and decide the verdict. "
    "Set 'score' to the overall (0-100). Set 'outcome' to pass for GO, warn for "
    "REVIEW, fail for NO-GO. Put each BLOCKER (its gate tag, what's wrong, and the "
    "fix) as one entry in 'findings'."
)


class QualityGateReviewGate:
    name = "quality_gate_review"
    blocking = True
    category = "Best practices"

    async def run(self, ctx: GateContext) -> GateResult:
        return await skills.judge(
            ctx, skill="quality-gate-review", gate_name=self.name, task=_TASK
        )
