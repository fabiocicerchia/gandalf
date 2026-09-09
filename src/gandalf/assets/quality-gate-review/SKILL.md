---
name: quality-gate-review
description: Review a code change, PR, diff, or code-challenge submission against fixed quality gates and produce a scored go/no-go decision. Runs six gates (correctness & algorithm, tests & CI, security & robustness, clean code & design, readability & documentation, project & delivery hygiene) built from an 82-item review checklist, scores each 0-5, computes a weighted overall score out of 100, gives a GO / REVIEW / NO-GO verdict, and lists the specific blockers to fix. Use whenever the user wants to judge whether work is ready to move forward — phrases like "review my work", "score this PR", "review this code challenge", "is this ready to ship/merge", "run the quality gates", "should I move forward", "rate the quality", "grade this submission". This is a scored decision aid, not a line-by-line bug hunt; for pure bug-finding use a code-review tool instead, and lean on this when the user wants a quality level and a ship-or-not call.
---

# Quality Gate Review

Judge whether a code change or code-challenge submission is ready to move forward. Score it
against six quality gates, roll the scores into one number, and return a clear GO / REVIEW /
NO-GO verdict with the exact blockers standing in the way. The point is a defensible decision
the user can act on, not a generic critique.

The gates condense an 82-item review checklist (see `references/checklist.md`); every item maps
to exactly one gate, with no duplication.

## When to use this

Use when the user wants a quality *level* and a ship-or-not call on a code change, PR, diff, or
code-challenge submission: "review my work", "score this", "review this challenge", "is this
ready to merge", "run the gates", "should I move forward".

Do NOT use this for:
- A pure line-by-line bug hunt with no decision attached → use a code-review tool.
- Reviewing non-code deliverables (docs, decisions, plans) → this gate set is tuned for code.
- Trivial one-line changes where a verdict adds no value → just answer directly.

## Procedure

