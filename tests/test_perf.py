"""Performance, asserted as *work done* rather than as elapsed time.

A wall-clock threshold on a shared CI runner is either so loose it catches
nothing or so tight it fails on a noisy neighbour. Every hot path here has a
countable invariant behind it instead — how many times a pattern set is
compiled, how many times git is asked the same question — and those hold on any
machine, at any load, at any tree size.

The scaling test at the end is a complexity tripwire, not a measurement: a bound
with enough headroom that only a genuine change of shape can trip it.
"""

from __future__ import annotations

import subprocess
import time

from gandalf import plugins, scope
from gandalf.ignores import _compiled_ignores
from gandalf.plugins import (
    ignore_patterns,
    is_ignored,
    scannable_files,
    tracked_files,
)


def _repo(tmp_path, files):
    repo = tmp_path / "repo"
    repo.mkdir()
    for rel in files:
        f = repo / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("x = 1\n")
    git = ["git", "-c", "user.email=t@e.com", "-c", "user.name=t"]
    subprocess.run([*git, "init", "-q", "."], cwd=repo, check=True)
    subprocess.run([*git, "add", "-A"], cwd=repo, check=True)
    subprocess.run(
        [*git, "-c", "commit.gpgsign=false", "commit", "-qm", "init"],
        cwd=repo,
        check=True,
    )
    return repo


def _reset_caches() -> None:
    plugins.set_extra_ignores([])
    tracked_files.cache_clear()
    scannable_files.cache_clear()
    ignore_patterns.cache_clear()
    _compiled_ignores.cache_clear()


def test_ignore_patterns_are_compiled_once_for_a_whole_tree_walk() -> None:
    """`is_ignored` is called once per file — on a large repo, tens of thousands
    of times. It must not rebuild the regex alternation on each of them."""
    _reset_caches()
    pats = ("node_modules", "src/generated", "*.min.js", ".venv")

    for i in range(5_000):
        is_ignored(f"src/pkg{i % 50}/mod{i}.py", pats)

    info = _compiled_ignores.cache_info()
    assert info.misses == 1, f"compiled {info.misses} times for one pattern set"
    assert info.hits == 4_999


def test_the_tracked_listing_is_read_from_git_once_per_workdir(tmp_path) -> None:
    """Every gate asks for the same file list. Shelling out to git per gate is
    ~35 subprocesses for one answer that cannot have changed mid-run."""
    _reset_caches()
    repo = str(_repo(tmp_path, [f"src/mod{i}.py" for i in range(5)]))

    for _ in range(20):
        scannable_files(repo)

    assert tracked_files.cache_info().misses == 1, "one `git ls-files` for the run"
    assert scannable_files.cache_info().misses == 1, "and one filter pass over it"


def test_languages_reuses_that_listing_instead_of_asking_git_again(tmp_path) -> None:
    """`languages()` runs immediately before the gates do, against the same tree.

    It used to issue its own `git ls-files`, so every whole-tree scan paid for
    two identical listings — and parsed the second one with `.split()`, which
    mangles any path git quotes. See test_ignore.py for that half of it.
    """
    _reset_caches()
    repo = str(_repo(tmp_path, ["src/app.py", "cmd/main.go"]))
    tracked_files(repo)  # Warm it, as the first gate would.
    before = tracked_files.cache_info()

    assert scope.languages(repo, []) == {"python", "go"}

    after = tracked_files.cache_info()
    assert after.misses == before.misses, "no second listing was fetched"
    assert after.hits == before.hits + 1, "it read the cached one"


def test_a_scoped_run_never_touches_the_tracked_listing_at_all(tmp_path) -> None:
    """With a changed set in hand there is nothing to list — a --staged scan of
    three files must not enumerate a 25k-file tree to classify them."""
    _reset_caches()
    repo = str(_repo(tmp_path, ["src/app.py"]))

    assert scope.languages(repo, ["src/app.py", "web/app.ts"]) == {"python", "ts"}
    assert tracked_files.cache_info().misses == 0, "git was never asked"


def test_filtering_a_large_tree_stays_linear() -> None:
    """The tripwire. 25k paths against a realistic pattern set is what a scan of
    a large untended repo costs; it is ~30ms when the pattern match is a set
    lookup plus one alternation, and minutes if it goes back to fnmatching every
    pattern against every path. The bound is deliberately absurd so a slow, cold
    or loaded runner cannot trip it on its own.
    """
    _reset_caches()
    pats = (*ignore_patterns("."), "*.min.js", "src/generated", "vendor")
    paths = [f"src/pkg{i % 200}/mod{i}.py" for i in range(25_000)]

    started = time.monotonic()
    kept = [p for p in paths if not is_ignored(p, pats)]
    elapsed = time.monotonic() - started

    assert len(kept) == 25_000, "nothing here matches an ignore pattern"
    assert elapsed < 10.0, f"25k paths took {elapsed:.1f}s — the match went quadratic"
