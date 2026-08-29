# Configuration

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
| `GANDALF_GATES_PATH` | — | extra `:`-separated dirs to load gates from — **a trust boundary, see below** |
| `GANDALF_PROGRESS` | auto | set `1` to force the stderr progress bar when stderr isn't a TTY |
| `GANDALF_TOOLS_IMAGE` | `gandalf-tools` | Docker image scanners run in when off the host PATH |
| `GANDALF_KICS_IMAGE` | `checkmarx/kics:latest` | image the `kics` gate runs from (it ships its own query assets) |
| `GANDALF_CODEQL_IMAGE` | `mcr.microsoft.com/cstsectools/codeql-container:latest` | image the `codeql` gate runs from when no host `codeql` binary |
| `GANDALF_CODEQL_TIMEOUT` | `600` | per-step timeout (s) for codeql DB build + analyze (slower than other gates) |
| `GANDALF_ACT` | `1` | set `0` to disable the `ci_act` gate |
| `GANDALF_ACT_EVENT` / `GANDALF_ACT_PLATFORM` / `GANDALF_ACT_TIMEOUT` | `pull_request` / `ubuntu-latest=…` / `900` | `act` runner config |

If headroom is unreachable the summary shows a one-line note and gates still run.

## Trust boundary: `GANDALF_GATES_PATH`

`GANDALF_GATES_PATH` names directories that gandalf imports Python from. Every
`.py` in them is executed at import time — module-level code runs *before*
anything checks whether the file defines a gate — so setting this variable is
equivalent to arbitrary code execution as whatever user gandalf runs as. In CI
that is the job's user, with the job's secrets and the job's token.

A gate loaded this way can also **replace a built-in**: discovery is keyed by
gate name, and the last one wins, so a plugin named `gitleaks` silently becomes
the `gitleaks` gate and can report a clean pass in the scorecard, the JSON, the
SARIF upload and the PR comment. gandalf prints a line to stderr when this
happens, but the run continues — overriding a scanner is a legitimate thing to
want, and gandalf cannot tell a deliberate swap from a malicious one.

So:

- Treat it exactly as you would `PYTHONPATH` or a `curl | sh`.
- **Never** let it be set from untrusted input. In particular, do not derive it
  from a pull-request branch, a fork's workflow file, or anything a contributor
  can edit — a PR that adds one file could disable the secret scanner that is
  meant to be reviewing it.
- Point it at directories inside the repository you are already trusting with
  code review, or at a path baked into the runner image.
- If you do not use plugin gates, leave it unset. There is no default.

Gate files under `src/gandalf/gates/` carry the same weight, but they arrive
through the same review as the rest of the codebase.

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
exclude     = ["src/generated", "*.min.js"]  # paths no gate should read
```

`concurrency` bounds how many gates run simultaneously — important because
~60 gates may each spawn a `docker run`, which can swamp a laptop or CI runner
if they all launch at once. Precedence: `--concurrency N` → `GANDALF_CONCURRENCY`
→ config → CPU count.

### Excluding paths

`exclude` adds to the repo's `.gandalfignore` and the built-in defaults
(`reports`, `node_modules`, `llama.cpp`, `.venv`, `.git`); `--exclude <glob>`
adds to it again, repeatably, without touching a file. All three feed one list,
matched the same way:

| Pattern | Matches |
|---|---|
| `node_modules` | that directory wherever it appears, and everything under it |
| `src/generated` | that path from the repository root, and everything under it |
| `*.min.js` | any path or filename the glob matches |
| `.env` | that filename in any directory |

The list narrows what **every** gate reads, not only the tree-scanning ones that
translate it into their own tool's exclude flag. It sits on top of git: gates
only ever see git-tracked files, so anything `.gitignore` hides — build output,
a docs site, a virtualenv — is already out of scope and needs no entry here. It also decides what the
`--cache` hash covers, so editing an excluded file doesn't invalidate results
no gate would have re-derived.

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
