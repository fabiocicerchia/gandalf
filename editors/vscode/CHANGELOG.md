# Changelog

## 0.1.0

First release.

- Findings as editor diagnostics, with the gate, category, severity and rule id
  in the hover.
- Findings pane in the bottom panel as a native tree view: grouped by file,
  severity icons, error badge, current-file / whole-project toggle and a
  severity quick pick in the title bar.
- The gandalf HTML report, rendered as-is in an editor tab and themed to match
  the editor.
- Scans on save (scoped to the saved file), on demand, at startup, or on an
  interval — debounced, coalesced, serialized, and skipped when the file has not
  changed.
- Environment check listing every scanner tool and where it comes from, plus a
  one-command build of the `gandalf-tools` image.
- Autofix (`--fix`) and baseline (`--write-baseline`) commands, both confirmed
  before they touch anything.
