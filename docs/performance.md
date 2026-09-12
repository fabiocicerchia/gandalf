# Performance

## Making a slow scan faster

**A real scan is dominated by the gates, not by gandalf.** Thirty-odd gates each
shell out to a linter, a scanner, or a `docker run`; that is tens of seconds to
minutes, and no amount of tuning in gandalf's own code touches it. The lever is
the gate set and the order it runs in.

### First: find out where the time actually goes

```sh
gandalf --debug          # or GANDALF_DEBUG=1, which the editor extension sets
```

Every line carries the elapsed time it was written at, so the log reads as a
timeline: each stage as it starts, the order the gates were scheduled in, each
gate's start and its duration, and every external command with its timeout and
exit code. The run ends with the five slowest gates.

Reach for it especially when a scan *doesn't* finish. The timings in the report
and the extension's **Gandalf: Show Gate Timings** can only describe gates that
got to the end; a gate still running when the editor's timeout fires appears in
neither, and the `--debug` log is the only place it is named — look for a `gate
<name>: start` with no matching completion.

### Then: the levers, roughly in order of what they save

| Lever | What it does |
|---|---|
| `--no-llm` | Drops the LLM summary *and* the judge gates (`grill_me`, `codebase_architecture`, `well_architected`, `compliance`, the `skill_*` gates). Each is a full model round trip; with nothing listening at `GANDALF_LLM_URL` each is a connect timeout plus its retries instead. For an editor or pre-commit run this is usually the largest single saving. |
| `skip` in `.gandalf.toml` | The honest answer for a gate that costs minutes and tells you something you already know from CI — `codeql`, `ci_act`, a full test-suite gate. In the repository, where it can be reviewed. |
| `--cache` | A gate whose files did not change is not re-run at all. Advisory gates (`trivy`, `osv`, …) still expire after six hours, because a new CVE is a new answer for identical bytes. |
| `--exclude` / `.gandalfignore` | Vendored trees and generated code are usually most of what a full-tree scanner reads. |
| `[gandalf.timeouts]` | Bounds the worst case per gate rather than removing it: `semgrep = 60` degrades that gate to amber at a minute instead of letting it own the run. |
| `--concurrency N` | Trades wall-clock for a responsive machine. Rarely a speed-up on its own — see below. |

### Why the order gates run in matters

Gates run concurrently but bounded, so there is a queue, and whichever gate
starts last decides when the run ends. Discovery order is alphabetical by module
filename, which put `bandit` first and `trivy` near the back: the queue drained
into a five-minute scanner that nothing could overlap with.

Gates are now submitted **heaviest first** — longest-processing-time-first, the
standard scheduling answer — so the expensive ones start immediately and the
quick ones fill in behind them. The estimate is, in order of preference: what
the gate cost last time (recorded per gate in the `--cache` file, so the second
run on a repository schedules by measurement), a `cost` attribute a gate
declares for itself, then a coarse built-in prior. See `gandalf/schedule.py`.

The practical consequence is that lowering `--concurrency` is much less
punishing than it was: with `--concurrency 2` the two heaviest gates are the two
that start, rather than two arbitrary linters while trivy waits.

## What the benchmark measures — and what it doesn't

Everything below is the *other* cost: the work gandalf and the extension
do themselves, between the gates finishing and the report appearing. It matters
because it is the part that runs on the editor's UI thread, and the part that
scales with the number of findings rather than with the number of gates. It is
not where a slow scan's minutes are.

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
