"""Design-readiness gate — the `grill-me` skill (github.com/mattpocock/skills)
run as an automated gate.

The skill is a relentless interview that walks every branch of a design's
decision tree until nothing load-bearing is left unresolved. A CI gate can't
interview a human, so it flips the skill inward: the model plays the interviewer
against the change itself and reports the load-bearing decisions the change
leaves unanswered or ambiguous. Few open questions → high readiness (PASS);
many → WARN. Advisory only (PASS/WARN).
"""

from __future__ import annotations

from gandalf.skillgate import SkillGate


class GrillMeGate(SkillGate):
    name = "grill_me"
    category = "Design readiness"
    # grill-me delegates to /grilling; embed both so the gate carries the real
    # interview rubric, not just the one-line entrypoint.
    skills = ("grill-me", "grilling")
    pass_threshold = 0.8
    unit = "open question"
    task = (
        "Play the relentless interviewer from the grilling skill, but turn it on the "
        "CHANGE below instead of a live user. Walk the decision tree the change "
        "implies and surface every LOAD-BEARING decision it leaves unresolved, "
        "ambiguous, or silently assumed — the questions a careful reviewer would "
        "refuse to merge without answers to. For each, phrase the open question and, "
        "per the skill, give your own recommended answer in the detail. Ignore "
        "trivia and style; only decisions that change correctness, behaviour, "
        "scope, or safety count.\n"
        "Score DESIGN READINESS 0-100: 100 = every load-bearing decision is resolved "
        "or unambiguously evident in the change; lower as more critical branches are "
        "left open. Put each unresolved decision in findings (severity by how load-"
        "bearing it is). An empty list means the design is fully pinned down."
    )
