# Performance

## What this measures — and what it doesn't

**A real scan is dominated by the gates, not by gandalf.** Thirty-odd gates each
shell out to a linter, a scanner, or a `docker run`; that is tens of seconds,
and no amount of tuning in gandalf's own code touches it. If a scan feels slow,
the lever is the gate set — `gandalf --debug` names the slowest gates, and the
VS Code extension's **Gandalf: Show Gate Timings** copies a ready-made skip
list.

Everything on this page is the *other* cost: the work gandalf and the extension
do themselves, between the gates finishing and the report appearing. It matters
because it is the part that runs on the editor's UI thread, and the part that
scales with the number of findings rather than with the number of gates.

![Bar chart: where a scan's in-process time and memory go, previous
implementation against current, for eight operations across two panels — time in
milliseconds and peak memory in mebibytes](assets/performance.svg)

## Running it

```sh
make bench                          # table + redraws the chart above
python3 scripts/bench.py --json     # machine-readable, to diff over time
```

Stdlib only, no dependencies. The extension half needs `node` and an
`npm install` in `extensions/vscode`; without them that section is skipped and
the gandalf half still runs.

Each figure is the **fastest** of several runs, not the mean: every source of
noise on a developer machine makes a run slower and none make it faster, so the
minimum is the closest thing to the cost of the work itself. Absolute numbers
are machine-specific — the reference run below is a 16-core Linux box on Python
3.13 — but the *ratios* travel.

| Operation | Before | After | |
|---|---:|---:|---|
| Rebuild the board, 40 streamed gates | — | 570 ms | |
| Reconcile 20k findings | — | 136 ms | |
| Cache key, 2k files + a 32 MiB blob | 108 ms | 100 ms | |
| Exclusion filter, 25k paths | — | 79 ms | |
| Normalize 20k findings (extension) | — | 65 ms | |
| Detect languages, 400-file tree | 1.74 ms | 0.24 ms | **7.4x faster** |
| Sort 20k findings (extension) | — | 1.66 ms | |
| Cache key, peak heap | 32.0 MiB | 0.27 MiB | **118x smaller** |
| Write JSON report, 20k findings | 8.47 MiB | 0.05 MiB | **166x smaller** |

## Where the wins came from

**Peak memory, twice.** `write_text(json.dumps(...))` renders the whole report
into a string and *then* writes it, so the process holds the document twice over
at the moment it lands; `json.dump` streams it into the file. Separately, the
cache key hashed each file with `read_bytes()`, which puts that file's entire
contents on the heap — one 32 MiB tracked blob was a 32 MiB spike. `file_digest`
reads in fixed-size blocks.

**One listing, not two.** `scope.languages()` ran its own `git ls-files`
moments before the gates ran another one. It now reads the cached listing —
which also fixed a bug, since plain `ls-files` quotes non-ASCII paths and the
old whitespace `split()` mangled them into nothing a language matcher
recognised.

**Counted, not timed.** Three more changes don't appear above because their win
is a count rather than a duration, and counts are asserted in the test suite
instead: the findings pane walks the board **once** per repaint rather than two
or three times, diagnostics are published in **one** bulk write rather than one
per file, and the report webview no longer re-renders a multi-megabyte document
into a hidden tab on every save.

## Two things that measured the wrong way

Kept here because the obvious "optimization" is wrong in both cases, and the
next person will otherwise try it again.

**Hoisting an `Intl.Collator` out of the sort comparator made it 5x slower** —
33 ms against 6 ms sorting 20k paths. V8 already fast-paths
`String.prototype.localeCompare` for the default locale; extracting `.compare`
loses that fast path, and `numeric: true` disables it outright. The comparator
in `parse.ts` carries a note saying so.

**`file_digest` is about 20% slower than `read_bytes()` on a tree of nothing but
small source files** — one syscall beats a read loop. It was kept anyway,
because the moment a repo contains one large tracked file the result inverts
hard: on the mixed tree benchmarked above it is *both* faster and 118x smaller.
Bounded memory loses slightly on the tidy case and wins enormously on the untidy
one.

Both were caught by keeping the old implementation next to the new one in the
benchmark, so a claimed speedup has to survive being measured.

## The CI half

Timings don't belong in CI, so the regressions that matter are pinned as
invariants that hold on any machine, at any load:

- `tests/test_perf.py` — the ignore patterns are compiled once per tree walk,
  the tracked listing is read from git once per workdir, a scoped run never
  enumerates the tree at all.
- `extensions/vscode/src/test/perf.test.ts` — one path resolution per distinct
  file, one board walk per repaint, one bulk diagnostic write per publish.

Each ends with a deliberately loose complexity tripwire (25k paths, 20k
findings) sized so that only a genuine change of algorithmic shape can trip it.
