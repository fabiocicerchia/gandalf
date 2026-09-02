# Architecture map

Derived from source by automap 2.0. Every line is computed, not written. Regenerate with `automap map`; do not edit by hand.

## What this says about the system

Each item fired because a measurement crossed a threshold. The numbers and the evidence are from your code; the explanation is fixed text from a rule catalog, identical every time that rule fires on any repository. `automap rules` prints the catalog on its own so you can audit the claims before trusting them here. What none of it can tell you is why your team built it this way — that is what `automap adr` leaves blank.

| | count |
|---|---:|
| Serious | 1 |
| Worth attention | 1 |
| Minor | 3 |
| Notes | 1 |

### Serious · 1 component pair(s) are repeatedly changed in the same commit despite having no import between them.

**Why it matters.** This is coupling the import graph cannot see, and it is often the coupling that actually hurts. Two components that must change together are coupled through something — a wire format, a database column, a duplicated constant, an assumption — and because nothing links them in code, nothing warns the person who changes only one.

**What usually causes it.** A shared schema or protocol with no shared definition, copy-pasted logic that has to be kept in step, or a genuine feature that was split across a boundary in the wrong place.

**What to do.** Make the hidden contract explicit: one shared type, schema, or constant that both sides import, so the next change to it cannot silently miss a side. Where the split itself was wrong, moving the code together is cheaper than maintaining the coincidence.

<details><summary>Evidence</summary>

- `extensions` and `src` — 4 commits together, no import

</details>

<sub>`ARCH-COCHANGE` · Change over time</sub>

### Worth attention · 2 module(s) are more than 4× the median size (102 lines); the largest is 612 lines.

**Why it matters.** A file this far from the median is rarely one idea. It cannot be reviewed in one sitting, it produces merge conflicts between people working on unrelated things, and it hides its internal structure from every tool that works at file granularity — including this one, which sees it as a single node.

**What usually causes it.** Accretion. Each addition was small and reasonable, and no single commit was the one that made it too large.

**What to do.** Split along the lines its own imports suggest: the groups of functions that share dependencies are usually the natural modules. Do it before it becomes the file everyone avoids.

<details><summary>Evidence</summary>

- `src/gandalf/plugins.py` — 612 lines
- `extensions/vscode/src/extension.ts` — 558 lines

</details>

<sub>`ARCH-GODFILE` · Size and shape</sub>

### Minor · 1 of 702 imports (0%) point at something this tool could not find on disk.

**Why it matters.** Every conclusion below is drawn from the edges that did resolve. Unresolved local imports mean real dependencies are missing from the graph, so cycles may go undetected and coupling is understated. A map with unknown holes is more dangerous than no map, because it invites confidence.

**What usually causes it.** Usually a source root, path alias, or monorepo package boundary that has not been declared. Occasionally generated code, or imports assembled at runtime from strings.

**What to do.** Add the missing `source_roots` or `aliases` to `.automap.json` and rerun until this is zero, or publish the graph as a lower bound and say so where it is published.

<details><summary>Evidence</summary>

- TypeScript: 1 unaccounted

</details>

<sub>`ARCH-COVERAGE` · Evidence quality</sub>

### Minor · 1 component(s) sit far from the balance between how abstract they are and how much depends on them.

**Why it matters.** Two bad corners exist. A component that is concrete and widely depended on is rigid: it cannot change without breaking its dependents, and it offers no seam to extend through. A component that is abstract and depended on by nothing is unused indirection: interfaces with one implementation and no callers.

**What usually causes it.** Rigidity comes from exposing concrete types across a boundary instead of an interface. Unused abstraction comes from designing for a second implementation that never arrived.

**What to do.** For the rigid ones, introduce an interface on the depended-on side and let dependents bind to that. For the unused abstractions, collapse the indirection until a second implementation actually exists.

<details><summary>Evidence</summary>

- `extensions` — abstractness 0.32, instability 0.0, distance 0.68

</details>

<sub>`ARCH-MAINSEQ` · Structure</sub>

### Minor · 42 modules over 30 lines are imported by nothing in this tree.

**Why it matters.** Unreferenced code still gets read, still gets updated during refactors, and still appears in searches. If it is genuinely unused it is a tax on every future reader. If it is used through a mechanism no static tool can see, that mechanism is exactly the thing worth writing down, because nobody will infer it.

**What usually causes it.** Entry points invoked by a runner or framework, plugins loaded by name, code kept 'just in case', or genuine leftovers.

**What to do.** Check each against how it is actually invoked. Delete what is dead; for the rest, record the invocation mechanism where a reader will find it.

<details><summary>Evidence</summary>

- `extensions/vscode/esbuild.mjs` — 61 lines
- `extensions/vscode/src/bench.ts` — 152 lines
- `extensions/vscode/src/extension.ts` — 558 lines
- `scripts/bench.py` — 376 lines
- `scripts/chart.py` — 202 lines
- `src/gandalf/gates/_toolchain.py` — 237 lines
- `src/gandalf/gates/bandit.py` — 56 lines
- `src/gandalf/gates/build.py` — 59 lines

</details>

<sub>`ARCH-ORPHAN` · Size and shape</sub>

### Note · No layering declared, so layer checks are off.

