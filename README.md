# 🧙 Gandalf — codebase quality-gate evaluator

> **"You shall not pass!"**

[![code-quality](https://github.com/fabiocicerchia/gandalf/actions/workflows/code-quality.yml/badge.svg)](https://github.com/fabiocicerchia/gandalf/actions/workflows/code-quality.yml)
[![security](https://github.com/fabiocicerchia/gandalf/actions/workflows/security.yml/badge.svg)](https://github.com/fabiocicerchia/gandalf/actions/workflows/security.yml)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![OpenSSF Scorecard](https://api.securityscorecards.dev/projects/github.com/fabiocicerchia/gandalf/badge)](https://securityscorecards.dev/viewer/?uri=github.com/fabiocicerchia/gandalf)
[![FOSSA Status](https://app.fossa.com/api/projects/git%2Bgithub.com%2Ffabiocicerchia%2Fgandalf.svg?type=shield)](https://app.fossa.com/projects/git%2Bgithub.com%2Ffabiocicerchia%2Fgandalf?ref=badge_shield)
[![Release](https://img.shields.io/github/v/release/fabiocicerchia/gandalf)](https://github.com/fabiocicerchia/gandalf/releases)

Evaluate the codebase as-is, get an LLM summary and a Red/Amber/Green
traffic-light scorecard from pluggable gates. Stdlib-only, no dependencies.

```bash
PYTHONPATH=src python -m gandalf                 # whole working tree, as-is (default)
PYTHONPATH=src python -m gandalf --staged        # staged changes only
PYTHONPATH=src python -m gandalf --commit <sha>  # a specific commit (in a throwaway git worktree)
PYTHONPATH=src python -m gandalf --path <dir>    # limit scanning to a folder
```

The package lives under `src/`, so put `src` on `PYTHONPATH` (the wrapper below does this for you).

Or `make analyze`. Exit code is `1` when the verdict is red, `0` otherwise — CI-usable.

## Install a `gandalf` command

```bash
make install                       # drops a wrapper in ~/.local/bin (on your PATH)
make install BINDIR=/usr/local/bin # …or anywhere else
```

Or the one-line installer (clones/updates a checkout under
`~/.local/share/gandalf` and runs `make install`):

```bash
curl -fsSL https://raw.githubusercontent.com/fabiocicerchia/gandalf/main/install.sh | bash
```

Pure-stdlib, so the "install" is just a one-line wrapper that runs this checkout
(`python -m gandalf`) against whatever repo you're in. Equivalent one-liner:

```bash
printf '#!/bin/sh\nexport PYTHONPATH="%s/src:$PYTHONPATH"\nexec python3 -m gandalf "$@"\n' "$PWD" > ~/.local/bin/gandalf && chmod +x ~/.local/bin/gandalf
```

### `.gandalfignore` — skip paths in tree-scanning gates

The container/dependency gates (`trivy`, `checkov`, `kics`) scan the whole tree.
Add a `.gandalfignore` at the repo root (gitignore-style: one glob per line, `#`
comments) to skip local secrets/state that aren't committed — e.g. a `.env` or a
`data/` dir — so they aren't reported as false-positive leaks. Built-in defaults
(`reports`, `node_modules`, `llama.cpp`, `.venv`, `.git`) always apply.

## Scanners run in Docker — host stays clean

gandalf itself is pure-stdlib Python (nothing to install). The scanner tools live
in one image so they never touch the host:

```bash
make tools   # builds the gandalf-tools image (docker build -f gandalf/tools.Dockerfile)
```

Once built, any gate whose binary isn't on the host `PATH` runs its command
atomically as `docker run --rm -v <worktree>:/src gandalf-tools <tool> …`. A named
`gandalf-cache` volume keeps tool DBs (trivy, semgrep rules) warm across runs and
off the host. Resolution per tool, in order:

1. host binary on `PATH` → run it directly (no Docker);
1. else `gandalf-tools` image present → run the tool in a throwaway container;
1. else → the gate degrades to 🟡 WARN.

So you can `make tools` for zero host installs, *or* install any subset of tools
on the host and skip the image — both work, mixed freely. Override the image
name with `GANDALF_TOOLS_IMAGE`.

The image covers the language-agnostic tools: `ruff`, `semgrep`, `bandit`,
`pip-audit` (osv), `osv-scanner`, `trivy`, `gitleaks`, `checkov`, `hadolint`,
`scorecard`, `mypy`, `vulture`, `codespell`, `yamllint`, `shellcheck`,
`actionlint`. The Go
and Node gates use the host toolchain (`go`/`npx`/`npm`), and `ci_act` (host
Docker daemon), `tests` (project env), the `dynamic` DAST tools, and `atheris`
also run on the host.

## What it does

1. **LLM analysis** — one call to the headroom endpoint returns three
   markdown sections: a generic **summary**, **remediation** (specific fixes to
   raise the score — grounded in the actual findings, citing file:line / package
   / rule id), and **improvement** (ways to raise the bar beyond passing).
1. **Gates → RAG** — runs every discovered gate concurrently, maps each result
   to 🟢 PASS / 🟡 WARN / 🔴 FAIL, plus an overall verdict and a 0–100 score.
1. **Outputs** — colored terminal scorecard, a self-contained HTML report, and a
   CI-parsable JSON file (both written to `reports/`). The HTML report is 3/4
   page width, has a light/dark theme toggle, RAG-tinted rows, a markdown-rendered
   summary + remediation + improvement, click-to-sort Gate / RAG columns,
   expandable per-gate findings, and a header showing the commit ref and the
   UTC generation time.

Overall verdict: 🔴 if any gate fails · 🟡 if any warns · 🟢 if all pass.

## Flags

| Flag | Effect |
|------|--------|
| `--commit <sha>` | Evaluate that commit (checked out in a temp worktree, auto-removed). |
| `--staged` | Evaluate staged changes only. |
| `--path <dir>` | Limit scanning to git-tracked files under a folder. On its own it scans the whole folder; with `--staged`/`--commit` it narrows that change set to the folder. |
| `--no-llm` | Skip the LLM summary. |
| `--debug` | Verbose stderr log: per-gate timing and every external command run (also via `GANDALF_DEBUG=1`). Steps the progress bar aside. Gate durations are always recorded under `duration` in the JSON. |
| `--fix` | Apply gate autofixes (`ruff --fix`, `ruff format`, `eslint --fix`) to the working tree before scoring, so the scorecard reflects the fixed state. Ignored for `--commit` (throwaway worktree). |
| `--no-html` | Skip the HTML report (JSON is always written). |
| `--json` | Also dump the JSON payload to stdout. |
| `--target <url>` | Live URL for the dynamic gates (nikto/sqlmap/dalfox). Without it they skip. |
| `--allow-remote` | Permit dynamic scans against a non-localhost `--target`. |
| `--title` / `--body` | Request title / acceptance criteria for the `compliance` gate. Without them it skips. |
| `--sarif [PATH]` | Also write a SARIF 2.1.0 report (default `reports/<stem>.sarif`) for GitHub code scanning / CI dashboards. |
| `--pr-comments [PATH]` | Write GitHub PR review comments (per-finding, anchored to `file:line`) as JSON, ready to POST to the "Create a review" API (default `reports/<stem>-pr-comments.json`). |
| `--pr N` | Also post those comments to PR #N via the REST API (needs `GITHUB_TOKEN` and `--pr-repo` / `$GITHUB_REPOSITORY`). |
| `--baseline <path>` | Suppress findings listed in a baseline file (default `.gandalf-baseline.json` if present). |
| `--write-baseline [PATH]` | Snapshot current findings to a baseline file (default `.gandalf-baseline.json`). |
| `--config <path>` | Path to a `.gandalf.toml` (default: repo root). |

## Configuration (env vars)

| Var | Default | Purpose |
|-----|---------|---------|
| `GANDALF_LLM_URL` | `http://127.0.0.1:8787/v1` | headroom OpenAI-compatible base URL |
| `GANDALF_MODEL` | `gpt-oss-120b` | model id for summary + remediation + the LLM-judge gates (compliance + the skill-backed gates) |
| `GANDALF_MAX_TOKENS` | `8000` | max completion tokens (reasoning models need headroom or the last section truncates) |
| `GANDALF_API_KEY` | `sk-no-key-required` | bearer token |
| `GANDALF_LLM_RETRIES` | `2` | transient-failure retries for the LLM call (attempts = retries + 1); retries network errors, timeouts, and 429/5xx with exponential backoff — not 4xx |
| `GANDALF_LLM_BACKOFF` | `1.0` | base backoff seconds (delay = base × 2^attempt) |
| `GANDALF_GATE_TIMEOUT` | `120` | per-gate subprocess timeout (seconds) |
| `GANDALF_GATES_PATH` | — | extra `:`-separated dirs to load gates from |
| `GANDALF_PROGRESS` | auto | set `1` to force the stderr progress bar when stderr isn't a TTY |
| `GANDALF_TOOLS_IMAGE` | `gandalf-tools` | Docker image scanners run in when off the host PATH |
| `GANDALF_KICS_IMAGE` | `checkmarx/kics:latest` | image the `kics` gate runs from (it ships its own query assets) |
| `GANDALF_CODEQL_IMAGE` | `mcr.microsoft.com/cstsectools/codeql-container:latest` | image the `codeql` gate runs from when no host `codeql` binary |
| `GANDALF_CODEQL_TIMEOUT` | `600` | per-step timeout (s) for codeql DB build + analyze (slower than other gates) |
| `GANDALF_ACT` | `1` | set `0` to disable the `ci_act` gate |
| `GANDALF_ACT_EVENT` / `GANDALF_ACT_PLATFORM` / `GANDALF_ACT_TIMEOUT` | `pull_request` / `ubuntu-latest=…` / `900` | `act` runner config |

If headroom is unreachable the summary shows a one-line note and gates still run.

## Configuration (`.gandalf.toml`)

Per-repo settings live in a version-controlled `.gandalf.toml` at the repo root
(override the path with `--config` or `GANDALF_CONFIG`). It reviews with the code
instead of living in scattered env vars. Env vars still win over the file, which
wins over built-in defaults. All keys are optional.

```toml
[gandalf]
only        = ["ruff", "gitleaks"]   # allowlist: run ONLY these gates
skip        = ["atheris"]            # denylist: never run these
concurrency = 8                       # max gates running at once (<=0 = unbounded)
```

`concurrency` bounds how many gates run simultaneously — important because
~35 gates may each spawn a `docker run`, which can swamp a laptop or CI runner
if they all launch at once. Precedence: `--concurrency N` → `GANDALF_CONCURRENCY`
→ config → CPU count.

### Per-gate timeouts

The global per-gate subprocess timeout is `GANDALF_GATE_TIMEOUT` (default 120s).
Override it per gate — heavy scanners (semgrep, trivy, kics) often need more,
light ones less:

```toml
[gandalf.timeouts]
default = 120    # overrides the global default for all gates
semgrep = 300    # per-gate override, keyed by gate name
trivy   = 300
```

A gate-name key wins over `default`, which wins over `GANDALF_GATE_TIMEOUT`. A
gate that exceeds its budget degrades to 🟡 WARN, as before.

### Severity-weighted scoring

Most gates score by finding *count* — one critical vuln weighs the same as one
style nit. Enable severity weighting so a gate's score reflects how bad its
findings are:

```toml
[gandalf.severity]
weight = true
```

or `--severity-weight`. Only findings that report a severity (security /
dependency / IaC gates — bandit, trivy, semgrep, licenses, osv…) are weighted;
count-scored gates (ruff, mypy…) are untouched, and a gate's RAG outcome never
changes — only the 0–100 score feeding the composite. A single CRITICAL sinks
the score more than a handful of LOWs.

`only` is an allowlist (empty = allow all), `skip` always removes; both are
applied before language filtering. Gates removed by config are listed as
"disabled by config" in the terminal output and under `disabled_gates` in the
JSON. Further tables (`[gandalf.verdict]`, `[gandalf.timeouts]`,
`[gandalf.severity]`, `[gandalf.suppress]`) are documented in their sections
below.

## Verdict policy (when the run fails)

By default only a **red** verdict fails the run (exit 1); amber passes. Tune that
per repo or per invocation:

```toml
[gandalf.verdict]
fail_on   = "warn"   # "fail" (default) | "warn" — treat warnings as failures too
min_score = 85       # also fail if the composite score drops below this (0-100)
```

CLI `--fail-on {fail,warn}` and `--min-score N` override the file. The displayed
RAG traffic light is unchanged (it always reflects the gates); the policy only
changes the pass/fail decision, the exit code, and `passed` / `policy` in the
JSON. When the RAG isn't red but the policy still fails the run, the terminal
prints an explicit `Policy: run FAILED — <reason>` line.

## Suppressing known findings (baseline)

To stop a *known* finding from failing the gate — without disabling the whole
gate (that's `skip`) — mute it. Two mechanisms:

**Rules** (`[gandalf.suppress]`) — `gate:rule:pathglob`, any field empty to
wildcard:

```toml
[gandalf.suppress]
rules = [
  "ruff:E501",           # mute that code everywhere
  "gitleaks::tests/*",   # mute gitleaks under tests/
  "vulture",             # mute the whole gate (still runs, just no findings)
]
```

**Baseline** — snapshot the findings present today so only *new* ones can fail
(the classic way to adopt gandalf on a legacy repo):

```bash
python -m gandalf --write-baseline     # writes .gandalf-baseline.json
python -m gandalf                      # auto-loads it; baselined findings are muted
```

`--baseline <path>` points at a specific file; `[gandalf.suppress] baseline`
sets a default. Fingerprints are line-insensitive (gate + path + rule + message),
so a baselined finding survives edits above it. Muting can only make a gate
better: if every finding is muted the gate passes; a partial mute keeps the
outcome but raises the score and hides the muted findings.

## JSON report shape

```json
{
  "scope": "staged",
  "generated_at": "2026-07-03 13:10:42 UTC",
  "commit": {"sha": "…", "short": "ccfc3ec", "subject": "fix: …", "date": "2026-07-02T23:17:13+02:00"},
  "languages": ["python", "shell"],
  "verdict": "fail",
  "passed": false,
  "score": 60,
  "summary": "…",
  "remediation": "…markdown…",
  "improvement": "…markdown…",
  "skipped_gates": ["eslint", "go_build"],
  "gates": [
    {"name": "build", "outcome": "fail", "score": 0.0,
     "summary": "1 file(s) fail to compile — …", "findings": [...], "blocking": true}
  ]
}
```

`commit` is the evaluated commit for `--commit`, else the latest commit (HEAD)
even for `--staged` / working-tree scopes.

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
place and returns `(changed, message)`. Fixers run sequentially before scoring;
`ruff`, `format`, and `eslint` ship one.

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

## Contract compatibility with ai-harness

`gandalf/base.py` is intentionally the same shape as `ai-harness/app/gates/base.py`
(only `GateOutcome` is inlined instead of imported), so gate files move between
the two projects unchanged. All 17 ai-harness gates are ported into
`gandalf/gates/` (couplings replaced: `app.config.settings` → env vars / module
constants; the `compliance` judge's ai-harness router → `gandalf.llm`), and 14
more were added on top — the Python quality gates (mypy/vulture/format), the
polyglot linters (shellcheck/actionlint/yamllint/codespell), and full Go and
Node/TS suites — for 31 total.

## Tests

```bash
pytest                           # the whole suite (tests/ + src/ wired via pyproject.toml)
```

Each test module also runs standalone without pytest (handy in a bare
environment):

```bash
for m in tests/test_gandalf.py tests/test_config.py tests/test_suppress.py \
         tests/test_sarif.py tests/test_report.py tests/test_run.py; do
  PYTHONPATH=src python "$m"
done
```

Coverage: RAG aggregation + plugin discovery + language filtering
(`test_gandalf`), config loading & gate selection (`test_config`), suppression &
baseline (`test_suppress`), SARIF rendering (`test_sarif`), verdict policy +
terminal/HTML rendering (`test_report`), and the gate runner's bounded
concurrency + error isolation (`test_run`).

## Project layout

```
src/gandalf/     the package (CLI + gates/)
tests/           pytest suite
docs/            mkdocs documentation
examples/        runnable examples
.github/         CI workflows, issue/PR templates, dependabot
```

## Documentation

Full docs live in [`docs/`](docs/) (mkdocs). Runnable examples live in
[`examples/`](examples/).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). By participating you agree to the
[Code of Conduct](CODE_OF_CONDUCT.md).

## Security

Found a vulnerability? See [SECURITY.md](SECURITY.md) — please don't open a
public issue.

## License

[Apache-2.0](LICENSE) © Fabio Cicerchia
