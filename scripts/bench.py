#!/usr/bin/env python3
"""Benchmark gandalf's in-process hot paths, and draw the result.

Deliberately *not* part of the test suite. A wall-clock assertion on a shared CI
runner is either too loose to catch anything or too tight to survive a noisy
neighbour — the invariants that belong in CI (how many times a listing is read,
how many writes cross to the renderer) live in tests/test_perf.py and
extensions/vscode/src/test/perf.test.ts. This is the other half: real numbers,
on your machine, when you want to know how big something actually is.

Every row that can be measured both ways *is* — the old implementation is kept
here beside the new one so the comparison is a measurement rather than a memory.

    make bench                        # table + docs/assets/performance.svg
    python3 scripts/bench.py --json   # machine-readable, for a diff over time

Stdlib only, like the rest of gandalf.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import tracemalloc
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from gandalf import findings as gfindings  # noqa: E402
from gandalf import plugins, scope  # noqa: E402

# Big enough that the numbers mean something, small enough that `make bench`
# stays a coffee-free operation.
FINDINGS = 20_000
TREE_PATHS = 25_000
HASH_FILES = 2_000
REPO_FILES = 400
REPEAT = 5


def timed(fn, repeat: int = REPEAT) -> float:
    """Milliseconds for the fastest of `repeat` runs.

    The fastest, not the mean: every source of noise on a developer machine
    makes a run slower and none make it faster, so the minimum is the closest
    thing to the cost of the work itself.
    """
    best = float("inf")
    for _ in range(repeat):
        started = time.perf_counter()
        fn()
        best = min(best, time.perf_counter() - started)
    return best * 1000


def peak_mb(fn) -> float:
    """Peak heap in MiB while `fn` runs."""
    tracemalloc.start()
    try:
        fn()
        return tracemalloc.get_traced_memory()[1] / (1024 * 1024)
    finally:
        tracemalloc.stop()


# --- the subjects ------------------------------------------------------------


def bench_tree_filter() -> dict:
    """The exclusion filter, applied to every path in the tree on every scan."""
    pats = plugins.ignore_patterns(".") + ("*.min.js", "src/generated", "vendor")
    paths = [f"src/pkg{i % 200}/mod{i}.py" for i in range(TREE_PATHS)]
    plugins._compiled_ignores.cache_clear()

    def run():
        return [p for p in paths if not plugins.is_ignored(p, pats)]

    return {
        "id": "tree-filter",
        "label": f"Exclusion filter, {TREE_PATHS // 1000}k paths",
        "unit": "ms",
        "after": timed(run),
    }


def bench_content_hash(tmp: Path) -> dict:
    """The cache key: one hash over every scanned file's name and contents.

    `read_bytes()` pulled each file into memory whole; `file_digest` reads it in
    fixed-size blocks.

    The file-size distribution decides this one, so the fixture has to be a
    realistic tree rather than a flat one. On nothing but small source files
    `read_bytes` is about 20% quicker — one syscall beats a read loop. Add the
    one large tracked file that most repos have (a fixture, a vendored blob, a
    lockfile) and it inverts hard: that file's whole contents land on the heap,
    and the block reader is faster as well as smaller. Bounded loses slightly on
    the tidy case and wins enormously on the untidy one, so bounded it is.
    """
    root = tmp / "hashtree"
    root.mkdir()
    small = b"x = 1\n" * 2_000  # ~12 KB, a plausible source file
    files = []
    for i in range(HASH_FILES):
        f = root / f"mod{i}.py"
        f.write_bytes(small)
        files.append(f"mod{i}.py")
    # The tail every real repository has.
    (root / "fixture.bin").write_bytes(b"\0" * (32 * 1024 * 1024))
    files.append("fixture.bin")

    def old():
        h = hashlib.sha256()
        for f in sorted(files):
            h.update(f.encode())
            h.update(hashlib.sha256((root / f).read_bytes()).digest())
        return h.hexdigest()

    def new():
        h = hashlib.sha256()
        for f in sorted(files):
            h.update(f.encode())
            with (root / f).open("rb") as fh:
                h.update(hashlib.file_digest(fh, "sha256").digest())
        return h.hexdigest()

    assert old() == new(), "the optimisation must not change the cache key"
    return [
        {
            "id": "content-hash",
            "label": f"Cache key, {HASH_FILES // 1000}k files + a 32 MiB blob",
            "unit": "ms",
            "before": timed(old, 3),
            "after": timed(new, 3),
        },
        {
            "id": "content-hash-mem",
            "label": "Cache key, peak heap",
            "unit": "MiB peak",
            "before": peak_mb(old),
            "after": peak_mb(new),
        },
    ]


def _payload(n: int) -> dict:
    """A run record the size of a first scan of a large untended repo."""
    per_gate = n // 40
    return {
        "scope": "working-tree",
        "verdict": "warn",
        "score": 61,
        "gates": [
            {
                "name": f"gate{g}",
                "outcome": "warn",
                "score": 0.5,
                "summary": f"gate{g}: {per_gate} finding(s)",
                "findings": [
                    {
                        "path": f"src/pkg{i % 200}/mod{i % 500}.py",
                        "line": (i % 400) + 1,
                        "message": f"finding {g}-{i} — something the tool wants changed",
                        "severity": ("HIGH", "MEDIUM", "LOW")[i % 3],
                        "rule_id": f"R{i % 90:03d}",
                    }
                    for i in range(per_gate)
                ],
            }
            for g in range(40)
        ],
    }


def bench_report_write(tmp: Path) -> dict:
    """Writing the JSON report.

    `write_text(json.dumps(...))` renders the whole document into a string and
    then hands it to the writer, so the process holds the report twice over at
    the moment it is written. `json.dump` streams it into the file instead. The
    saving is memory, not time — the bar is peak heap.
    """
    payload = _payload(FINDINGS)
    out = tmp / "report.json"

    def old():
        out.write_text(json.dumps(payload, indent=2, default=str))

    def new():
        with out.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, default=str)

    old()
    first = out.read_text()
    new()
    assert out.read_text() == first, "the file must come out byte-identical"
    return {
        "id": "report-write",
        "label": f"Write JSON report, {FINDINGS // 1000}k findings",
        "unit": "MiB peak",
        "before": peak_mb(old),
        "after": peak_mb(new),
    }


def bench_annotate() -> dict:
    """Reconciling every finding's path/line/rule — runs once per report."""
    raw = [g["findings"] for g in _payload(FINDINGS)["gates"]]
    flat = [f for gate in raw for f in gate]

    return {
        "id": "annotate",
        "label": f"Reconcile {FINDINGS // 1000}k findings",
        "unit": "ms",
        "after": timed(lambda: gfindings.annotate_all(flat, ""), repeat=3),
    }


