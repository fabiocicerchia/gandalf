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
make help    # Show this help
make setup   # Install the pre-commit hook
make lint    # Run all pre-commit checks on the whole tree
make test    # Run the test suite
make analyze # Run gandalf against this repo
make install # Drop a `gandalf` wrapper in BINDIR (default ~/.local/bin)
make tools   # Build the scanner-tools image (zero host installs)
```

## Tooling

- `make setup` installs the pre-commit hook, and that is the whole of it.
  Don't add a `.githooks/` directory: `core.hooksPath` replaces `.git/hooks/`
  wholesale, so setting it silently stops every pre-commit hook from running.
- Hooks are pinned by commit SHA with the tag in a trailing comment. A tag can
  be moved, a SHA cannot.
- CI runs this same `.pre-commit-config.yaml` through `pre-commit/action`, so
  what passes locally is what gates the pull request.

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
