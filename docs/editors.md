# Editor integration

## VS Code

The extension lives in [`extensions/vscode/`](https://github.com/fabiocicerchia/gandalf/tree/main/extensions/vscode)
and runs the same CLI you run by hand — it shells out to `gandalf`, reads the
JSON report, and shows the HTML report as-is. Nothing about gandalf changes
because an editor is driving it.

What you get:

- findings as diagnostics, with the gate, category, severity and rule in the hover;
- a native tree view in the bottom panel listing every finding, grouped by file,
  with a distinct icon per reported level (critical / high / medium / low / info /
  unrated) and filters for level, editor severity and current-file vs project;
- the HTML scorecard in an editor tab;
- an environment check that says, tool by tool, which gates can actually run
  here — on `PATH`, from the `gandalf-tools` image, or not at all.

### Install

From the Marketplace — **Extensions** view, search *Gandalf — Quality Gates*, or:

```sh
code --install-extension fabiocicerchia.gandalf
```

It is published to the
[VS Marketplace](https://marketplace.visualstudio.com/items?itemName=fabiocicerchia.gandalf)
for VS Code and to
[Open VSX](https://open-vsx.org/extension/fabiocicerchia/gandalf)
for the forks (Cursor, Windsurf, VSCodium), from the same release.

To build it from a checkout instead — an unreleased change, or no Marketplace —
`make ext-install` from the repository root (`CODE=cursor` for a fork,
`make ext-package` to build the `.vsix` and install it by hand; Node 18+ for the
build only).

Reload the window afterwards; a **Gandalf** tab appears in the bottom panel.
For development, `npm run watch` and <kbd>F5</kbd> from `extensions/vscode/` launch
an Extension Development Host. It carries no version of its own: release-please
bumps its manifest along with `version.txt`, and publishing the release publishes
the extension — see
[Releasing](https://github.com/fabiocicerchia/gandalf/tree/main/extensions/vscode#releasing).

The extension finds gandalf via `gandalf.path` (a wrapper or a checkout — either
shape is recognised), the open workspace if it is a gandalf checkout, `gandalf`
on `PATH`, or the `~/.local/share/gandalf` clone that `install.sh` creates — in
that order. Run **Gandalf: Check Environment** first: it reports whether
gandalf, git, docker and the `gandalf-tools` image are present, and offers to
build the image.

### While a scan runs

The status bar shows a live gate counter (`Gandalf 12/37`) and a whole-tree scan
gets a cancellable notification with a progress bar — both read from the progress
line `gandalf/progress.py` already writes, enabled for a piped run with
`GANDALF_PROGRESS=1`.

Findings do not wait for the run to end, either: gandalf reports each gate as it
finishes (`--stream`) and the pane fills as the results land, replacing what the
last run said about that gate while the rest of the board stays up. The verdict
and the composite score still come only from the final report — a single gate
cannot produce them.

`Gandalf: Show Gate Timings` lists every gate by wall-clock cost so a slow scan
can name its culprits, and copies a `skip` list for the ones you don't want
while editing. `Gandalf: Show Score History` reads `.gandalf-trend.jsonl` back —
the log gandalf has always written and nothing has ever read — and shows the
score across recent commits, with any commit scannable from the list.

### Cost control

Gates spawn real tools, so the extension never scans on keystroke. Saving a file
scans *that file* (`--path`); the whole tree is scanned on demand, at startup,
or on an interval. Runs are debounced, coalesced and strictly serialized, an
unchanged file is not rescanned, wide scans reuse gandalf's `--cache`, and
artifacts go to the extension's own storage (`--out-dir`) with no trend entry
(`--no-trend`) rather than into `reports/`.

The [extension README](https://github.com/fabiocicerchia/gandalf/tree/main/extensions/vscode#keeping-it-cheap)
has the full breakdown and ready-made settings profiles for large repositories,
laptops on battery, and commit-shaped feedback.

## Other editors

There is no dedicated plugin for other editors yet, but nothing stops one:
run `gandalf --no-llm --out-dir <dir>` and read `<dir>/<stem>.json`, or use
`--sarif` and feed any SARIF-aware viewer. See
[Reports and badges](reports.md) for the payload shape.
