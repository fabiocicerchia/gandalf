"""Well-Architected gate — the `well-architected` skill (adapted from AWS
sample-well-architected-skills-and-steering) run as an automated gate.

Evaluates the change against all six Well-Architected pillars — Operational
Excellence, Security, Reliability, Performance Efficiency, Cost Optimization,
Sustainability — and reports severity-tagged findings (🔴 High / 🟡 Medium risk).
The pillars are general cloud-design guidance, so this gate is generic (no
`langs`) and runs on every change; pillars it can't assess are marked N/A rather
than invented. Advisory only (PASS/WARN).
"""

from __future__ import annotations

from gandalf.skillgate import SkillGate


class WellArchitectedGate(SkillGate):
    name = "well_architected"
    category = "Well-Architected"
    skills = ("well-architected",)
    pass_threshold = 0.75
    unit = "risk"
    task = (
        "Perform a Well-Architected review of the CHANGE below against ALL SIX pillars "
        "using the skill above: Operational Excellence, Security, Reliability, "
        "Performance Efficiency, Cost Optimization, Sustainability. Do NOT skip a "
        "pillar — if a pillar cannot be assessed from the evidence in scope, say so "
        "(a low-severity 'N/A — <reason>' finding) rather than inventing issues. For "
        "each real gap, tag severity high (🔴 High Risk / HRI) or medium (🟡 Medium "
        "Risk / MRI), name the pillar in the title, cite the file/line, and give a "
        "concrete next step (a specific pattern or service to adopt) plus why it "
        "matters. Do not raise deterministic issues the dedicated scanners already "
        "own (secrets, dependency CVEs, SAST) unless they reflect a genuine "
        "architectural pillar gap.\n"
        "Score WELL-ARCHITECTED COMPLIANCE of the change 0-100 across the applicable "
        "pillars: 100 = the change upholds the pillars' design principles; lower as "
        "high/medium-risk gaps accumulate. An empty findings list means the change "
        "introduces no pillar risk."
    )
