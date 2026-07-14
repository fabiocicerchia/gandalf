# Architecture

Gandalf evaluates a repository through pluggable **gates** and rolls their
results into a Red/Amber/Green scorecard.

## Overview

`python -m gandalf` (`src/gandalf/__main__.py`) resolves what to scan (working
tree, staged, a `--commit` worktree, or a `--path` subfolder), discovers gates,
runs them under bounded concurrency, then aggregates and renders the report.

## Components

- **`__main__.py`** — CLI, scope resolution, concurrency, orchestration.
- **`plugins.py`** — auto-discovers `Gate` subclasses in `gates/` and provides
  shared subprocess helpers (per-gate timeout budgets).
- **`gates/`** — one file per gate (bandit, ruff, semgrep, codeql, licenses, …).
- **`base.py`** — `Gate`, `GateContext`, `GateResult`, `GateOutcome`.
- **`report.py` / `sarif.py`** — RAG aggregation, terminal/HTML/SARIF output.
- **`llm.py` / `skills.py` / `skillgate.py`** — LLM summary and skill-driven
  review gates (playbooks under a top-level `skills/`).
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