1. **Identify what's under review and its breadth.** A *bare diff / PR* (changed lines only) and
   a *full repo / code-challenge submission* (whole project) are scored against different subsets
   of the checklist — repo-level items (README, Docker, git history, folder structure) don't apply
   to a bare diff. Determine which you have; if ambiguous, ask. Note what you could NOT see (no CI
   access, can't run tests) — unknowns lower confidence, not the score.

2. **Detect the language/ecosystem** from file extensions and config files, and map the generic
   checks to that ecosystem's tools (linter, formatter, doc-comments, package manager). The
   mapping table is in `references/checklist.md` — e.g. PHP → phpcbf / php-cs-fixer / DocBlocks /
   Composer; TS → eslint / prettier / TSDoc / npm. If the language is unclear, ask.

3. **Establish intent.** Restate in one line what the change/submission is *supposed* to do. Every
   gate is judged against that intent — "correct" and "complete" are meaningless without it.

4. **Score each of the six gates 0-5** using `references/rubric.md` (read it — it pins the score
   anchors and the per-gate checklist items to look for). Mark any item that cannot apply to this
   artifact as **N/A** rather than failing it (e.g. README on a bare diff). Be specific and
   evidence-based: cite the file/line or the missing thing, never "feels off". The gates:

   | # | Gate | Weight | Absorbs (checklist categories) |
   |---|------|--------|--------------------------------|
   | 1 | Correctness & algorithm | 25 | Algorithm, Performance |
   | 2 | Tests & CI | 18 | Tests |
   | 3 | Security & robustness | 18 | Security |
   | 4 | Clean code & design | 18 | Clean Code, Complexity, Paradigms, Coding Style |
   | 5 | Readability & documentation | 12 | Readability, Documentation |
   | 6 | Project & delivery hygiene | 9 | Environment, Versioning, Language, i18n, Presentation |

5. **Compute the overall score (0-100)** over the gates that apply, renormalising for N/A:
   `overall = round( Σ(gate_score / 5 × weight) / Σ(weight) × 100 )`, summing only gates that have
   at least one applicable item. A gate whose items are *all* N/A is dropped from both sums (so a
   bare diff isn't punished for having no README). A gate with *some* N/A items is scored 0-5 on
   its applicable items only. Always state which gates were dropped and why. If only one gate
   applies (`Σ(weight)` collapses to a single gate), skip the weighted roll-up entirely — report
   that gate's raw score and say so, rather than presenting a 0/100 that really means "almost
   nothing was applicable".

6. **Decide the verdict (balanced bar)** in this order — first match wins:
   - **NO-GO** if any *critical* gate (1 Correctness & algorithm or 3 Security & robustness) scores
     ≤ 2, **or** overall < 60.
   - **REVIEW** if overall is 60–79, **or** any gate scores ≤ 2, **or** any gate scores 3 on a
     dimension that clearly matters for this artifact.
   - **GO** if overall ≥ 80 **and** every applicable gate ≥ 3 **and** no critical gate below 4.

   Critical gates can veto a high average — a security hole is a NO-GO even if everything else is
   excellent. State explicitly when a veto drove the verdict.

   If the user asks for "strict" (every gate must clear a minimum) or "lenient" (block only on
   genuinely broken work), adjust thresholds and note which mode you used.

7. **List blockers and fixes.** For every gate scoring ≤ 3, give a concrete, actionable blocker
   tagged with its gate, ordered by severity. A blocker names what's wrong and what to do —
   "add a test for the empty-list path in foo.py:42", not "improve tests".

8. **Consistency check, then emit the scorecard** (format below). Before emitting, confirm the
   verdict is consistent with the scores and the veto rules — a GO printed above a gate scoring ≤ 2,
   or a NO-GO with every gate ≥ 4 and no veto named, is a contradiction to fix, not to ship. Produce the full 82-item ✓/✗/N-A checklist ONLY if the
   user asks for it ("show the full checklist", "tick the boxes", "item by item") — render it from
   `references/checklist.md`, grouped by gate, marking each item ✓ / ✗ / N-A with a one-line note
   on every ✗.

## Output format

```
QUALITY GATE REVIEW — <one-line intent>
Reviewed: <bare diff | full repo/submission> · <language/ecosystem> · <scope: files / commit range / PR>

OVERALL: <NN>/100  →  <GO | REVIEW | NO-GO>
<one-line reason for the verdict; name any critical-gate veto or dropped gates>

GATE SCORES
  1. Correctness & algorithm        <n>/5  <⚠ if ≤3>
  2. Tests & CI                     <n>/5  <⚠ if ≤3>
  3. Security & robustness          <n>/5  <⚠ if ≤3>
  4. Clean code & design            <n>/5  <⚠ if ≤3>
  5. Readability & documentation    <n>/5  <⚠ if ≤3>
  6. Project & delivery hygiene     <n>/5  <⚠ if ≤3, or N/A>

BLOCKERS (fix before GO)
  - [<gate>] <what's wrong> → <what to do>  (file:line)
  - ...

NOTES
  - <strengths worth keeping; gates dropped as N/A and why; anything you couldn't verify>
```

If the verdict is GO with no gate ≤ 3, replace BLOCKERS with `BLOCKERS: none` and list any
optional nice-to-haves under NOTES.

## Example (abbreviated)

```
QUALITY GATE REVIEW — add retry with backoff to the payments webhook client
Reviewed: bare diff · PHP · 3 files (Client.php, Config.php, ClientTest.php)

OVERALL: 73/100  →  REVIEW
Solid implementation, but the retry path has no test and unbounded retries risk a thundering herd.
Gate 6 (hygiene) dropped — N/A for a bare diff.

GATE SCORES
  1. Correctness & algorithm        4/5
  2. Tests & CI                     2/5  ⚠
  3. Security & robustness          5/5
  4. Clean code & design            4/5
  5. Readability & documentation    4/5
  6. Project & delivery hygiene     N/A

BLOCKERS (fix before GO)
  - [Tests] Retry/backoff path is untested → add a test asserting it retries N times then throws (ClientTest.php)
  - [Risk] No max-retry ceiling or jitter → cap attempts and add jitter to avoid synchronized retries (Client.php:58)

NOTES
  - Clean separation of config from client; good naming and DocBlocks.
  - Could not run phpunit — test gate scored on inspection only.
```

DON'T: hand back "looks good, ship it" or a wall of nitpicks with no score or verdict — the
deliverable is the scorecard and the decision.
DO:    always end on a verdict the user can act on, with blockers concrete enough to fix without
       asking you what you meant.

## Notes

- Score what you can see. If tests can't be run or CI isn't visible, score on inspection and say
  so in NOTES — don't silently assume pass or fail.
- The checklist is the source of evidence; the gates are the scoring engine. Detailed per-gate
  anchors live in `references/rubric.md`; the full 82-item checklist and the language-tool mapping
  live in `references/checklist.md`.