def bench_languages(tmp: Path) -> dict:
    """Detecting the languages in scope, on a whole-tree scan.

    The old implementation ran its own `git ls-files`; the gates then ran
    another one moments later. The new one reads the listing plugins already
    cached — the saving is an entire subprocess, which is most of the cost.
    """
    repo = tmp / "repo"
    repo.mkdir()
    for i in range(REPO_FILES):
        f = repo / f"src/pkg{i % 20}/mod{i}.py"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("x = 1\n")
    git = ["git", "-c", "user.email=b@e.com", "-c", "user.name=b"]
    subprocess.run([*git, "init", "-q", "."], cwd=repo, check=True)
    subprocess.run([*git, "add", "-A"], cwd=repo, check=True)
    subprocess.run(
        [*git, "-c", "commit.gpgsign=false", "commit", "-qm", "init"],
        cwd=repo,
        check=True,
    )
    root = str(repo)

    def old():
        # scope.languages as it was: its own listing, split on whitespace.
        out = subprocess.run(
            ["git", "ls-files"], cwd=root, capture_output=True, text=True, check=True
        ).stdout
        return scope._classify(out.split())

    def new():
        return scope.languages(root, [])

    plugins.tracked_files.cache_clear()
    new()  # Warm the cache, as the first gate would.
    assert old() == new() == {"python"}
    return {
        "id": "languages",
        "label": f"Detect languages, {REPO_FILES}-file tree",
        "unit": "ms",
        "before": timed(old),
        "after": timed(new),
    }


