# Gandalf for VS Code

Run [Gandalf](https://github.com/fabiocicerchia/gandalf)'s quality gates while
you write the code, instead of finding out in CI.

- **Inline diagnostics** — every finding that has a file and a line becomes a
  squiggle. The hover explains the problem, which gate found it, its severity
  and the rule id (linked to the tool's docs when there is one).
- **A findings pane** at the bottom — a normal VS Code tree view, so it behaves
  like the Problems panel next to it: findings grouped by file, severity icons,
  type-ahead filtering, keyboard navigation, an error badge on the view. Toggle
  between the current file and the whole project from the title bar; click a
  finding to jump to it.
- **The report**, rendered exactly as `reports/*.html` renders it — the same
  verdict banner, category scores, sortable gate table and LLM sections you get
  from the CLI, because it *is* that file, opened in an editor tab.
- **Every gate**, including the containerized ones. The environment check tells
  you which tools are present, which come from the scanner-tools image, and
  which are missing — so a green board never quietly means "never checked".

## Requirements

Gandalf itself. It is pure-stdlib Python with no install step, so the extension
finds it in whichever way you already have it, in this order:

1. `gandalf.executable` — an explicit path to the wrapper `make install` writes.
2. `gandalf.checkoutPath` — a source checkout (the directory holding `src/gandalf`).
3. The workspace itself, if you have gandalf's repository open.
4. `gandalf` on your `PATH`.
5. `~/.local/share/gandalf` — where the one-line `install.sh` puts its clone.

Nothing found? `Gandalf: Check Environment` says so, with the fix.

### Getting all the gates, not just some

Most gates shell out to a real scanner. Gandalf looks for each tool on `PATH`
first, then in the `gandalf-tools` Docker image — so with Docker installed and
the image built, you get the full gate set with zero host installs:

```sh
make tools     # in a gandalf checkout — or run “Gandalf: Build Scanner Tools Image”
```

Language toolchains (`go`, `cargo`, `npm`, `npx`, `golangci-lint`, `govulncheck`)
are never containerized — gandalf uses the ones you already develop with. The
`kics` and `codeql` gates pull their own images, and the dynamic scanners
(`nikto`, `sqlmap`, `dalfox`) only run with an explicit `--target`, so they stay
idle in an editor.

Run **`Gandalf: Check Environment`** to see exactly where each tool is coming
from. Gates that could not run are reported in the view's message line rather
than listed as findings — they are not results, and they should not look like
any.

## Commands

| Command | What it does |
|---|---|
| `Gandalf: Scan Workspace` | Full run over the working tree. |
| `Gandalf: Scan Current File` | Re-runs the gates scoped to the active file (`--path`). |
| `Gandalf: Scan Staged Changes` | `--staged` — what a commit would be judged on. |
| `Gandalf: Open Report` | The HTML scorecard, in an editor tab. |
| `Gandalf: Open Report (regenerate with LLM summary)` | Same, re-run with the LLM sections. |
| `Gandalf: Apply Gate Autofixes` | `--fix` (ruff `--fix`, ruff format, eslint `--fix`). Asks first — it rewrites files. |
| `Gandalf: Write Baseline` | `--write-baseline`: accept today's findings so only new ones fail. Asks first. |
| `Gandalf: Check Environment (Doctor)` | Tool-by-tool inventory of what can actually run. |
| `Gandalf: Build Scanner Tools Image` | `docker build -f tools.Dockerfile -t gandalf-tools .` in a terminal. |
| `Gandalf: Cancel Running Scan` | Kills the current run. |
| `Gandalf: Clear Results` | Drops all diagnostics and findings. |
| `Gandalf: Filter by Severity` | Native quick pick — which severities the pane shows. |

## Keeping it cheap

A gandalf run forks ~30 gates, several of which are `docker run`. Doing that on
every keystroke would be unusable, so **the extension never scans while you
type**. What it does instead, in layers:

**1. Scope, first and foremost.** A save triggers a scan of *that file*
(`--path <file>`), not the tree. That is the difference between a couple of
seconds and a couple of minutes. The whole project is scanned on demand, at
startup, and — if you ask for it — on a long interval. Per-file results are
merged over the last project run, so the pane always shows the project picture
with the file you just touched refreshed.

**2. Don't run what you just ran.** Saving an unmodified buffer fires
`didSave`; the extension hashes the file and skips the scan when the bytes are
identical to the last scan of it.

**3. Debounce and coalesce.** A burst of saves collapses into one run
(`gandalf.scan.debounceMs`, default 1.5s). Set `gandalf.scan.idleMs` to also
require the editor to be quiet for a while first.

**4. One process, ever.** Runs are strictly serialized — there is never a
second gandalf competing for the same CPU and the same Docker daemon. While one
runs, only the newest queued request survives, so a save storm cannot build a
backlog. Invoking a command preempts an automatic run rather than queueing
behind it.

**5. Gandalf's own gate cache.** Workspace and staged scans pass `--cache`, so
a gate whose scanned files are unchanged returns its previous result instead of
re-running its tool. File scans deliberately skip it: the cache is keyed on a
hash of the whole scanned file set, so a one-file scan would overwrite the
workspace entries with a one-file hash and turn the next full scan into a total
miss. The cache file (`.gandalf-cache.json` by default) belongs in `.gitignore`
— or point `gandalf.scan.cachePath` at `.git/gandalf-cache.json` and forget
about it.

**6. Bound the parallelism.** `gandalf.scan.concurrency` caps gates in flight.
Gandalf defaults to your CPU count; on a laptop that is also running a dev
server, 3–4 keeps the machine responsive. `gandalf.scan.timeoutSeconds` kills a
run that gets stuck.

**7. Idle machines stay idle.** Periodic sweeps are skipped while the window is
in the background, and skipped entirely if a scan already ran recently.

**8. Nothing lands in your repository.** Reports go to the extension's storage
directory (`--out-dir`), not `reports/`, and the trend log is not appended to
(`--no-trend`) — a scan on every save would swamp a history that is meant to be
per-commit. Old reports are pruned to the newest `gandalf.reports.keep` runs.
Both are settings if you want the CLI behaviour back.

**9. The LLM stays off** for background scans. Summaries cost a round trip to a
model; ask for one when you want to read it (`Gandalf: Open Report (regenerate
with LLM summary)`), or set `gandalf.scan.llm`.

### Profiles worth copying

Comfortable default — nothing to configure:

```jsonc
{ "gandalf.scan.trigger": "onSave", "gandalf.scan.scopeOnSave": "file" }
```

Large repository or slow gates — narrow what runs while you work, and sweep
everything twice an hour:

```jsonc
{
  "gandalf.scan.trigger": "onSaveAndInterval",
  "gandalf.scan.intervalMinutes": 30,
  "gandalf.scan.concurrency": 4,
  "gandalf.configPath": ".gandalf.vscode.toml"
}
```

```toml
# .gandalf.vscode.toml — the fast gates only; CI still runs .gandalf.toml in full.
[gandalf]
only = ["ruff", "format", "mypy", "bandit", "gitleaks", "build"]

[gandalf.timeouts]
default = 60
```

Battery saver — scan only when asked:

```jsonc
{ "gandalf.scan.trigger": "manual", "gandalf.scan.onStartup": false }
```

Commit-shaped feedback — judge what you are about to commit:

```jsonc
{ "gandalf.scan.scopeOnSave": "staged" }
```

Also worth knowing: a `.gandalfignore` at the repo root keeps tree-scanning
gates (`trivy`, `checkov`, `kics`) out of local state like `.env` or `data/`,
and `[gandalf.timeouts]` in `.gandalf.toml` gives a slow gate its own budget.

## Settings

Every setting is under `gandalf.` — `gandalf.executable`, `gandalf.checkoutPath`,
`gandalf.pythonPath`, `gandalf.configPath`, `gandalf.extraArgs`, the
`gandalf.scan.*` group described above, `gandalf.diagnostics.*`
(`enabled`, `minSeverity`, `maxPerFile`), `gandalf.reports.*`
(`directory`, `keep`, `recordTrend`), `gandalf.tools.image` and
`gandalf.statusBar.enabled`. VS Code's settings UI has the full list with
descriptions (search for "Gandalf").

Gate selection (`only` / `skip`) lives in `.gandalf.toml`, not on the command
line — point `gandalf.configPath` at an editor-specific config to run a
different gate set while you work.

## Notes and limits

- **Multi-root workspaces**: scans target the folder holding the active editor,
  and results are kept per folder.
- **Results are per session** — they live in memory, not on disk. The startup
  scan repopulates them.
- **The pane and the status bar are native**; the only webview is the report
  itself, because it is gandalf's own HTML document rendered unchanged.
- **`--path` needs a tracked file**: a file git doesn't know about is skipped
  (silently, in the log) rather than scanned.
- **Findings without a location** — a scorecard check, an architecture judgement
  — appear in the pane, not as squiggles. There is nowhere to put them.

## Development

```sh
npm install
npm run check     # tsc --noEmit
npm test          # normalizer unit tests (node --test, no framework)
npm run build     # bundle to dist/ with esbuild
npm run watch     # rebuild on change; F5 in VS Code launches an Extension Host
npm run package   # .vsix
```

The extension talks to gandalf only through its CLI and its JSON report, so it
stays useful against any gandalf checkout. `src/parse.ts` is the one piece that
has to understand gate output; its key lists mirror `gandalf/report.py`,
`gandalf/sarif.py` and `gandalf/suppress.py`, and it is covered by unit tests
with fixtures taken from real gate output.

## License

Apache-2.0, same as gandalf.