**Why it matters.** Cycles and coupling are measurable without knowing your intent, but 'this dependency should not exist' is not. Declaring layers is how you tell the tool what the design is supposed to be, which turns a description into a check that can fail in CI.

**What usually causes it.** Most repositories never write the layering down; it lives in review comments and in whoever has been there longest.

**What to do.** Add a `layers` map to `.automap.json`, ordered top to bottom. Start with the layering you believe you have — the first run will tell you whether you have it.

<sub>`ARCH-NOLAYERS` · Evidence quality</sub>

## Inside the files

The section above reasons about the import graph, where an edge either exists or does not. This one reads inside files, and its evidence is weaker by construction. Python is analysed with its real grammar, so complexity, nesting, length and parameter counts are exact. Every other language is matched lexically against comment-stripped source: those rules report **the presence of a construct, not a proven defect**. There is no dataflow analysis here. A flagged line may be perfectly correct in context, and an unflagged file may still be wrong. Read these as places to look, not as a verdict.

| category | findings |
|---|---:|
| Security | 3 |
| Performance | 3 |
| Scalability | 3 |
| Algorithms and data structures | 2 |
| Maintainability | 4 |
| Readability | 1 |

### Security

**Serious · SEC-EVAL** — 8 occurrence(s) across 2 file(s).

*Why it matters.* Evaluating a string as code means the set of things this program can do is not fixed at build time. If any part of that string is influenced by input, the answer is 'anything the process can do'. It also defeats every other tool in the pipeline: type checkers, linters, and this one cannot see through it.

*What usually causes it.* Usually dynamic dispatch, config-driven behaviour, or deserialising something convenient. Almost always reachable another way.

*What to do.* Replace with an explicit dispatch table mapping allowed names to functions. If the input really is arbitrary code, isolate it in a sandboxed process with its own privileges.

<details><summary>Evidence</summary>

- `extensions/vscode/src/progress.ts:42` — `exec(`
- `extensions/vscode/src/progress.ts:53` — `exec(`
- `extensions/vscode/src/runner.ts:138` — `exec(`
- `extensions/vscode/src/runner.ts:252` — `exec(`
- `extensions/vscode/src/runner.ts:383` — `exec(`
- `extensions/vscode/src/runner.ts:419` — `exec(`

</details>

**Serious · SEC-SHELL** — 114 occurrence(s) across 14 file(s).

*Why it matters.* Handing a string to a shell means the shell parses it: quoting, globbing, pipes, and semicolons all apply. Any input that reaches that string can add another command. This is command injection, and it is one of the oldest and most reliably exploited defects there is.

*What usually causes it.* Building a command line by concatenation because it is the shortest way to call an external tool.

*What to do.* Pass an argument list rather than a string, and do not involve a shell: `subprocess.run([...], shell=False)`, `execFile`, `ProcessBuilder`. If a shell feature is genuinely needed, validate against an allowlist first.

<details><summary>Evidence</summary>

