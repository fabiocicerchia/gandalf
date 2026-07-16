# Gandalf — feature backlog

Missing capabilities for the quality-gate evaluator, split into **must-have**
(needed before gandalf is a dependable CI gate on real repos) and
**nice-to-have** (raises the bar once the core is solid). Grounded in the
current code.

---

## Must-have

- [x] **Gate selection.** `[gandalf.toml] only` / `skip` allowlist/denylist,
  applied before language filtering; config-disabled gates surface in the output
  and JSON. (CLI `--only`/`--skip` shorthands still open — config covers it.)

- [x] **Config file (`.gandalf.toml`).** `gandalf/config.py` loads a
  version-controlled config from the repo root (`--config` / `GANDALF_CONFIG`
  override); env vars still win. Sub-tables drive verdict, timeouts, severity,
  suppression.

- [x] **Scan git-tracked files in whole-tree mode.** `plugins.tracked_files()`
  (cached `git ls-files`); `_scan_targets` and `build` use it, so vendored/
  untracked trees no longer enter the scan or trip the timeout.

- [x] **Baseline / finding suppression.** `gandalf/suppress.py`: config
  `rules` (`gate:rule:pathglob`) + a generated `.gandalf-baseline.json`
  (`--write-baseline`), so a legacy repo only fails on new findings. Muting
  re-scores a gate and can only improve it.

- [x] **SARIF output.** `gandalf/sarif.py` + `--sarif` emits SARIF 2.1.0 for
  GitHub code scanning / CI dashboards.

- [x] **Configurable verdict policy.** `report.Policy` + `--fail-on` /
  `--min-score` (and `[gandalf.verdict]`). RAG display unchanged; policy drives
  pass/fail + exit code.

- [x] **Bounded gate concurrency.** Semaphore in `_run_gates`, resolved from
  `--concurrency` → `GANDALF_CONCURRENCY` → config → CPU count.

- [x] **Tests for the report/scope/llm layers.** New `test_config`,
  `test_suppress`, `test_sarif`, `test_report` (policy + render smoke),
  `test_run`, `test_pr_comments`, `test_severity`, `test_debug`, `test_llm`.

---

## Nice-to-have

- [x] **Auto-fix / `--fix` mode.** Optional gate `fix(ctx)` protocol; `ruff`,
  `format`, `eslint` ship fixers that run before scoring.

- [x] **PR integration (line comments).** `gandalf/pr_comments.py` +
  `--pr-comments` / `--pr` post per-finding review comments anchored to
  `file:line`. (A README score **badge** is still open.)

- [x] **Per-gate timeout override.** `[gandalf.timeouts]` (gate-name key >
  `default` > global), threaded via a `GATE_TIMEOUT` contextvar.

- [x] **Finding severity weighting.** `gandalf/severity.py` +
  `[gandalf.severity] weight` / `--severity-weight` — a critical outweighs
  several lows; count-scored gates untouched.

- [x] **Verbose / `--debug` + per-gate timing.** `gandalf/debug.py`; durations
  also always recorded under `duration` in the JSON.

- [x] **Network resilience.** `llm._request_with_retry` — exponential backoff on
  transient LLM failures (429/5xx/network), not 4xx.

- [ ] **More language suites.** Rust done (`gandalf/gates/rust.py`:
  `cargo build`/`clippy`/`cargo-audit`/`cargo test`, tagged `langs={"rust"}`).
  Java/Kotlin, Ruby, PHP, C/C++, .NET still open — same pattern, one gate file
  per language, see `rust.py`/`golang.py` as the template.

- [x] **Result caching between runs.** `gandalf/cache.py` + `--cache [PATH]`
  (default `.gandalf-cache.json`) — keys every gate's result by a content hash
  of the scanned file set; an unchanged set reuses the prior outcome. Skipped
  automatically for `--target`/`--title`/`--body` runs, since those affect
  gates without changing any file.

- [x] **Trend history.** `gandalf/trend.py` appends `{commit, score,
  generated_at}` to `.gandalf-trend.jsonl` after every run; the terminal and
  HTML report headers show `(+N vs prev)` / `(-N vs prev)` against the most
  recent differing commit.

- [x] **Pre-commit hook shim.** A ready `.pre-commit-hooks.yaml` entry so
  gandalf runs `--staged` on commit.

- [x] **JUnit XML output.** For CI systems that render test-style reports
  (Jenkins, GitLab) rather than SARIF.

- [ ] **README score badge.** Generate a shields-style badge from the JSON.

- [x] **HTML report filtering.** Filter/collapse rows by RAG state and a diff
  view for the changeset, on top of the existing sort/expand.
