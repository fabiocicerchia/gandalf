---
name: ruthless-refactor
description: Aggressively simplify and shrink an inflated codebase without changing behavior — find and delete dead code, collapse duplication, remove needless indirection and over-engineering, and replace custom code with language or library features. Use when the user says things like "simplify this module", "this codebase is bloated", "reduce the line count", "remove dead code", "there's too much abstraction here", or asks to make code smaller and leaner while keeping it fully working. Works in small test-verified passes and reports what was removed and why it was safe. Not for bug-hunting or scored review — use a code-review or quality-gate skill for that.
---

# Ruthless Refactor

Produce the **smallest, clearest codebase that fully solves the problem**. Every line of
code is a liability, not an asset. The deliverable is working code that is measurably
smaller and clearer, plus a short report of what was removed and why it was safe.

## Guardrails (non-negotiable)

Aggressive deletion is only safe inside these rails:

- **Behavior lock first.** Run the existing tests before touching anything. If risky
  logic has no coverage, write characterization tests to pin current behavior *before*
  refactoring it. If tests cannot run in this environment, say so and downgrade to
  *proposing* changes with rationale instead of editing blind.
- **Small verified passes.** Target roughly 10% reduction per pass, then re-run the
  tests. Never batch hours of deletions into one unverified mega-change — a broken
  pass must be cheap to bisect and revert.
- **No silent contract changes.** Public APIs, CLI flags, serialized formats, and any
  observable behavior stay intact. If a simplification requires breaking one, flag it
  and ask — don't just do it.
- **Don't golf.** Fewer lines is the metric, clarity is the goal; when they conflict,
  clarity wins. Never strip logging, error handling, or input validation to save lines,
  and never merge code that is only *coincidentally* similar — DRY is about shared
  meaning, not shared characters.

## Procedure

1. **Baseline.** Measure LOC of the target (`cloc` or `wc -l`), record the test command
   and its current pass/fail state, and restate in one line what the code must keep
   doing. Without a baseline there is no honest "after".
2. **Read before cutting.** Spend more time reading than editing. For each candidate,
   ask: Is it still used? Does something else already provide this? What breaks if it
   goes? Does the language, stdlib, or an existing dependency already do this?
3. **Lock behavior** (see guardrails) — tests green before the first deletion.
4. **Iterate.** Each pass: pick the highest-value targets from the hunt list below,
   apply the change, run the tests, verify behavior unchanged. Repeat.
5. **Stop deliberately.** When a pass yields little or the next cut would hurt clarity,
   declare done rather than forcing reduction. Diminishing returns are the exit signal.
6. **Report** using the output format below.

## What to hunt (highest value first)

1. **Dead code** — unused functions, classes, branches, config, dependencies.
2. **Duplication** — the same logic in several places; consolidate to one.
3. **Needless indirection** — layers, wrappers, and interfaces with a single
   implementation and no second consumer in sight.
4. **Reinvented wheels** — custom code the stdlib, framework, or an existing
   dependency already provides.
5. **Over-generic frameworks** — flexibility built for futures that never arrived;
   collapse to what is actually used.
6. **Poor domain modeling** — many classes for one business concept, parallel APIs
   doing the same operation, clusters of boolean flags that should be one state
   machine. A better model naturally produces less code.

Useful moves: Inline Method, Collapse Hierarchy, Consolidate Duplicate Code, Replace
Conditional with Polymorphism (or the reverse, when polymorphism is the bloat), Replace
Custom Code with Library Features.

## Output format

End with this report so the result is verifiable:

```
RUTHLESS REFACTOR — <target>
LOC: <before> → <after>  (<n>% reduction, <p> passes)
Tests: <command> — <green/red before> → <green after>

REMOVED / SIMPLIFIED
  - <what> — <why it was safe> (<evidence: no references / covered by test X / stdlib equivalent>)
  - ...

FLAGGED, NOT DONE (needs a decision)
  - <simplification that would change a public contract or lacks test cover> → <what it would break / what's needed>
```

## Examples

DON'T: compress five clear lines into one nested ternary — fewer lines, worse code.
DO:    delete an unused helper class and its tests after confirming nothing references it.

DON'T: remove a try/except that logs context and rethrows — that's error handling, not bloat.
DO:    replace a 60-line hand-rolled deep-merge with the library equivalent, keeping the tests.
