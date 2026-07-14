# CLAUDE.md

Guidance for Claude Code (and other AI agents) working in this repo.

## Project

Gandalf is a codebase quality-gate evaluator: it runs pluggable "gates" over a
repo (working tree, staged changes, or a specific commit) and reports a
Red/Amber/Green traffic-light scorecard plus an LLM summary. Pure-stdlib
Python — no runtime dependencies. Package lives under `src/gandalf/`; the CLI
entry point is `src/gandalf/__main__.py` (`python -m gandalf`).

## Commands

```sh
# run:   PYTHONPATH=src python -m gandalf [--staged | --commit <sha> | --path <dir>]
# test:  pytest
# lint:  pre-commit run --all-files
```

## Conventions

- Match existing style; don't reformat unrelated code.
- Conventional Commits for messages (see CONTRIBUTING.md).
- Keep the code stdlib-only — no runtime dependencies.
- Gates live in `src/gandalf/gates/`; each `.py` exports a `Gate` subclass and
  is auto-discovered. Tests live in `tests/`.
- Update docs/ and examples/ with behavior changes.
- Never commit secrets; CI runs gitleaks. Keep `.env` out of git.

## Guardrails

- Don't add dependencies without a clear reason; prefer stdlib.
- Don't touch generated files (`reports/`, `__pycache__/`) by hand.
- Ask before large refactors or destructive operations.
