# Editor integration

## VS Code

The extension lives in [`editors/vscode/`](https://github.com/fabiocicerchia/gandalf/tree/main/editors/vscode)
and runs the same CLI you run by hand — it shells out to `gandalf`, reads the
JSON report, and shows the HTML report as-is. Nothing about gandalf changes
because an editor is driving it.

What you get:

- findings as diagnostics, with the gate, category, severity and rule in the hover;
- a native tree view in the bottom panel listing every finding, grouped by file
  and filtered to the current file or the whole project;
- the HTML scorecard in an editor tab;
- an environment check that says, tool by tool, which gates can actually run
  here — on `PATH`, from the `gandalf-tools` image, or not at all.

### Install

```sh
cd editors/vscode
npm install && npm run package     # produces gandalf-quality-gates-<version>.vsix
code --install-extension gandalf-quality-gates-*.vsix
```

The extension finds gandalf via `gandalf.executable`, `gandalf.checkoutPath`,
the open workspace (if it is a gandalf checkout), `gandalf` on `PATH`, or the
`~/.local/share/gandalf` clone that `install.sh` creates — in that order.

### Cost control

Gates spawn real tools, so the extension never scans on keystroke. Saving a file
scans *that file* (`--path`); the whole tree is scanned on demand, at startup,
or on an interval. Runs are debounced, coalesced and strictly serialized, an
unchanged file is not rescanned, wide scans reuse gandalf's `--cache`, and
artifacts go to the extension's own storage (`--out-dir`) with no trend entry
(`--no-trend`) rather than into `reports/`.

The [extension README](https://github.com/fabiocicerchia/gandalf/tree/main/editors/vscode#keeping-it-cheap)
has the full breakdown and ready-made settings profiles for large repositories,
laptops on battery, and commit-shaped feedback.

## Other editors

There is no dedicated plugin for other editors yet, but nothing stops one:
run `gandalf --no-llm --out-dir <dir>` and read `<dir>/<stem>.json`, or use
`--sarif` and feed any SARIF-aware viewer. See
[Reports and badges](reports.md) for the payload shape.
