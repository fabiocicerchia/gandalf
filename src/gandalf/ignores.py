"""Which files a gate is allowed to look at.

The tracked-file listing, the ignore patterns (built-in defaults, a repo's
`.gandalfignore`, `--exclude`), the matcher they compile into, and the scan
target list every gate asks for. One answer, cached, so twenty gates do not
each walk the tree.
"""

from __future__ import annotations

import re
import subprocess
from fnmatch import translate
from functools import lru_cache
from pathlib import Path

from .base import GateContext


@lru_cache(maxsize=8)
def tracked_files(workdir: str) -> tuple[str, ...]:
    """git-tracked files (repo-relative), cached per workdir. Whole-tree scans
    use this instead of '.', so untracked/vendored trees (e.g. a vendored
    llama.cpp checkout) aren't dragged in and don't blow the per-gate timeout."""
    try:
        out = subprocess.run(  # nosec B603 B607 - fixed git argv, no shell
            ["git", "ls-files", "-z"],
            cwd=workdir,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return ()
    return tuple(p for p in out.split("\0") if p)


# Every gate skips these by default: build, vendor and report noise that isn't
# the repo's own source. This keeps the tool generic — it's used against many
# repos, so nothing repo-specific is hardcoded.
_DEFAULT_IGNORES = ("reports", "node_modules", "llama.cpp", ".venv", ".git")

# Set once from --exclude before any gate runs (see __main__.main), so a caller
# that knows what to skip — an editor with its own excluded folders, a CI job —
# can say so without writing a file into the repo.
_EXTRA_IGNORES: tuple[str, ...] = ()


def set_extra_ignores(patterns) -> None:
    """Extend the ignore list for this process. Clears the caches built from it."""
    global _EXTRA_IGNORES
    _EXTRA_IGNORES = tuple(p.strip() for p in (patterns or []) if p and p.strip())
    ignore_patterns.cache_clear()
    scannable_files.cache_clear()
    _compiled_ignores.cache_clear()


@lru_cache(maxsize=8)
def ignore_patterns(workdir: str) -> tuple[str, ...]:
    """Paths no gate should look at: the built-in defaults, any lines from a
    repo-root ``.gandalfignore`` (one glob per line; blank lines and lines
    starting with ``#`` ignored), and anything passed to --exclude. Deduped,
    order preserved. A dir name (``data``), a path (``src/generated``) and a
    glob (``*.min.js``) all work — see is_ignored."""
    pats = list(_DEFAULT_IGNORES)
    f = Path(workdir) / ".gandalfignore"
    if f.is_file():
        for line in f.read_text(errors="replace").splitlines():
            s = line.strip()
            if s and not s.startswith("#"):
                pats.append(s)
    pats.extend(_EXTRA_IGNORES)
    return tuple(dict.fromkeys(pats))  # de-dup, order preserved


def _alternation(pats: list[str]):
    """One regex matching any of the globs, or None when there are none."""
    return re.compile("|".join(f"(?:{translate(g)})" for g in pats)) if pats else None


@lru_cache(maxsize=16)
def _compiled_ignores(patterns: tuple[str, ...]):
    """Sort the patterns into the cheapest test each one allows.

    Naively fnmatching every pattern against every path costs ~900ms on a 25k
    file tree, and this runs on every scan. Most patterns are plain directory
    names, which a set membership test answers; only the ones with glob
    characters need a regex, and those collapse into one alternation."""
    names: set[str] = set()  # bare names: match any path segment
    prefixes: list[str] = []  # anchored paths: match the path or a parent of it
    segment_globs: list[str] = []  # globs with no separator: match any segment
    path_globs: list[str] = []  # globs with a separator: match the whole path
    for raw in patterns:
        pat = raw.strip().replace("\\", "/").removeprefix("./").rstrip("/")
        if not pat:
            continue
        globbed = any(c in pat for c in "*?[")
        if not globbed and "/" not in pat:
            names.add(pat)
        elif not globbed:
            prefixes.append(pat)
        elif "/" in pat:
            path_globs.append(pat)
            prefixes.append(pat)
        else:
            segment_globs.append(pat)

    # A glob is tried against the whole path as well, because fnmatch's `*`
    # spans separators — `*.min.js` is expected to match `web/app.min.js`.
    return (
        names,
        tuple(prefixes),
        _alternation(segment_globs),
        _alternation(path_globs + segment_globs),
    )


def _under(p: str, prefixes: tuple[str, ...]) -> bool:
    """Whether the path is one of these anchored paths, or sits inside one."""
    return any(p == pre or p.startswith(pre + "/") for pre in prefixes)


def is_ignored(rel: str, patterns: tuple[str, ...]) -> bool:
    """gitignore-ish match of a repo-relative path against the ignore patterns.

    A pattern matches when it equals or globs the whole path, the basename, any
    single directory segment, or a leading directory prefix. That covers the
    three ways people write these: a bare directory name to skip everywhere
    (``node_modules``), a path anchored at the root (``src/generated``), and a
    glob (``*.min.js``)."""
    p = rel.replace("\\", "/").removeprefix("./")
    if not p:
        return False
    names, prefixes, segment_re, path_re = _compiled_ignores(tuple(patterns))
    segments = p.split("/")
    if names and not names.isdisjoint(segments):
        return True
    if _under(p, prefixes):
        return True
    if path_re is not None and path_re.match(p):
        return True
    return segment_re is not None and any(segment_re.match(s) for s in segments)


@lru_cache(maxsize=8)
def scannable_files(workdir: str) -> tuple[str, ...]:
    """Tracked files minus the ignored ones. Cached because the whole-tree filter
    is O(files × patterns) and every gate asks for the same answer."""
    pats = ignore_patterns(workdir)
    return tuple(f for f in tracked_files(workdir) if not is_ignored(f, pats))


def _changed_in_scope(
    ctx: GateContext, pats: tuple[str, ...], py_only: bool
) -> list[str]:
    """The change's own files that still exist and are not ignored. Deletions
    and non-existent paths are dropped."""
    root = Path(ctx.workdir)
    return [
        rel
        for rel in ctx.changed_files or []
        if (not py_only or rel.endswith(".py"))
        and not is_ignored(rel, pats)
        and (root / rel).is_file()
    ]


def _scan_targets(ctx: GateContext, *, py_only: bool = False) -> list[str]:
    """Files to scan: the change's own files (bounded runtime, scoring reflects
    the diff not pre-existing repo issues), falling back to the git-tracked tree
    when the changed set is empty. Deletions/non-existent paths are dropped.

    Whole-tree mode scans tracked files rather than '.', so an untracked/vendored
    subtree never enters the scan. Only when the workdir isn't a git repo (no
    tracked files) does it fall back to '.'.

    Ignored paths (.gandalfignore, --exclude, the built-in defaults) are dropped
    from both, so an exclusion narrows what *every* gate reads rather than only
    the few that translate the list into their tool's own exclude flag."""
    targets = _changed_in_scope(ctx, ignore_patterns(ctx.workdir), py_only)
    if targets:
        return targets
    tracked = scannable_files(ctx.workdir)
    if py_only:
        tracked = tuple(p for p in tracked if p.endswith(".py"))
    return list(tracked) or ["."]