# --- the extension half ------------------------------------------------------


def bench_extension(repo_root: Path) -> list[dict]:
    """Run the VS Code extension's bench, if node and its deps are here.

    Skipped rather than failed when they aren't: the Python half is useful on
    its own, and not everyone working on gandalf has the extension set up.
    """
    ext = repo_root / "extensions" / "vscode"
    if not shutil.which("node") or not (ext / "node_modules").is_dir():
        print("  (extension bench skipped — needs node and `npm install` in", ext, ")")
        return []
    build = subprocess.run(
        ["node", "esbuild.mjs", "--bench"], cwd=ext, capture_output=True, text=True
    )
    if build.returncode != 0:
        print("  (extension bench skipped — build failed)\n", build.stderr[-500:])
        return []
    run = subprocess.run(
        ["node", "out/bench.js"], cwd=ext, capture_output=True, text=True
    )
    if run.returncode != 0:
        print("  (extension bench skipped — run failed)\n", run.stderr[-500:])
        return []
    try:
        return json.loads(run.stdout)
    except json.JSONDecodeError:
        print("  (extension bench skipped — unreadable output)")
        return []


# --- output ------------------------------------------------------------------


def table(rows: list[dict]) -> str:
    width = max(len(r["label"]) for r in rows)
    out = [f"  {'':{width}}   {'before':>10}  {'after':>10}   change"]
    for r in rows:
        before = r.get("before")
        after = r["after"]
        unit = r["unit"]
        b = f"{before:.1f}" if before is not None else "—"
        change = ""
        if before is not None and after > 0:
            change = (
                f"{before / after:.1f}x faster"
                if "ms" in unit
                else f"{before / after:.1f}x smaller"
            )
        out.append(
            f"  {r['label']:{width}}   {b:>10}  {after:>10.1f}   {change}   ({unit})"
        )
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="bench", description=__doc__.split("\n")[0])
    ap.add_argument("--json", action="store_true", help="emit the raw measurements")
    ap.add_argument("--svg", metavar="PATH", help="write the chart here")
    ap.add_argument("--no-extension", action="store_true", help="skip the VS Code half")
    args = ap.parse_args(argv)

    repo_root = Path(__file__).resolve().parent.parent
    rows: list[dict] = []
    with tempfile.TemporaryDirectory(prefix="gandalf-bench-") as tmp:
        d = Path(tmp)
        if not args.json:
            print(
                f"gandalf bench — python {sys.version.split()[0]}, {os.cpu_count()} cpu\n"
            )
        for subject in (
            lambda: bench_tree_filter(),
            lambda: bench_content_hash(d),
            lambda: bench_report_write(d),
            lambda: bench_annotate(),
            lambda: bench_languages(d),
        ):
            produced = subject()
            for row in produced if isinstance(produced, list) else [produced]:
                row["side"] = "gandalf"
                rows.append(row)
        if not args.no_extension:
            for row in bench_extension(repo_root):
                row["side"] = "extension"
                rows.append(row)

    if args.json:
        json.dump(rows, sys.stdout, indent=2)
        print()
        return 0

    print(table(rows))
    if args.svg:
        from chart import render  # noqa: PLC0415 — only needed for --svg

        target = Path(args.svg)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(render(rows))
        print(f"\n  chart: {target}")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    raise SystemExit(main())
