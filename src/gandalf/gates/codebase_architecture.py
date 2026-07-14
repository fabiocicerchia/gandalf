"""Deep-module gate — the `improve-codebase-architecture` skill
(github.com/mattpocock/skills) run as an automated gate.

The skill surfaces deepening opportunities: shallow modules, poor locality,
leaky seams, interfaces that are hard to test. Interactively it explores the
tree and writes an HTML report; as a gate it applies the same judgement (and the
`codebase-design` vocabulary — module / interface / depth / seam / adapter /
leverage / locality, the deletion test) to the change and scores its
architectural health. Advisory only (PASS/WARN).
"""

from __future__ import annotations

from gandalf.skillgate import SkillGate


class CodebaseArchitectureGate(SkillGate):
    name = "codebase_architecture"
    category = "Architecture"
    # improve-codebase-architecture is built on the codebase-design vocabulary;
    # embed both so the gate speaks the exact terms the skill mandates.
    skills = ("improve-codebase-architecture", "codebase-design")
    pass_threshold = 0.75
    unit = "deepening opportunity"
    task = (
        "Apply the improve-codebase-architecture skill to the CHANGE below, using the "
        "codebase-design vocabulary EXACTLY (module, interface, depth, seam, adapter, "
        "leverage, locality) — never 'component', 'service', 'API', or 'boundary'. Do "
        "NOT write an HTML report or propose full interfaces; instead judge the "
        "architecture the change introduces or touches and list deepening "
        "opportunities:\n"
        "- shallow modules whose interface is nearly as complex as their implementation;\n"
        "- pure helpers extracted only for testability while the real bugs hide in how "
        "they're called (no locality);\n"
        "- tightly-coupled modules leaking across their seams;\n"
        "- code that is untested or hard to test through its current interface.\n"
        "Apply the deletion test to anything you suspect is shallow: would deleting it "
        "concentrate complexity (deep, keep) or just move it (shallow, deepen)?\n"
        "Score ARCHITECTURAL HEALTH of the change 0-100: 100 = deep modules, clean "
        "seams, good locality, testable through their interfaces; lower as shallowness "
        "and leakage accumulate. Each finding names the module/file and the deepening "
        "move. An empty list means the change is already well-shaped."
    )
