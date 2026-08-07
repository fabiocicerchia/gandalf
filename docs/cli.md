# CLI reference

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
| `--pr-comments [PATH]` | Write GitHub PR review comments (per-finding, anchored to `file:line`) as JSON, ready to POST to the "Create a review" API (default `reports/<stem>-pr-comments.json`). Anchors land on lines the diff adds; everything else rolls up into the summary body. |
| `--pr N` | Also post those comments to PR #N via the REST API (needs `GITHUB_TOKEN` and `--pr-repo` / `$GITHUB_REPOSITORY`). Idempotent: the summary is one sticky comment edited in place with a "Last updated" stamp, and inline comments are reconciled (unchanged kept, fixed deleted, new posted) instead of re-posted. |
| `--baseline <path>` | Suppress findings listed in a baseline file (default `.gandalf-baseline.json` if present). |
| `--write-baseline [PATH]` | Snapshot current findings to a baseline file (default `.gandalf-baseline.json`). |
| `--config <path>` | Path to a `.gandalf.toml` (default: repo root). |
| `--cache [PATH]` | Reuse a gate's prior result when the scanned files are unchanged (default `.gandalf-cache.json`). Ignored with `--target`/`--title`/`--body`. |
