# Architecture

Gandalf evaluates a repository through pluggable **gates** and rolls their
results into a Red/Amber/Green scorecard.

## Overview

`python -m gandalf` (`src/gandalf/__main__.py`) resolves what to scan (working
tree, staged, a `--commit` worktree, or a `--path` subfolder), discovers gates,
runs them under bounded concurrency, then aggregates and renders the report.

## Components

- **`__main__.py`** — the run: scope resolution, concurrency, orchestration.
- **`cli.py`** — the flag table, readable without running anything.
- **`fixers.py` / `stream.py`** — `--fix` (and what it actually rewrote) and
  the `--stream` NDJSON feed.
- **`outputs.py` / `summary.py`** — the JSON/HTML/SARIF/JUnit/badge artifacts,
  and the terminal footer.
- **`plugins.py`** — auto-discovers `Gate` subclasses in `gates/`, and is the
  import surface a gate is written against: it re-exports `toolrun.py`
  (resolve a tool on PATH or in the gandalf-tools image, run it under a
  per-gate timeout budget, kill the container behind it), `ignores.py` (which
  files a gate may look at) and `outcomes.py` (the results for a gate that
  produced no signal).
- **`gates/`** — one file per gate (bandit, ruff, semgrep, codeql, licenses, …),
  over the shared readers in `gates/_toolchain.py`.
- **`base.py`** — `Gate`, `GateContext`, `GateResult`, `GateOutcome`.
- **`report.py`** — the RAG vocabulary, the composite score and the policy.
- **`render_text.py` / `render_html.py` / `html_assets.py` / `sarif.py`** —
  the drawing, kept apart from the scoring.
- **`pr_comments.py` / `suggest.py`** — GitHub review comments anchored at
  `file:line`, carrying the tool's own fix as an applicable suggestion.
- **`llm.py` / `skills.py` / `skillgate.py`** — LLM summary and skill-driven
  review gates (playbooks under a top-level `skills/`).
- **`findings.py` / `locate.py` / `fingerprint.py`** — one owner for reading a
  heterogeneous gate finding: the key lists, the `path:line:col` scraped out of
  a message, and the deliberately frozen vocabulary suppression hashes with.
- **`config.py` / `scope.py` / `suppress.py` / `severity.py`** — `.gandalf.toml`
  config, file classification, baseline/suppression, severity mapping.

## Data flow

```
scope → discover_gates → run (bounded concurrency) → aggregate → render (RAG / SARIF / HTML)
```

## Decisions

- Pure stdlib, no runtime dependencies — the "install" is a PYTHONPATH wrapper.
- `src/` layout keeps the importable package separate from repo scaffolding.
- Gates are auto-discovered files, so adding a check is dropping one `.py` in
  `gates/`.

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

Overall verdict: 🔴 if any gate fails · 🟡 if any warns · 🟢 if all pass —
counting only the gates that actually ran. A gate that could not run (tool not
installed, timed out, judge unreachable, nothing in scope) is marked ⚪ and
excluded from both the verdict and the composite score; `plugins.unavailable()`
builds those results and `plugins.did_not_run()` reads the marker. `GateOutcome`
deliberately keeps its three members, so the cache, SARIF, JUnit and the badge
are unaffected and gate files stay portable to ai-harness.

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
