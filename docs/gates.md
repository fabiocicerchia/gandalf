# Gate ruleset

Every gandalf gate, what it checks, and how it scores. Gates are auto-discovered
from `src/gandalf/gates/` — each file exports one or more gate classes. The
scorecard groups gates by the **category** column below.

## Legend

- **Blocking** — a FAIL here reddens the verdict regardless of `fail_on`; a
  broken build or a leaked secret is a hard stop.
- **Advisory** — emits only PASS or WARN, never FAIL (the deterministic tool
  gates own the red line). All skill/LLM gates are advisory.
- **Self-skips** — the gate returns nothing to score when the relevant files or
  a live target are absent (e.g. no `.sql`, no `--target`), so it never
  false-fails a repo it doesn't apply to.
- **Degrades to WARN** — LLM/network gates never crash the run; if the endpoint
  is unreachable they warn instead of failing.
- **Fixes** — under `--fix` the gate runs its tool in write mode and repairs
  what it can before scoring; where the tool also reports *what* the fix is, a
  PR comment carries it as an applicable `suggestion` (see
  [CLI reference](cli.md#suggested-fixes)).

Select gates per repo in `.gandalf.toml`: `only = [...]` (allowlist),
`skip = [...]` (denylist). Env vars override the file.

---

## Security — SAST, secrets, DAST, fuzz

| Gate | Checks | Notes |
|------|--------|-------|
| `semgrep` | Pattern-based SAST across languages. | FAIL on any ERROR-severity rule or >5 findings, else WARN. A rule shipping an autofix suggests it on a PR. |
| `bandit` | Python SAST (common insecure APIs). | |
| `gitleaks` | Secret scanning (keys, tokens, credentials). | **Blocking** — a leak is a hard stop. |
| `codeql` | Semantic SAST; builds a queryable DB, deeper than pattern scanners. | Heavy; needs the CodeQL CLI. |
| `atheris` | Coverage-guided fuzzing of gandalf's own parsers. | Needs `tests/fuzz/fuzz_adapters.py` + the `atheris` package; self-skips otherwise. |
| `nikto` | Web-server misconfiguration sweep (DAST). | Needs a **live** `--target`; local-only, refuses remote hosts. |
| `sqlmap` | SQL-injection probe (DAST). | Live target only. |
| `dalfox` | XSS probe (DAST). | Live target only. |

## Dependencies — known-vuln scanning

| Gate | Checks | Notes |
|------|--------|-------|
| `osv` | `pip-audit` against Python requirements / project files. | |
| `osv_scanner` | OSV scan across lockfiles (multi-ecosystem). | |
| `govulncheck` | Go vulnerability database check. | Go toolchain. |
| `trivy` | Known-vuln scan of dependencies. | |

## Licensing

| Gate | Checks | Notes |
|------|--------|-------|
| `licenses` | Forbidden / restricted dependency licenses (via trivy). | Permissive licenses ignored. |

## Infrastructure — IaC, containers, CI config

| Gate | Checks | Notes |
|------|--------|-------|
| `checkov` | IaC misconfiguration (Terraform, k8s, Docker, …). | |
| `kics` | IaC misconfiguration (Checkmarx); complements checkov/trivy. | Needs its query assets. |
| `hadolint` | Dockerfile lint. | |
| `actionlint` | GitHub Actions workflow lint. | |

## Database — SQL lint + migration safety

| Gate | Checks | Notes |
|------|--------|-------|
| `sqlfluff` | SQL lint. | Self-skips without `.sql`; dialect via `GANDALF_SQL_DIALECT`. **Fixes** with `sqlfluff fix`. |
| `squawk` | Unsafe Postgres DDL (blocking locks, dropped columns, non-concurrent indexes). | Self-skips without `.sql`. |

## Code quality — lint, format, types, dead code

| Gate | Checks | Notes |
|------|--------|-------|
| `ruff` | Python lint. | **Fixes** with `ruff check --fix`; suggests the same edits on a PR. |
| `format` | `ruff format --check` — formatting drift (does not rewrite). | **Fixes** by rewriting with `ruff format`. |
| `mypy` | Python type checking. | |
| `vulture` | Python dead-code detection. | |
| `golangci_lint` | Go meta-linter (govet, staticcheck, errcheck, unused, …). | Go toolchain. **Fixes** with `--fix` (gofmt, goimports, misspell, …). |
| `eslint` | JS/TS lint. | Uses the repo's local config/deps. **Fixes** with `eslint --fix`; suggests the same edits on a PR. |
| `tsc` | TypeScript type check. | |
| `shellcheck` | Shell-script lint. | **Fixes** by applying its own `--format=diff` patch; suggests it on a PR. |
| `yamllint` | YAML lint. | |

## Complexity

| Gate | Checks | Notes |
|------|--------|-------|
| `lizard` | Cyclomatic complexity / function length thresholds. | Advisory (capped at WARN). |

## Documentation

| Gate | Checks | Notes |
|------|--------|-------|
| `interrogate` | Python docstring coverage. | WARNs below `GANDALF_DOCSTRING_MIN` (default 60%); self-skips without Python. |
| `mdl` | Markdown lint. | Advisory; self-skips without markdown. |
| `codespell` | Common misspellings in code/docs. | **Fixes** unambiguous typos with `-w`; suggests them on a PR. |

## Build & tests

| Gate | Checks | Notes |
|------|--------|-------|
| `build` | Changed Python actually compiles (syntax/parse). | **Blocking**. |
| `go_build` | `go build ./...`. | **Blocking**; Go toolchain. |
| `tests` | Runs the project's pytest suite. | |
| `go_test` | Runs `go test`. | |
| `node_test` | Runs `npm test`. | |
| `ci_act` | Runs `.github/workflows/*` locally via `act` in Docker. | Self-skips without workflows. |

## Best practices

| Gate | Checks | Notes |
|------|--------|-------|
| `compliance` | LLM judge scoring how fully the change satisfies the request. | Needs a request to judge; degrades to WARN. |
| `scorecard` | OSSF Scorecard — repo security-posture score (0–10). | |

---

## Skill-backed advisory gates

These turn a prose reviewing **skill** (an embedded `skills/<slug>/SKILL.md`
playbook) into an LLM-judged gate. They are **advisory** (PASS/WARN only) and
degrade to WARN when the model is unreachable or the skill isn't embedded. The
skill file is the rubric — edit it and the gate follows.

| Gate | Skill | Judges |
|------|-------|--------|
| `security_assessment` | `security-assessment` | CNCF TAG-Security-style posture of the change. |
| `quality_gate_review` | `quality-gate-review` | Six quality gates → GO / REVIEW / NO-GO verdict. |
| `ruthless_refactor` | `ruthless-refactor` | Duplication, dead code, needless indirection, reinvented stdlib. |
| `pr_code_summary` | `pr-code-summarizer` | Tech-lead 60-second read: what changed, risks, questions. |
| `codebase_architecture` | `improve-codebase-architecture` (+ `codebase-design`) | Shallow modules, leaky abstractions, deepening opportunities. |
| `grill_me` | `grill-me` (+ `grilling`) | Design readiness — interrogates every branch of a decision. |
| `well_architected` | `well-architected` | The change against the six Well-Architected pillars. |

> Skills live at the repo root under `skills/`, read from gandalf's **own**
> source tree (not the code under review), so `--commit`/`--staged` runs against
> a throwaway worktree still find them. A missing skill directory makes the
> strict skill gates error and the soft ones skip.

## Gates are plugins

A gate is any class with `name: str`, `blocking: bool`, and
`async def run(self, ctx) -> GateResult`. To add one, drop a `.py` file
exporting such a class into `gandalf/gates/` (or any dir on `GANDALF_GATES_PATH`) —
it's discovered automatically, no registry to edit. Name collisions let a
plugin override a built-in.

```python
# gandalf/gates/mygate.py
from gandalf.base import GateContext, GateOutcome, GateResult

class MyGate:
    name = "mygate"
    blocking = False

    async def run(self, ctx: GateContext) -> GateResult:
        return GateResult(self.name, GateOutcome.PASS, 1.0, "all good")
```

`ctx.changed_files` is empty in whole-tree mode (scan the repo) and populated in
`--staged`/`--commit` mode (scan just those files). `ctx.workdir` is where to run.

A gate can additionally opt into `--fix` by exposing
`async def fix(self, ctx) -> tuple[bool, str]` that applies its autofixes in
place and returns `(changed, message)`. Fixers run sequentially before scoring
(order matters: a lint fix and a reformat touch the same files), and `--fix`
cascades to the tool itself — `ruff --fix`, `ruff format`, `eslint --fix`,
`golangci-lint --fix`, `cargo clippy --fix`, `sqlfluff fix`, `codespell -w`,
and shellcheck's own `--format=diff` patch. `ctx.meta["fix"]` is `True` during
such a run, for a gate that wants to run its tool differently under it.

Returning `False` for `changed` is safe: the runner measures what each fixer
rewrote from the worktree, which is the only honest answer for the tools that
report nothing (`eslint --fix`) or exit non-zero on a perfectly successful run
(`eslint`, `golangci-lint`).

If the gate's tool can say *what* the fix is, keep that in the finding — ruff's
`fix`, shellcheck's `fix.replacements` and semgrep's `extra.fix` are read as-is,
and anything else can be normalised into a `_fix` block (see
`gandalf/suggest.py`). That is what becomes a one-click ` ```suggestion ` on a
pull request.

### Language relevance

gandalf detects the languages in scope and **only runs the gates relevant to them,
plus the language-agnostic ones** — so a Go change never triggers eslint or mypy.
Detection is by file extension + marker files (`go.mod`, `package.json`,
`tsconfig.json`, `pyproject.toml`, `Dockerfile`, …): from the **changed files** in
`--staged`/`--commit` mode, or the whole tracked tree by default. Irrelevant
language gates are dropped from the run entirely (listed under "skipped" in the
output and JSON), not just skipped-green.

A gate opts into this by setting a `langs` class attribute (e.g.
`langs = frozenset({"go"})`); gates without one are generic and always run. The
tag → language mapping lives in `scope.py` (`_EXT_LANG` / `_MARKER_LANG`).

### Built-in gates (36)

Each gate needs its external tool — on the host `PATH` or (for the scanners) in
the `gandalf-tools` image. When the tool is unavailable, or a dynamic gate has no
`--target`, or `compliance` has no `--title`/`--body`, the gate degrades to 🟡
WARN — so any repo still produces a full scorecard. Language-tagged gates (the
Python, Go, Node/TS groups, plus `shellcheck`=shell, `yamllint`=yaml,
`hadolint`=docker) run only when that language is in scope; everything else is
generic and always runs.

**Image = host-clean.** `gandalf-tools` provides the language-agnostic scanners
(ruff, semgrep, bandit, pip-audit, osv-scanner, trivy, gitleaks, checkov,
hadolint, scorecard, mypy, vulture, codespell, yamllint, shellcheck, actionlint,
mdl). The
`kics` gate runs from the official `checkmarx/kics` image (it ships its own query
assets), and `codeql` from a host `codeql` binary or a bundle image
(`GANDALF_CODEQL_IMAGE`) — the CodeQL CLI is a large bundle, not a pip/apt package,
so it's not baked into `gandalf-tools`. The Go and Node gates use your **host**
toolchain (`go`, `npx`, `npm`) —
you already have those — so they're never containerized.

If the image is stale or partial (a tool it claims to provide isn't actually
present), the gate degrades to 🟡 WARN — a missing dockerized tool never reads
as a clean pass.

Python:

| Gate | Blocking | Tool | Checks |
|------|----------|------|--------|
| `build` | yes | — (stdlib) | every Python file compiles (syntax) |
| `ruff` | no | ruff | lint |
| `format` | no | ruff format | formatting drift (`--check`) |
| `mypy` | no | mypy | static type errors |
| `bandit` | no | bandit | security lint |
| `vulture` | no | vulture | dead / unused code |

Cross-language SAST / deps / secrets / IaC:

| Gate | Blocking | Tool | Checks |
|------|----------|------|--------|
| `semgrep` | no | semgrep | SAST — python **+ go + js + ts** + owasp + secrets |
| `codeql` | no | codeql (bundle / own image) | semantic SAST (data-flow/taint) — python, js/ts, go |
| `gitleaks` | yes | gitleaks | secrets in the tree |
| `osv` | no | pip-audit | Python dependency vulns |
| `osv_scanner` | no | osv-scanner | dependency vulns, **all ecosystems** (go.mod, package-lock, …) |
| `trivy` | no | trivy | fs vulns + secrets + **misconfig + license** |
| `checkov` | no | checkov | IaC misconfig |
| `kics` | no | checkmarx/kics (own image) | IaC misconfig (Terraform/k8s/Docker/Ansible/…) |
| `hadolint` | no | hadolint | Dockerfile lint |
| `scorecard` | no | scorecard | OSSF security-posture score (0–10, local file-based checks) |

Shell / CI / config / prose:

| Gate | Blocking | Tool | Checks |
|------|----------|------|--------|
| `shellcheck` | no | shellcheck | shell script bugs (`*.sh`/`*.bash`) |
| `actionlint` | no | actionlint | GitHub Actions workflow lint |
| `yamllint` | no | yamllint | YAML lint |
| `codespell` | no | codespell | source/doc typos |
| `mdl` | no | mdl | Markdown lint (`*.md`) |
| `ci_act` | no | act + Docker | runs `.github/workflows/*` locally |

Database (self-skips without `*.sql`; dialect via `GANDALF_SQL_DIALECT`, default `ansi`):

| Gate | Blocking | Tool | Checks |
|------|----------|------|--------|
| `sqlfluff` | no | sqlfluff | SQL lint / style |
| `squawk` | no | squawk | Postgres migration safety (unsafe DDL, locks, …) |

Go (host toolchain; self-skips without `go.mod`):

| Gate | Blocking | Tool | Checks |
|------|----------|------|--------|
| `go_build` | yes | go | `go build ./...` compiles |
| `golangci_lint` | no | golangci-lint | meta-linter (govet, staticcheck, errcheck, unused, …) |
| `govulncheck` | no | govulncheck | Go vulns (reachability-aware) |
| `go_test` | no | go | `go test ./...` |

Node / TypeScript (host toolchain; self-skips without `package.json`):

| Gate | Blocking | Tool | Checks |
|------|----------|------|--------|
| `eslint` | no | npx eslint | JS/TS lint (project-local config) |
| `tsc` | no | npx tsc | TypeScript type check (needs `tsconfig.json`) |
| `node_test` | no | npm test | runs the `test` script |

Tests + compliance + dynamic:

| Gate | Blocking | Tool | Checks |
|------|----------|------|--------|
| `tests` | no | pytest | runs the Python test suite |
| `compliance` | no | LLM (headroom) | does the diff satisfy `--title`/`--body`? (≥85% = pass) |
| `atheris` | no | atheris | coverage-guided fuzzing (needs a harness) |
| `nikto` | no | nikto + `--target` | server misconfig sweep |
| `sqlmap` | no | sqlmap + `--target` | SQL-injection probe |
| `dalfox` | no | dalfox + `--target` | XSS probe |

The dynamic gates (`nikto`/`sqlmap`/`dalfox`) refuse non-localhost targets unless
you pass `--allow-remote`. `golangci-lint`/`govulncheck` aren't in the image
(they need the Go toolchain) — `go install` them on the host to activate.

### Skill-driven review gates (4)

These gates have no external tool. Each wraps one reviewing **skill** — a prose
playbook under the repo's top-level [`skills/`](../skills) directory — and runs
it as an LLM judge against the same headroom endpoint the `compliance` gate uses.
The skill's `SKILL.md` becomes the rubric; the model returns a strict JSON
verdict (`outcome` + `score` + `findings`) that maps onto the gate. The skills
are embedded in this repo, so the gates are self-contained and versioned with the
code. Like every LLM gate, each degrades to 🟡 WARN (never crashes the run) when
the endpoint is unreachable — so static-only runs aren't blocked by a missing
model.

| Gate | Blocking | Skill | Judges |
|------|----------|-------|--------|
| `quality_gate_review` | yes | [`quality-gate-review`](../skills/quality-gate-review) | six weighted quality gates → GO / REVIEW / NO-GO (pass / warn / fail) |
| `ruthless_refactor` | no | [`ruthless-refactor`](../skills/ruthless-refactor) | simplification wins: duplication, dead code, needless indirection, custom-vs-library |
| `pr_code_summary` | no | [`pr-code-summarizer`](../skills/pr-code-summarizer) | a technical-lead's 60-second read; warns when complexity/risk is high |
| `security_assessment` | no | [`security-assessment`](../skills/security-assessment) | CNCF TAG Security posture: SBOM, signing, branch protection, disclosure, incident response |

`quality_gate_review` is the only blocking skill gate — a NO-GO verdict reddens
the run — but a WARN from an unreachable model never does. The skills are read
from gandalf's own source tree (next to the package), not the worktree under
review, so `--commit`/`--staged` runs judge against the same rubric. To disable
these gates for a fast, LLM-free run, point `GANDALF_LLM_URL` at nothing (they
WARN and drop out of the verdict) — the tool-based gates are unaffected.

### Skill-backed advisory gates (3)

A second family of skill gates, built on the shared `SkillGate` base in
`gandalf/skillgate.py`. Each embeds a skill (under `skills/`) verbatim, wraps its
`SKILL.md` in a non-interactive scoring contract, and maps the model's 0–100
score to RAG. The skill file is the rubric and single source of truth — edit the
skill and the gate follows, exactly like a human running `/<skill>`.

Unlike the review gates above, these are **advisory: they emit only 🟢 PASS or 🟡
WARN, never 🔴 FAIL.** LLM judgement is subjective, so they surface friction
without hard-blocking a build — the deterministic tool gates own the red line.
WARN is also the honest degrade when headroom is unreachable, a skill isn't
embedded, or nothing is in scope: never a false pass. All three are generic (run
on every change).

| Gate | Category | Embedded skill(s) | Judges |
|------|----------|-------------------|--------|
| `grill_me` | Design readiness | [`grill-me`](../skills/grill-me) → `grilling` | The load-bearing decisions the change leaves unresolved or ambiguous (PASS ≥ 80). |
| `codebase_architecture` | Architecture | [`improve-codebase-architecture`](../skills/improve-codebase-architecture) → `codebase-design` | Deep-module health — shallow modules, poor locality, leaky seams, hard-to-test interfaces (PASS ≥ 75). |
| `well_architected` | Well-Architected | [`well-architected`](../skills/well-architected) | The change against all six Well-Architected pillars, HRIs/MRIs tagged by severity (PASS ≥ 75). |

`grill-me` and `improve-codebase-architecture` come from
[mattpocock/skills](https://github.com/mattpocock/skills); `well-architected` is
adapted from AWS's
[sample-well-architected-skills-and-steering](https://github.com/aws-samples/sample-well-architected-skills-and-steering).
Each is embedded together with the dependency skills it invokes (grilling,
codebase-design), so the gate carries the full rubric offline.
