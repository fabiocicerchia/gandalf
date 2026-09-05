"""Gate: the `ruthless-refactor` skill as a simplification judge.

Treats every line as a liability and looks for duplication, dead code,
needless indirection, and custom code that a library already provides.
Advisory (non-blocking): bloat is a maintainability smell, not a release
blocker — it warns loudly rather than reddening the run.
"""

from __future__ import annotations

from gandalf import skills
from gandalf.base import GateContext, GateResult

_TASK = (
    "Judge how lean the code is. Set 'score' 0-100 where 100 is the smallest, "
    "clearest code that fully solves the problem and 0 is heavily bloated. "
    "Outcome: pass if there is little to cut (score >= 80), warn if there are "
    "clear simplification wins (60-79), fail if the code is seriously inflated "
    "(< 60). Each finding names one concrete cut: the duplicated logic, dead "
    "code, redundant layer, or custom code replaceable by a stdlib/library "
    "feature, with the file/symbol."
)


class RuthlessRefactorGate:
    name = "ruthless_refactor"
    blocking = False
    category = "Complexity"

    async def run(self, ctx: GateContext) -> GateResult:
        return await skills.judge(ctx, skill="ruthless-refactor", gate_name=self.name, task=_TASK)