- `extensions/vscode/esbuild.mjs:32` — ``src/test/${`
- `extensions/vscode/scripts/copy-package-files.mjs:16` — ``copied ${`
- `extensions/vscode/src/bench.ts:50` — ``gate${`
- `extensions/vscode/src/bench.ts:53` — ``gate${g}: ${`
- `extensions/vscode/src/bench.ts:56` — ``src/pkg${i % 200}/mod${`
- `extensions/vscode/src/bench.ts:58` — ``finding ${g}-${`

</details>

**Worth attention · SEC-WEAKCRYPTO** — 1 occurrence(s) across 1 file(s).

*Why it matters.* MD5 and SHA-1 have practical collision attacks, DES has an exhaustible key space, and ECB mode leaks structure because identical plaintext blocks produce identical ciphertext. Each is fine for a checksum and wrong for anything where an adversary benefits from forging or reading.

*What usually causes it.* Copied from an older example, or chosen when the use was non-security and later became security-relevant.

*What to do.* For integrity use SHA-256 or better; for passwords use argon2, scrypt, or bcrypt, never a plain hash; for encryption use AES-GCM or a library that picks the mode for you. Where the use is genuinely a non-security checksum, say so in a comment so the next reader does not have to re-derive it.

<details><summary>Evidence</summary>

- `src/gandalf/suppress.py:52` — `sha1(`

</details>

### Performance

**Serious · PERF-NPLUSONE** — 2 occurrence(s) across 2 file(s).

*Why it matters.* A query or request issued once per iteration turns one operation into N. The code reads correctly and passes tests on small fixtures, then degrades linearly with data size in production. This is the single most common cause of an endpoint that was fast in development and is slow in production.

*What usually causes it.* Iterating over parents and fetching each one's children, which is the natural way to express it and the natural thing an ORM makes easy.

*What to do.* Fetch the set in one call: a join, an `IN` query, a batched request, or the ORM's eager-loading option. Where the calls are independent network requests, issue them concurrently rather than in sequence.

<details><summary>Evidence</summary>

- `extensions/vscode/src/bench.ts:138` — `store.findings(`
- `src/gandalf/llm.py:84` — `urlopen(`

</details>

**Worth attention · PERF-SYNCIO** — 13 occurrence(s) across 7 file(s).

*Why it matters.* Synchronous I/O blocks the event loop, which in a single-threaded runtime means every other request waits, not just this one. Throughput collapses under concurrency even though each individual operation looks fast.

*What usually causes it.* Startup and CLI code where blocking is fine, later reused inside a request path where it is not.

*What to do.* Use the promise-based forms and await them. Where the call really is startup-only, keep it out of any module that a request path imports so it cannot be reused by accident.

<details><summary>Evidence</summary>

- `extensions/vscode/esbuild.mjs:30` — `readdirSync(`
- `extensions/vscode/scripts/copy-package-files.mjs:15` — `copyFileSync(`
- `extensions/vscode/src/bench.ts:99` — `mkdtempSync(`
- `extensions/vscode/src/bench.ts:103` — `mkdirSync(`
- `extensions/vscode/src/bench.ts:104` — `writeFileSync(`
- `extensions/vscode/src/bench.ts:148` — `rmSync(`

</details>

**Worth attention · PERF-NESTEDLOOP** — 2 occurrence(s) across 2 file(s).

*Why it matters.* Three levels of loop nesting means work proportional to the product of three collection sizes. That is fine when the inner collections are bounded and quietly catastrophic when one of them grows with data.

*What usually causes it.* An inner lookup written as a scan because the collection was small when the code was written.

*What to do.* Check what each level iterates over and which of them can grow. The usual fix is to replace the innermost scan with a dictionary or set built once outside the loops.

<details><summary>Evidence</summary>

- `extensions/vscode/src/exclude.ts:57` — `3 levels of loop nesting`
- `src/gandalf/plugins.py:231` — `3 levels of loop nesting`

</details>

### Scalability

**Worth attention · SCL-INMEMSTATE** — 1 occurrence(s) across 1 file(s).

*Why it matters.* Module-level mutable state lives in one process. The moment a second instance runs — a second worker, a second pod, a rolling deploy — each has its own copy, and behaviour depends on which one served the request. It is also shared between concurrent requests within the process, which makes it a correctness problem before it is a scaling one.

*What usually causes it.* A cache, a registry, or a counter that was correct when the service ran as a single process, and was never revisited when it did not.

*What to do.* Decide whether the state is per-request, per-process, or global. Per-request belongs in the request context; global belongs in a shared store such as Redis or the database; per-process caches need an explicit bound and must tolerate being cold.

<details><summary>Evidence</summary>

- `src/gandalf/plugins.py:118` — `_TOOL_SOURCE: dict[str, str] = {}`

</details>

**Minor · SCL-SLEEPPOLL** — 1 occurrence(s) across 1 file(s).

*Why it matters.* Polling with a sleep sets a floor on latency and a ceiling on throughput at the same time: work waits for the next tick, and every waiter costs a thread or a connection while it sleeps. Under load the sleeps do not amortise, they accumulate.

*What usually causes it.* Waiting for something to become ready, where a notification mechanism did not exist or seemed heavier than a loop.

*What to do.* Use the blocking primitive the library already provides: a queue, a condition variable, a notification channel, or a webhook. Where polling is genuinely required, back off exponentially and cap the wait.

<details><summary>Evidence</summary>

- `src/gandalf/llm.py:93` — `time.sleep(`

</details>

**Minor · SCL-UNBOUNDEDREAD** — 2 occurrence(s) across 1 file(s).

*Why it matters.* Reading an entire file, result set, or response into memory works until the input grows. The failure mode is not gradual: it is a process killed for memory, usually in production, usually on the largest customer.

*What usually causes it.* The input was small and bounded when the code was written, and often still is in every test fixture.

*What to do.* Stream instead: iterate the file line by line, page the query, or process the response incrementally. Where loading it all is genuinely required, enforce an explicit limit and fail clearly when it is exceeded rather than by exhaustion.

<details><summary>Evidence</summary>

- `src/gandalf/pr_comments.py:264` — `.read()`
- `src/gandalf/pr_comments.py:433` — `.read()`

</details>

### Algorithms and data structures

**Worth attention · ALGO-LINEARSCAN** — 11 occurrence(s) across 6 file(s).

*Why it matters.* Membership testing against a list or array is a linear scan. Inside a loop that makes the whole operation quadratic, which is the most common accidental O(n²) in ordinary application code: no algorithm was chosen, a data structure was.

*What usually causes it.* A list was the obvious container when the code was written, and membership testing was added later without revisiting the choice.

*What to do.* Build a set or dictionary once before the loop and test against that. Membership goes from linear to constant, and the change is usually one line.

<details><summary>Evidence</summary>

- `extensions/vscode/esbuild.mjs:7` — `.includes(`
- `extensions/vscode/esbuild.mjs:8` — `.includes(`
- `extensions/vscode/esbuild.mjs:12` — `.includes(`
- `extensions/vscode/esbuild.mjs:14` — `.includes(`
- `extensions/vscode/src/exclude.ts:29` — `.indexOf(`
- `extensions/vscode/src/exclude.ts:30` — `.indexOf(`

</details>

**Worth attention · ALGO-SORTLOOP** — 12 occurrence(s) across 10 file(s).

*Why it matters.* Sorting inside a loop repeats an n log n operation on data that has usually not changed, or has changed in a way that could be maintained incrementally. The total cost is a factor of n above what the work requires.

*What usually causes it.* Needing ordered data at a point inside the loop, with the sort placed where the need appears rather than where the data is produced.

*What to do.* Sort once before the loop. If the collection genuinely changes each iteration, a heap or a sorted container maintains order at log n per insertion instead of n log n per pass.

<details><summary>Evidence</summary>

- `extensions/vscode/src/store.ts:152` — `.sort(`
- `scripts/bench.py:121` — `sorted(`
- `scripts/bench.py:128` — `sorted(`
- `scripts/chart.py:145` — `.sort(`
- `src/gandalf/__main__.py:124` — `sorted(`
- `src/gandalf/cache.py:122` — `sorted(`

</details>

### Maintainability

**Worth attention · MNT-SWALLOW** — 5 occurrence(s) across 4 file(s).

*Why it matters.* An empty handler converts a failure into a silent wrong answer. The program continues in a state its author did not anticipate, and the eventual symptom appears somewhere unrelated with no trace of the original cause. Debugging time for these is measured in days.

*What usually causes it.* A failure that was noisy and not understood, silenced to get on with the work, and never revisited.

*What to do.* Handle it, or log it with enough context to identify the case, or let it propagate. If it is genuinely expected and safe, catch the specific exception type and write a comment saying why nothing needs to happen.

<details><summary>Evidence</summary>

- `extensions/vscode/src/extension.ts:433` — `catch {`
- `extensions/vscode/src/history.ts:44` — `catch {`
- `extensions/vscode/src/parse.ts:214` — `catch {`
- `extensions/vscode/src/runner.ts:130` — `catch {                                  }`
- `extensions/vscode/src/runner.ts:194` — `catch {                                              }`

</details>

**Worth attention · MNT-COMPLEX** — 25 of 339 Python functions (7%) have a cyclomatic complexity of 12 or more; the highest is 50.

*Why it matters.* Complexity counts the independent paths through a function, which is also the number of test cases needed to cover it and the number of cases a reader must hold at once. Past about ten, reviewers stop simulating the function and start trusting it, which is where defects survive review.

*What usually causes it.* Requirements added one branch at a time. No single change made the function complex.

*What to do.* Extract the branches that belong together into named functions; the names are usually already in the comments or the variable names. Guard clauses that return early remove nesting without moving logic.

<details><summary>Evidence</summary>

- `src/gandalf/__main__.py:138` — `main` complexity 50, 234 lines, nesting 4
- `src/gandalf/render_text.py:31` — `render_terminal` complexity 23, 73 lines, nesting 3
- `src/gandalf/gates/supply_chain.py:114` — `run` complexity 21, 49 lines, nesting 1
- `src/gandalf/pr_comments.py:133` — `build` complexity 19, 46 lines, nesting 4
- `src/gandalf/gates/compliance.py:48` — `run` complexity 18, 53 lines, nesting 1
- `src/gandalf/outputs.py:108` — `write_outputs` complexity 16, 58 lines, nesting 2
- `src/gandalf/gates/scorecard.py:38` — `run` complexity 16, 46 lines, nesting 2
- `src/gandalf/render_html.py:215` — `render_html` complexity 15, 112 lines, nesting 2

</details>

**Minor · MNT-LONGFUNC** — 4 of 339 Python functions (1%) are 80 lines or longer; the longest is 234.

*Why it matters.* Length is a proxy for how much has to be understood before any part can be changed. A function that does not fit on a screen cannot be checked against its own beginning, and long functions accumulate local variables whose lifetimes overlap in ways nothing enforces.

*What usually causes it.* Sequential steps written where they occur, each addition smaller than the threshold for extracting it.

*What to do.* Extract the steps that operate on a distinct set of locals. If the extracted function needs six parameters, that group of values is a type worth naming.

<details><summary>Evidence</summary>

- `src/gandalf/__main__.py:138` — `main`, 234 lines
- `src/gandalf/cli.py:26` — `build_parser`, 180 lines
- `src/gandalf/render_html.py:215` — `render_html`, 112 lines
- `src/gandalf/gates/codeql.py:130` — `_analyze`, 88 lines

</details>

**Minor · MNT-PARAMS** — 10 of 339 Python functions (3%) take 6 or more parameters; the largest takes 14.

*Why it matters.* A long parameter list is usually several values that travel together and have no name. Callers must remember an order, positional mistakes between same-typed parameters type-check silently, and every new requirement adds another.

*What usually causes it.* Passing context down through layers, one value at a time as each became necessary.

*What to do.* Group the parameters that always appear together into a dataclass or record. The name of that group is usually a concept the codebase was missing.

<details><summary>Evidence</summary>

- `src/gandalf/summary.py:33` — `print_summary`, 14 parameters
- `src/gandalf/outputs.py:48` — `build_payload`, 13 parameters
- `src/gandalf/outputs.py:108` — `write_outputs`, 9 parameters
- `src/gandalf/skillgate.py:203` — `_prompt`, 7 parameters
- `src/gandalf/__main__.py:38` — `_run_gates`, 6 parameters
- `src/gandalf/pr_comments.py:181` — `review_payload`, 6 parameters

</details>

### Readability

**Worth attention · RDB-NESTING** — 10 of 339 Python functions (3%) nest control flow 4 levels or deeper.

*Why it matters.* Each level of nesting is a condition the reader must keep true in their head for everything inside it. Depth compounds: at four levels the reader is tracking four simultaneous invariants to understand one line. Nesting correlates with defects more strongly than length does.

*What usually causes it.* Conditions added around existing code rather than in front of it, because wrapping is a smaller diff than restructuring.

*What to do.* Invert the conditions and return early, so the exceptional cases leave at the top and the main path stays at one level. Extracting the innermost block into its own function achieves the same and gives the block a name.

<details><summary>Evidence</summary>

- `src/gandalf/plugins.py:576` — `discover_gates`, depth 5
- `src/gandalf/__main__.py:138` — `main`, depth 4
- `src/gandalf/plugins.py:245` — `_compiled_ignores`, depth 4
- `src/gandalf/pr_comments.py:71` — `added_lines`, depth 4
- `src/gandalf/pr_comments.py:133` — `build`, depth 4
- `src/gandalf/render_html.py:78` — `_md_to_html`, depth 4

</details>

---

The rest of this document is the evidence those findings were computed from.

## Coverage

What was read, and where every import went. Third-party means the target is expected to live outside this tree. Unaccounted means an import that looks local and resolved to nothing: those are edges missing from the graph below, usually a source root or path alias this tool has not been told about.

| Language | Fidelity | Files | Imports | Internal | Third-party | Unaccounted |
|---|---|---:|---:|---:|---:|---:|
| JavaScript | structural | 2 | 5 | 1 | 4 | 0 |
| Python | parsed | 68 | 623 | 104 | 519 | 0 |
| Ruby | heuristic | 1 | 0 | 0 | 0 | 0 |
| TypeScript | structural | 18 | 74 | 43 | 30 | **1** |

Unaccounted imports by language: TypeScript 1. Until that is zero, treat this graph as a lower bound on coupling.

## Shape

- 89 modules across 4 components
- 118 internal import edges, 0 component couplings
- 13875 lines
- propagation cost 0% — the share of other components an average component can reach through import paths

## Component graph

```mermaid
graph LR
  _mdl_style[".mdl_style<br/><small>Ruby · 1 mod · 16 loc</small>"]
  extensions["extensions<br/><small>JavaScript/TypeScript · 20 mod · 3321 loc</small>"]
  scripts["scripts<br/><small>Python · 2 mod · 578 loc</small>"]
  src["src<br/><small>Python · 66 mod · 9960 loc</small>"]
```

Dashed edges came from heuristic scanners. Thick borders are in a cycle. Labels count import sites.

## Ways in, and where they lead

This is not a record of what users do. That lives in analytics, and no static tool can recover it: a route nobody has ever called looks exactly like the one every session hits. What follows is the set of journeys the code **permits** — every way in, every navigation edge between screens, and what each way in can reach.

| Kind | Count | Frameworks |
|---|---:|---|
| Event and queue handlers | 5 | queue consumer |

### What each way in reaches

Components a route can touch by following imports, to a depth of four. This is the blast radius of that endpoint, and the set of code a change to it can disturb.

| Entry | Handler | Components reached |
|---|---|---:|
| `ADDEVENTLISTENER click` | `extensions/vscode/src/report.ts:25` | 0  |
| `ON close` | `extensions/vscode/src/runner.ts:244` | 0  |
| `ON data` | `extensions/vscode/src/runner.ts:225` | 0  |
| `ON error` | `extensions/vscode/src/runner.ts:239` | 0  |
| `ON exit` | `extensions/vscode/src/runner.ts:243` | 0  |

## The nouns

123 types declared: 23 inheritance and 19 composition relationships between types defined in this tree. Relationships to types declared elsewhere are omitted rather than guessed, so this is a lower bound. 89 types were read with a real parser; the rest come from declaration syntax, which is reliable for the declaration and weaker for the member lists.

### `src`

```mermaid
classDiagram
  class BundlerAuditGate {
    +name
    +ecosystem
    +langs
    +markers
    +binary
    +check(2)
  }
  class CheckstyleGate {
    +name
    +ecosystem
    +langs
    +markers
    +binary
    +_config(1)
    +check(2)
  }
  class CodebaseArchitectureGate {
    +name
    +category
    +skills
    +pass_threshold
    +unit
    +task
  }
  class ComposerAuditGate {
    +name
    +ecosystem
    +langs
    +markers
    +binary
    +check(2)
  }
  class CppBuildGate {
    +name
    +ecosystem
    +langs
    +markers
    +binary
    +check(2)
  }
  class CppcheckGate {
    +name
    +ecosystem
    +langs
    +markers
    +binary
    +check(2)
  }
  class CtestGate {
    +name
    +ecosystem
    +langs
    +markers
    +binary
    +check(2)
  }
  class DotnetAuditGate {
    +name
    +ecosystem
    +langs
    +markers
    +binary
    +check(2)
  }
  class DotnetBuildGate {
    +name
    +blocking
    +ecosystem
    +langs
    +markers
    +binary
    +check(2)
  }
  class GateOutcome {
    <<enumeration>>
    +PASS
    +WARN
    +FAIL
  }
  class SkillGate {
    +name: str
    +blocking
    +skills: tuple[str,...]
    +task
    +pass_threshold
    +needs_request
    +… 1 more fields
    +run(1)
    +_nothing_to_judge(4)
    +_verdict(1)
    +_prompt(6)
  }
  class ToolchainGate {
    +blocking
    +ecosystem
    +markers: tuple[str,...]
    +binary
    +run(1)
    +check(2)
    +missing(1)
  }
  ToolchainGate <|-- BundlerAuditGate
  ToolchainGate <|-- CheckstyleGate
  SkillGate <|-- CodebaseArchitectureGate
  ToolchainGate <|-- ComposerAuditGate
  ToolchainGate <|-- CppBuildGate
  ToolchainGate <|-- CppcheckGate
  ToolchainGate <|-- CtestGate
  ToolchainGate <|-- DotnetAuditGate
  ToolchainGate <|-- DotnetBuildGate
```

### `extensions`

```mermaid
classDiagram
  class DiagnosticGroup {
    <<interface>>
    +findings: Finding[]
    +settings: Settings
  }
  class FileNode {
    <<interface>>
    +kind
    +id: string
    +label: string
    +uri: vscode.Uri
    +children: FindingNode[]
  }
  class Finding {
    <<interface>>
    +id: string
    +gate: string
    +category: string
    +outcome: Outcome
    +severity: Severity
    +severityLabel: string
    +… 8 more fields
  }
  class FindingNode {
    <<interface>>
    +kind
    +id: string
    +finding: Finding
  }
  class FindingsView {
    +view: vscode.TreeView<Node>
    +scope: ScopeFilter
    +model: Model
    +allFindings: Finding[]
    +visibleFindings: Finding[]
    +treeDataProvider: this,
    +… 27 more fields
    +constructor(1)
    +register(0)
    +setScope(1)
    +expandAll(0)
    +pickFilters(0)
    +… 13 more methods
  }
  class GateEvent {
    <<interface>>
    +event
    +index: number
    +total: number
  }
  class Job {
    <<interface>>
    +folder: vscode.WorkspaceFolder
    +kind: ScanKind
    +relPath: string
    +absPath: string
    +commit: string
    +llm: boolean
    +… 3 more fields
  }
  class LastRun {
    <<interface>>
    +scope: string
    +verdict: Snapshot[
    +score: number
    +at: number
    +durationMs: number
  }
  class Model {
    <<interface>>
    +roots: Node[]
  }
  class Payload {
    <<interface>>
    +scope: string
    +verdict: Outcome
    +score: number
    +skipped_gates: string[]
    +disabled_gates: string[]
    +gates: RawGate[]
  }
  class RawFinding {
    <<extensions.vscode.src.types>>
  }
  class RawGate {
    <<interface>>
    +name: string
    +outcome: Outcome
    +score: number
    +summary: string
    +findings: RawFinding[]
    +category: string
    +… 2 more fields
  }
  class Settings {
    <<extensions.vscode.src.config>>
  }
  class Snapshot {
    <<interface>>
    +payload: Payload
    +findings: Finding[]
    +blocked: string[]
    +inapplicable: string[]
    +jsonPath: string
    +htmlPath: string
    +… 2 more fields
  }
  RawGate <|-- GateEvent
  DiagnosticGroup *-- Finding : findings
  DiagnosticGroup *-- Settings : settings
  FileNode *-- FindingNode : children
  FindingNode *-- Finding : finding
  FindingsView *-- Finding : allFindings
  FindingsView *-- Model : model
  LastRun *-- Snapshot : verdict
  Payload *-- RawGate : gates
  RawGate *-- RawFinding : findings
  Snapshot *-- Finding : findings
  Snapshot *-- Payload : payload
```

**Declared but never implemented in this tree:** `Check`, `Commit`, `DiagnosticGroup`, `FileNode`, `Finding`, `FindingNode`, `Gate`, `GateEvent`. Either the implementations live outside this tree, or the abstraction has no second case yet and the indirection is not paying for itself.

## Dependency matrix

Row depends on column; the number is how many import sites hold it. Components are ordered leaves first, so an ordinary dependency points to an earlier column and lands below the diagonal. **Every bold cell above the diagonal is a dependency pointing backwards.** Those cells are the whole review: scan the upper triangle and stop. A matrix is used rather than a drawing because it stays readable at any size.

| # | component | 1 | 2 | 3 | 4 |
|---|---|---|---|---|---|
| 1 | `src` | — | · | · | · |
| 2 | `scripts` | · | — | · | · |
| 3 | `extensions` | · | · | — | · |
| 4 | `.mdl_style` | · | · | · | — |

0 cells above the diagonal.

## Reachability from entry points

What each root actually pulls in, to a depth of three. Nothing imports these modules, so they are where a reader has to start.

**src/gandalf/__main__.py**

```
src.gandalf.__main__  (Python)
├─ src.gandalf.base  (Python)
├─ src.gandalf.cache  (Python)
│  ├─ src.gandalf.base  (Python)
│  └─ src.gandalf.plugins  (Python)
│     ├─ src.gandalf.base  (Python)
│     └─ src.gandalf.debug  (Python)
├─ src.gandalf.cli  (Python)
│  ├─ src.gandalf.cache  (Python)  ↑ shown above
│  └─ src.gandalf.suppress  (Python)
│     ├─ src.gandalf.base  (Python)
│     ├─ src.gandalf.findings  (Python)
│     └─ src.gandalf.plugins  (Python)  ↑ shown above
├─ src.gandalf.config  (Python)
├─ src.gandalf.debug  (Python)
├─ src.gandalf.fixers  (Python)
│  └─ src.gandalf.debug  (Python)
├─ src.gandalf.llm  (Python)
│  └─ src.gandalf.debug  (Python)
└─ src.gandalf.outputs  (Python)
   ├─ src.gandalf.badge  (Python)
   │  ├─ src.gandalf.base  (Python)
   │  └─ src.gandalf.report  (Python)
   ├─ src.gandalf.findings  (Python)
   ├─ src.gandalf.junit  (Python)
   │  ├─ src.gandalf.base  (Python)
   │  └─ src.gandalf.report  (Python)  ↑ shown above
   ├─ src.gandalf.plugins  (Python)  ↑ shown above
   ├─ src.gandalf.pr_comments  (Python)
   │  ├─ src.gandalf.base  (Python)
   │  ├─ src.gandalf.findings  (Python)
   │  ├─ src.gandalf.report  (Python)  ↑ shown above
   │  └─ src.gandalf.suggest  (Python)
   ├─ src.gandalf.render_html  (Python)
   │  ├─ src.gandalf.base  (Python)
   │  ├─ src.gandalf.html_assets  (Python)
   │  ├─ src.gandalf.plugins  (Python)  ↑ shown above
   │  └─ src.gandalf.report  (Python)  ↑ shown above
   ├─ src.gandalf.report  (Python)  ↑ shown above
   └─ src.gandalf.sarif  (Python)
      ├─ src.gandalf.base  (Python)
      ├─ src.gandalf.findings  (Python)
      ├─ src.gandalf.report  (Python)  ↑ shown above
      └─ src.gandalf.suppress  (Python)  ↑ shown above
└─ … 9 more
```

**extensions/vscode/src/extension.ts**

```
extensions.vscode.src.extension  (TypeScript)
├─ extensions.vscode.src.config  (TypeScript)
│  └─ extensions.vscode.src.types  (TypeScript)
├─ extensions.vscode.src.diagnostics  (TypeScript)
│  ├─ extensions.vscode.src.config  (TypeScript)  ↑ shown above
│  ├─ extensions.vscode.src.parse  (TypeScript)
│  │  └─ extensions.vscode.src.types  (TypeScript)
│  └─ extensions.vscode.src.types  (TypeScript)
├─ extensions.vscode.src.doctor  (TypeScript)
│  ├─ extensions.vscode.src.config  (TypeScript)  ↑ shown above
│  ├─ extensions.vscode.src.log  (TypeScript)
│  └─ extensions.vscode.src.runner  (TypeScript)
│     ├─ extensions.vscode.src.config  (TypeScript)  ↑ shown above
│     ├─ extensions.vscode.src.events  (TypeScript)
│     ├─ extensions.vscode.src.log  (TypeScript)
│     ├─ extensions.vscode.src.progress  (TypeScript)
│     └─ extensions.vscode.src.types  (TypeScript)
├─ extensions.vscode.src.exclude  (TypeScript)
├─ extensions.vscode.src.findingsView  (TypeScript)
│  ├─ extensions.vscode.src.parse  (TypeScript)  ↑ shown above
│  ├─ extensions.vscode.src.store  (TypeScript)
│  │  ├─ extensions.vscode.src.parse  (TypeScript)  ↑ shown above
│  │  └─ extensions.vscode.src.types  (TypeScript)
│  └─ extensions.vscode.src.types  (TypeScript)
├─ extensions.vscode.src.history  (TypeScript)
├─ extensions.vscode.src.log  (TypeScript)
└─ extensions.vscode.src.parse  (TypeScript)  ↑ shown above
└─ … 7 more
```

**scripts/bench.py**

```
scripts.bench  (Python)
```

## Coupling

| Component | Languages | Modules | LOC | Fan-in | Fan-out | Instability |
|---|---|---:|---:|---:|---:|---:|
| `.mdl_style` | Ruby | 1 | 16 | 0 | 0 | 0.0 |
| `extensions` | JavaScript, TypeScript | 20 | 3321 | 0 | 0 | 0.0 |
| `scripts` | Python | 2 | 578 | 0 | 0 | 0.0 |
| `src` | Python | 66 | 9960 | 0 | 0 | 0.0 |

Instability is fan-out / (fan-in + fan-out). A component many things depend on that itself depends widely propagates change in both directions.

## Cycles

None at component level.

## External dependencies

Third-party packages. Standard-library imports are counted separately below, because a dependency you cannot remove is not a design decision.

| Package | Sites | Components | First site |
|---|---:|---:|---|
| `gandalf` | 265 | 2 | scripts/bench.py:36 |
| `vscode` | 11 | 1 | extensions/vscode/src/config.ts:1 |
| `./test/vscode-shim` | 1 | 1 | extensions/vscode/src/bench.ts:22 |
| `chart` | 1 | 1 | scripts/bench.py:365 |

36 standard-library modules imported; most used: `__future__` (66), `json` (28), `pathlib` (25), `os` (20), `re` (16), `asyncio` (10), `dataclasses` (10), `shutil` (10), `sys` (9), `fs` (7), `path` (6), `tempfile` (6).

## Churn against size

Most-changed files in the last 12 months. This is where any map you carry in your head goes stale first.

| File | Lines touched | LOC | Language |
|---|---:|---:|---|
| `src/gandalf/report.py` | 1987 | 235 | Python |
| `src/gandalf/__main__.py` | 1575 | 375 | Python |
| `extensions/vscode/src/parse.ts` | 778 | 402 | TypeScript |
| `src/gandalf/plugins.py` | 682 | 612 | Python |
| `extensions/vscode/src/extension.ts` | 576 | 558 | TypeScript |
| `src/gandalf/pr_comments.py` | 524 | 436 | Python |
| `src/gandalf/findings.py` | 521 | 473 | Python |
| `extensions/vscode/src/runner.ts` | 510 | 452 | TypeScript |
| `src/gandalf/gates/supply_chain.py` | 433 | 317 | Python |
| `src/gandalf/gates/dynamic.py` | 415 | 259 | Python |
| `extensions/vscode/src/findingsView.ts` | 403 | 393 | TypeScript |
| `scripts/bench.py` | 376 | 376 | Python |
| `src/gandalf/suggest.py` | 354 | 354 | Python |
| `src/gandalf/sarif.py` | 349 | 181 | Python |
| `src/gandalf/skillgate.py` | 328 | 244 | Python |

## Public surface

<details><summary><code>extensions</code> — 78 exported</summary>


_Showing 40 of 78; `--full` lists them all._


`extensions.vscode.src.config`

- function readSettings:26
- interface Settings:6
- type Trigger:4

`extensions.vscode.src.diagnostics`

- class DiagnosticPublisher:47
- function describe:17
- interface DiagnosticGroup:38

`extensions.vscode.src.doctor`

- function buildToolsImage:115
- function runDoctor:41

`extensions.vscode.src.events`

- class EventParser:60
- interface GateEvent:20
- interface StartEvent:14
- type StreamEvent:26

`extensions.vscode.src.exclude`

- function enabledGlobs:1
- function excludePatterns:53
- function expandBraces:22
- function toGandalfPattern:38

`extensions.vscode.src.extension`

- function activate:33
- function deactivate:555

`extensions.vscode.src.findingsView`

- class FindingsView:63
- type Node:33

`extensions.vscode.src.history`

- function delta:77
- function parseLog:50
- function parseTrend:25
- function sparkline:61
- interface Commit:19
- interface TrendEntry:1

`extensions.vscode.src.log`

- function disposeLog:9
- function log:4

`extensions.vscode.src.parse`

- const LEVELS:74
- const LEVEL_LABEL:85
- const LEVEL_RANK:77
- const SEVERITIES:93
- const SEVERITY_LABEL:98
- const SEVERITY_RANK:95
- const VERDICT_WORD:96
- function compareFindings:342
- function gateStatus:256
- function gatesByStatus:375
- function normalize:365
- function normalizeGate:282

</details>

<details><summary><code>scripts</code> — 25 exported</summary>


`scripts.bench`

- const FINDINGS:41
- const HASH_FILES:43
- const REPEAT:45
- const REPO_FILES:44
- const TREE_PATHS:42
- def bench_annotate:213
- def bench_content_hash:93
- def bench_extension:274
- def bench_languages:226
- def bench_report_write:182
- def bench_tree_filter:76
- def main:327
- def peak_mb:63
- def table:306
- def timed:48

`scripts.chart`

- const BAR:42
- const DARK:29
- const GUTTER:40
- const LIGHT:20
- const PAIR_GAP:43
- const PANEL_GAP:45
- const RIGHT:41
- const ROW_GAP:44
- const WIDTH:39
- def render:139

</details>

<details><summary><code>src</code> — 309 exported</summary>


_Showing 40 of 309; `--full` lists them all._


`src.gandalf.__main__`

- def main:138

`src.gandalf.badge`

- const _COLOR:13
- def to_badge:20

`src.gandalf.base`

- class Gate:50
- class GateContext:40
- class GateOutcome:14
- class GateResult:24

`src.gandalf.cache`

- const ADVISORY_GATES:47
- const ADVISORY_TTL:46
- const CACHE_VERSION:38
- const DEFAULT_CACHE:34
- def content_hash:111
- def get:155
- def load:134
- def max_age:87
- def put:187
- def save:149
- def target_files:95
- def toolchain_salt:73

`src.gandalf.cli`

- const _DESCRIPTION:16
- def build_parser:26

`src.gandalf.config`

- class Config:40
- const CONFIG_FILENAME:37
- def load:83

`src.gandalf.debug`

- def enable:19
- def enabled:25
- def log:31

`src.gandalf.findings`

- const _MESSAGE_LEVEL:154
- const _TEXT_LOCATION:142
- const _TEXT_PATH:147
- def annotate:459
- def annotate_all:472
- def column:219
- def fingerprint_keys:444
- def first_int:176
- def first_str:161
- def line:214
- def message:229
- def message_level:255
- def normalise:350

</details>

---

**Not derivable from code.** Why these boundaries were chosen, what was rejected, and what constraint each one holds. `automap adr` scaffolds one file per decision point with the facts filled in and those questions blank.
