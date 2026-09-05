"""Gate: the `security-assessment` skill as a security-posture judge.

The skill drafts a CNCF TAG Security style self-assessment; as a gate it applies
that same lens to score the project's security posture and surface the "Known
Weakness" gaps (missing SBOM, no signing, no branch protection, absent security
policy/incident response, etc.). Advisory and non-blocking — a self-assessment
informs the roadmap, it doesn't veto a release.
"""

from __future__ import annotations

from gandalf import skills
from gandalf.base import GateContext, GateResult

_TASK = (
    "Assess the project's security posture across the assessment's areas: "
    "metadata/SBOM, secure development pipeline (branch protection, signing, "
    "SCA, required reviews, automated release), security functions, compliance, "
    "responsible disclosure, and incident response. Set 'score' 0-100 for the "
    "posture. Outcome: pass if the posture is solid, warn if there are notable "
    "gaps, fail if critical security practices are absent. Each finding is one "
    "'Known Weakness' with the recommended roadmap action."
)


class SecurityAssessmentGate:
    name = "security_assessment"
    blocking = False
    category = "Security"

    async def run(self, ctx: GateContext) -> GateResult:
        return await skills.judge(ctx, skill="security-assessment", gate_name=self.name, task=_TASK)
