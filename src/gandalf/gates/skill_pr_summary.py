"""Gate: the `pr-code-summarizer` skill as a risk-flagging summary.

Produces the technical-lead's 60-second read of the change (what changed, why
it matters, complexity, risks, questions) and surfaces it as gate findings.
Informational and non-blocking: it passes on a clean, low-risk change and warns
when the summary itself flags high complexity or real risks worth a human look.
"""

from __future__ import annotations

from gandalf import skills
from gandalf.base import GateContext, GateResult

_TASK = (
    "Summarise the change as the skill directs. Set 'score' 0-100 as an overall "
    "confidence (high when the change is low-complexity and low-risk). Outcome: "
    "warn if complexity is high OR there are real risks/concerns a reviewer must "
    "check; otherwise pass. 'summary' is the one-line 'what changed / why it "
    "matters'. 'findings' holds the complexity call, each risk/concern, and the "
    "2-3 questions to raise with the author — one per entry. If there is no diff "
    "in scope, summarise the codebase's current state instead and pass."
)


class PrCodeSummaryGate:
    name = "pr_code_summary"
    blocking = False
    category = "Best practices"

    async def run(self, ctx: GateContext) -> GateResult:
        return await skills.judge(
            ctx, skill="pr-code-summarizer", gate_name=self.name, task=_TASK
        )
