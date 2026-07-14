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

Select gates per repo in `.gandalf.toml`: `only = [...]` (allowlist),
`skip = [...]` (denylist). Env vars override the file.

---

## Security — SAST, secrets, DAST, fuzz

| Gate | Checks | Notes |
|------|--------|-------|
| `semgrep` | Pattern-based SAST across languages. | FAIL on any ERROR-severity rule or >5 findings, else WARN. |
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
| `sqlfluff` | SQL lint. | Self-skips without `.sql`; dialect via `GANDALF_SQL_DIALECT`. |
| `squawk` | Unsafe Postgres DDL (blocking locks, dropped columns, non-concurrent indexes). | Self-skips without `.sql`. |

## Code quality — lint, format, types, dead code

| Gate | Checks | Notes |
|------|--------|-------|
| `ruff` | Python lint. | |
| `format` | `ruff format --check` — formatting drift (does not rewrite). | |
| `mypy` | Python type checking. | |
| `vulture` | Python dead-code detection. | |
| `golangci_lint` | Go meta-linter (govet, staticcheck, errcheck, unused, …). | Go toolchain. |
| `eslint` | JS/TS lint. | Uses the repo's local config/deps. |
| `tsc` | TypeScript type check. | |
| `shellcheck` | Shell-script lint. | |
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
| `codespell` | Common misspellings in code/docs. | |

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
