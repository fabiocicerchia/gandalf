# Gate Scoring Rubric

Per-gate score anchors and the checklist items each gate judges. Score each gate 0–5 against the
stated **intent** of the change. When between two anchors, pick the lower unless evidence clearly
supports the higher. Always cite concrete evidence (file:line, the missing test, the unhandled
case) — never score on vibes. Mark items that cannot apply to the artifact as **N/A** (see
`checklist.md` for N/A and language-tool guidance); never fail an item for being inapplicable.

## Score anchors (apply to every gate)

- **5 — Excellent.** Fully satisfies the gate's applicable items; no concerns.
- **4 — Good.** Minor, non-blocking nits only.
- **3 — Adequate.** Works but has a real gap worth fixing; acceptable under time pressure.
- **2 — Weak.** A genuine problem that should block until addressed.
- **1 — Poor.** Serious deficiency; not trustworthy on this dimension.
- **0 — Absent/broken.** The gate is unmet entirely (e.g. no tests at all on risky logic; a clear
  security hole).

When you cannot verify a gate (can't run tests, no CI visibility), score on what's inspectable,
cap confidence, and say so in NOTES — do not default to 5 or 0.

---

## 1. Correctness & algorithm (weight 25, critical)

Absorbs checklist categories **Algorithm** and **Performance**.

Look for: correct logic for the intent including boundary/empty/null inputs; appropriate
algorithmic approach and a justified Big-O; recursion used only where it fits (no needless or
unbounded recursion); the provided example actually produces the stated output; return values
match the declared/expected types and contract; acceptable speed; no gratuitous extra loops or
quadratic blow-ups where a single pass would do.

- 5: Logic is clearly correct for the intent and edge inputs; complexity is appropriate and justified.
- 3: Works on the happy path but a plausible input is mishandled, or the approach is needlessly costly.
- ≤2: A path that will realistically be hit is wrong, the example/return values don't match, or it
  doesn't fulfill the intent.

## 2. Tests & CI (weight 18)

Absorbs checklist category **Tests**.

Look for: unit tests exercising the new/changed behaviour with assertions that would fail if the
logic broke; functional/integration tests where the change spans components; meaningful coverage
(the checklist's bar is >80%) of the changed code, not just imports; CI/CD configured and green
where visible. Coverage and CI are N/A only when genuinely unknowable — say so.

- 5: New behaviour and key edge cases tested with biting assertions; coverage healthy; CI green.
- 3: Some tests exist but miss an important path, or only cover the happy path, or CI absent.
- ≤2: No meaningful tests for risky/changed logic, or tests don't actually assert the behaviour.

## 3. Security & robustness (weight 18, critical)

Absorbs checklist category **Security** (incl. the robustness items).

Look for: no buffer overflow / unbounded buffer handling; no freezing — infinite loops, runaway
recursion, or memory leaks; no raw stacktraces or internals leaked to users; immutability where
state shouldn't change; exceptions caught and handled (not swallowed); resources closed (files,
streams, connections, locks); input validation on untrusted data; no deprecated APIs; no compiler/
runtime warnings left; no `eval` or equivalent dynamic-execution sinks. Also flag injection,
committed secrets, and missing authz on new endpoints.

- 5: No new exposure; untrusted input validated; resources released; no leaks or unsafe sinks.
- 3: A hardening gap that isn't directly exploitable but should be closed (e.g. an unclosed stream).
- ≤2: A plausibly exploitable hole, a leak/freeze risk, `eval` on untrusted input, or a committed
  secret. (Veto-level.)

## 4. Clean code & design (weight 18)

Absorbs checklist categories **Clean Code**, **Complexity**, **Paradigms**, **Coding Style**.

Look for: production-ready code with no dead code, no commented-out code, no debug code, no empty
blocks; correct namespaces/visibility modifiers; no global variables; correct data types and
structures; sensible design patterns without over-engineering; exceptions used instead of return
codes; doesn't return null where an empty/optional is better; classes marked final when not built
for inheritance; dependency injection over hidden construction; no dependency cycles; no needless
getters/setters. Complexity: no overly complex expressions, no obscure bitwise tricks, no magic
numbers/strings/variables/methods, respects the Law of Demeter, not over-engineered. Paradigms:
DRY (no duplication), SOLID, GRASP, coherent OOP, and not "quick & dirty". Style: linted clean,
formatter clean, follows community standards, sane folder structure, no mixed tabs vs spaces.
(Use the language-appropriate linter/formatter from the mapping in `checklist.md`.)

- 5: Clean, idiomatic, well-factored; lints and formats clean; no duplication or magic; fits conventions.
- 3: Understandable but has duplication, magic values, convention/lint violations, or awkward structure.
- ≤2: Hard to follow, copy-pasted logic, leftover dead/debug code, or design that fights maintenance.

## 5. Readability & documentation (weight 12)

Absorbs checklist categories **Readability** and **Documentation**.

Look for: clear, intention-revealing variable/function names; correct spelling; no double negations;
no deeply nested if/for/while (guard clauses preferred). Documentation: doc-comments on public
APIs (DocBlocks / JSDoc / docstrings per language); a README; usage instructions; CLI `--help`
where there's a CLI; no leftover TODOs or HACKs; appropriate logging; unusual behaviour explained
in comments; a UML/diagram where the design is non-trivial. README/usage/CLI/UML are N/A for a
bare diff — mark them so.

- 5: Reads cleanly; well named; public surface documented; README/usage present where applicable.
- 3: Understandable but under-documented, awkward names, deep nesting, or stray TODOs/HACKs.
- ≤2: Hard to follow, misleading names, or missing documentation where it's clearly needed.

## 6. Project & delivery hygiene (weight 9)

Absorbs checklist categories **Environment**, **Versioning**, **Language**, **i18n**, **Presentation**.

Look for: Environment — Dockerfile, docker-compose, and a `.env`/example for config. Versioning —
a proper git repo, many small focused commits, good commit messages, a `.gitignore`. Language —
declared package manager, a runtime/language version within its EOL window, reasonably current
dependencies. i18n — translations/externalised strings where user-facing text exists. Presentation
— coloured/clear shell output where there's CLI output.

Almost all of these are repo-level: when reviewing a **bare diff**, mark the whole gate **N/A** and
drop it from the score. When reviewing a **full repo/submission**, score it normally.

- 5: Reproducible env, clean git history, supported & current deps, i18n where needed.
- 3: Present but thin — e.g. few large commits, missing `.env` example, or aging deps.
- ≤2: No reproducible setup, no/poor version control hygiene, or EOL runtime.
