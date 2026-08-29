# CLI reference

## Flags

| Flag | Effect |
|------|--------|
| `--commit <sha>` | Evaluate that commit (checked out in a temp worktree, auto-removed). |
| `--staged` | Evaluate staged changes only. |
| `--path <dir>` | Limit scanning to git-tracked files under a folder. On its own it scans the whole folder; with `--staged`/`--commit` it narrows that change set to the folder. |
| `--no-llm` | Skip the LLM summary. |
| `--debug` | Verbose stderr log: per-gate timing and every external command run (also via `GANDALF_DEBUG=1`). Steps the progress bar aside. Gate durations are always recorded under `duration` in the JSON. |
| `--fix` | Let every gate whose tool can fix its own findings do so, in the working tree, before scoring — so the scorecard reflects the fixed state and what is left is what actually needs a human. Cascades to `ruff --fix`, `ruff format`, `eslint --fix`, `golangci-lint --fix`, `cargo clippy --fix`, `sqlfluff fix`, `codespell -w` and shellcheck's own diff. Fixers run sequentially (order matters — a lint fix then a reformat of the same file), and each one's report is the set of files it actually rewrote, measured from the worktree. Ignored for `--commit` (throwaway worktree); with `--staged` the fixes land in the working tree, so `git add` them again before committing. |
| `--no-html` | Skip the HTML report (JSON is always written). |
| `--out-dir <dir>` | Write reports to `<dir>` instead of `<repo>/reports` (created if missing). Lets an editor integration or CI job keep its artifacts out of the working tree. |
| `--no-trend` | Don't append this run to `.gandalf-trend.jsonl`. The score delta is still read from an existing log — useful when a tool re-runs gandalf often and shouldn't pollute the history. |
| `--json` | Also dump the JSON payload to stdout. |
| `--stream` | Emit one NDJSON line per gate to stdout as it finishes, before the scorecard: `{"event":"start","scope":…,"gates":N}` then one `{"event":"gate","index":i,"total":N,"name":…,"outcome":…,"findings":[…],"category":…,"duration":…}` per gate, in completion order. Lets a consumer show results during the run instead of waiting for the report. Cache hits are reported too. Findings are baseline-suppressed, but the score is pre-severity-weighting and there is no verdict — those are properties of the whole run, so the final report remains the record. |
| `--target <url>` | Live URL for the dynamic gates (nikto/sqlmap/dalfox). Without it they skip. |
| `--allow-remote` | Permit dynamic scans against a non-localhost `--target`. |
| `--title` / `--body` | Request title / acceptance criteria for the `compliance` gate. Without them it skips. |
| `--sarif [PATH]` | Also write a SARIF 2.1.0 report (default `reports/<stem>.sarif`) for GitHub code scanning / CI dashboards. |
| `--pr-comments [PATH]` | Write GitHub PR review comments (per-finding, anchored to `file:line`) as JSON, ready to POST to the "Create a review" API (default `reports/<stem>-pr-comments.json`). Anchors land on lines the diff adds; everything else rolls up into the summary body. A finding whose tool ships the replacement text carries it as a ` ```suggestion ` block, so the fix is one click on the PR — see [Suggested fixes](#suggested-fixes). |
| `--pr N` | Also post those comments to PR #N via the REST API (needs `GITHUB_TOKEN` and `--pr-repo` / `$GITHUB_REPOSITORY`). Idempotent: the summary is one sticky comment edited in place with a "Last updated" stamp, and inline comments are reconciled (unchanged kept, obsolete resolved, new posted) instead of re-posted — nothing is ever deleted. |
| `--baseline <path>` | Suppress findings listed in a baseline file (default `.gandalf-baseline.json` if present). |
| `--write-baseline [PATH]` | Snapshot current findings to a baseline file (default `.gandalf-baseline.json`). |
| `--config <path>` | Path to a `.gandalf.toml` (default: repo root). |
| `--exclude <glob>` | Skip paths matching the glob, for **every** gate. Repeatable. A bare name skips that directory anywhere (`node_modules`), a path anchors at the repository root (`src/generated`), and globs work (`*.min.js`). Adds to `.gandalfignore` and the built-in defaults rather than replacing them; `[gandalf] exclude = [...]` in `.gandalf.toml` does the same. |
| `--tool-versions` | Probe the version of every scanner that ran and record it in the report (one extra subprocess per tool). |
| `--cache [PATH]` | Reuse a gate's prior result when the scanned files are unchanged (default `.gandalf-cache.json`). Ignored with `--target`/`--title`/`--body`. |

## Suggested fixes

Several scanners already know the exact replacement text for what they flag.
When one does, `--pr-comments` / `--pr` attaches it to the inline comment as a
GitHub ` ```suggestion ` block — the reviewer commits it with **Commit
suggestion**, or batches it with the rest, without leaving the diff.

| Gate | Where the fix comes from |
|------|--------------------------|
| `ruff` | `fix.edits` — the same edits `ruff --fix` would apply |
| `eslint` | the message's `fix` range, translated from character offsets |
| `shellcheck` | `fix.replacements` (the safe ones it will suggest) |
| `semgrep` | a rule's `extra.fix` autofix |
| `codespell` | the correction in its `<found> ==> <correction>` message, applied to that line |

The rules are deliberately narrow, because a wrong one-click patch is worse
than none:

- The block replaces **whole lines**, and it has to start on the line the
  comment is anchored to — GitHub applies it to the range the comment covers.
- A replacement spanning several lines turns the comment into a multi-line one
  (`start_line`..`line`), and is dropped when any line in that range is not
  part of the diff, because GitHub would reject the comment outright.
- Findings merged into one comment are fixed **together**, so two hits on one
  line produce a single suggestion instead of two that invalidate each other.
- Nothing is suggested when the edits conflict, when they no longer line up
  with the file on disk, when the result would be identical to what is there,
  or when it runs past 40 lines.

A gate whose tool reports fixes in a format only that gate can read normalises
them into a `_fix` block on the finding (see `gandalf/suggest.py`); everything
else is read from the tool's own shape.
