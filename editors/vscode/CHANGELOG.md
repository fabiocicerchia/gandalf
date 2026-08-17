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
- Live progress while a scan runs: stage and gate counter in the status bar,
  parsed from gandalf's own progress line, plus a cancellable notification with a
  progress bar for whole-tree scans.
- Findings stream into the pane per gate as the run proceeds (gandalf's new
  `--stream`), instead of appearing all at once when the report is written. The
  verdict and composite score still come from the final report, which then
  replaces the streamed results.
- `Gandalf: Show Gate Timings` — every gate by wall-clock cost, with a
  copy-a-skip-list action; the slowest five are logged after each full scan.
- Environment check listing every scanner tool and where it comes from, plus a
  one-command build of the `gandalf-tools` image. It also checks the LLM endpoint
  and, when it is unreachable, offers to stop the judge gates retrying it.
- Editor scans cap the LLM retry budget at 1 (`gandalf.scan.llmRetries`). The
  judge gates call the model whatever `--no-llm` says, and gandalf's CI-shaped
  default of 3 retries with backoff was 14.4s of a 14.9s scan with no endpoint
  reachable; one retry brings that to 3.3s.
- Autofix (`--fix`) and baseline (`--write-baseline`) commands, both confirmed
  before they touch anything.
