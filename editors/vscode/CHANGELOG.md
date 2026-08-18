# Changelog

## 0.1.0

First release.

- Findings as editor diagnostics, with the gate, category, severity and rule id
  in the hover.
- Findings pane in the bottom panel as a native tree view: grouped by file, a
  distinct icon per reported level (critical / high / medium / low / info /
  unrated), error badge, expand-all and collapse-all, current-file /
  whole-project toggle, and a filter over both reported level and editor
  severity.
- The level a tool reports is kept as its own axis rather than collapsed into
  three editor severities, including the `[HIGH] …` prefix that the kics and
  licenses gates fold into the message text.
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
- `Gandalf: Show Score History` — the score across recent commits, read from the
  `.gandalf-trend.jsonl` gandalf already writes and joined against `git log`,
  with a sparkline and per-commit deltas. Picking a commit scans it and opens
  its report; that scan records a trend entry, unlike scans on save.
- `Gandalf: Export Report…` — save the HTML scorecard to a chosen location.
- Environment check listing every scanner tool and where it comes from, plus a
  one-command build of the `gandalf-tools` image. It also checks the LLM endpoint
  and, when it is unreachable, offers to stop the judge gates retrying it.
- Editor scans cap the LLM retry budget at 1. The
  judge gates call the model whatever `--no-llm` says, and gandalf's CI-shaped
  default of 3 retries with backoff was 14.4s of a 14.9s scan with no endpoint
  reachable; one retry brings that to 3.3s.
- The folders the editor hides (`files.exclude`, `search.exclude`) are excluded
  from scans too, translated into gandalf's `--exclude`; `gandalf.exclude` adds
  more, and `gandalf.useEditorExcludes` turns the automatic part off. Saving an
  excluded file starts no scan at all.
- Published to the Visual Studio Marketplace and to Open VSX from a
  `vscode-vX.Y.Z` tag, versioned separately from gandalf itself.
- Measured on a 10k-finding tree: one shared path cache per run (10,000
  synchronous filesystem calls down to 2,000), the merged board memoized against
  a revision counter (269 ms of repaint work per streamed scan down to ~0),
  streamed findings parsed without being buffered (two thirds of stdout
  discarded as it arrives), raw findings dropped from the retained report once
  normalized (4.5 MB down to 3.7 MB), and a saved file read once instead of
  twice.
