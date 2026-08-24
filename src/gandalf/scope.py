"""Resolve what to evaluate from git state.

Returns a Scope: the workdir gates run against, the changed_files list, and a
diff string for the LLM summary. `--commit` runs against a throwaway worktree
checked out at that commit; the caller must use Scope as a context manager so
the worktree is cleaned up.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Self


def _git(args: list[str], cwd: str = ".") -> str:
    return subprocess.run(  # nosec B603 B607 - fixed git argv, no shell
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=True
    ).stdout


def repo_root() -> str:
    """The repository containing the current directory.

    Everything else here assumes a repository, so this is where "there isn't
    one" has to be caught. git exits 128 for several distinct reasons — no
    repository, dubious ownership, an unreadable .git — and its stderr is the
    only thing that tells them apart, so that is what gets reported instead of
    a traceback out of subprocess.
    """
    try:
        return _git(["rev-parse", "--show-toplevel"]).strip()
    except FileNotFoundError:
        raise SystemExit("gandalf needs git on PATH, and it is not there") from None
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or "").strip().splitlines()
        reason = detail[0].removeprefix("fatal: ") if detail else "not a git repository"
        raise SystemExit(f"gandalf needs a git repository: {reason}") from None


# Map file extensions / marker filenames to a language tag. Gates tagged with a
# `langs` set only run when one of their tags is present in scope; untagged gates
# are generic and always run.
_EXT_LANG = {
    ".py": "python",
    ".pyi": "python",
    ".go": "go",
    ".rs": "rust",
    ".js": "node",
    ".jsx": "node",
    ".mjs": "node",
    ".cjs": "node",
    ".ts": "ts",
    ".tsx": "ts",
    ".sh": "shell",
    ".bash": "shell",
    ".yml": "yaml",
    ".yaml": "yaml",
    ".sql": "sql",
}
_MARKER_LANG = {
    "go.mod": "go",
    "Cargo.toml": "rust",
    "package.json": "node",
    "tsconfig.json": "ts",
    "pyproject.toml": "python",
    "setup.cfg": "python",
    "setup.py": "python",
    "requirements.txt": "python",
}


def _classify(paths: list[str]) -> set[str]:
    langs: set[str] = set()
    for p in paths:
        base = p.rsplit("/", 1)[-1]
        if base in _MARKER_LANG:
            langs.add(_MARKER_LANG[base])
        if (
            base == "Dockerfile"
            or base.startswith("Dockerfile.")
            or base.endswith(".dockerfile")
        ):
            langs.add("docker")
        dot = base.rfind(".")
        if dot != -1:
            langs.add(_EXT_LANG.get(base[dot:], ""))
    langs.discard("")
    return langs


def languages(workdir: str, changed_files: list[str]) -> set[str]:
    """Languages present in scope: from the changed files when scoped
    (--staged/--commit), else from the whole tracked tree (git ls-files, so the
    untracked vendored llama.cpp doesn't count)."""
    if changed_files:
        return _classify(changed_files)
    tracked = _git(["ls-files"], workdir).split()
    return _classify(tracked)


def commit_info(ref: str, workdir: str = ".") -> dict:
    """Short/full sha + subject + author-date (UTC) of a commit. For staged and
    working-tree scopes this is HEAD (the latest commit)."""
    try:
        out = _git(
            ["log", "-1", "--format=%H%x1f%h%x1f%s%x1f%cI", ref], workdir
        ).strip()
        full, short, subject, cdate = out.split("\x1f")
        return {"sha": full, "short": short, "subject": subject, "date": cdate}
    except (subprocess.CalledProcessError, ValueError):
        return {"sha": "", "short": "", "subject": "", "date": ""}


@dataclass
class Scope:
    label: str  # "working-tree" | "staged" | commit sha
    workdir: str
    changed_files: list[str] = field(default_factory=list)
    diff: str = ""
    commit: dict = field(
        default_factory=dict
    )  # ref commit (HEAD for staged/working-tree)
    _worktree: str | None = field(default=None, repr=False)

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc) -> None:
        if self._worktree:
            subprocess.run(  # nosec B603 B607 - fixed git argv, no shell
                ["git", "worktree", "remove", "--force", self._worktree],
                capture_output=True,
                check=False,
            )
            shutil.rmtree(self._worktree, ignore_errors=True)


def _narrow_to_path(sc: Scope, path: str) -> Scope:
    """Restrict a Scope to git-tracked, non-excluded files under `path`. On a
    whole-tree scope (empty changed_files) this becomes the folder's files; on a
    staged/commit scope it intersects the changed set with the folder.

    Excluded paths are dropped here rather than later because an empty scope has
    to fail loudly: `changed_files` empty means "whole tree" everywhere
    downstream, so silently narrowing to nothing would scan everything — the
    opposite of what --path asked for."""
    from .plugins import ignore_patterns, is_ignored  # local: avoids a cycle

    rel = path.strip().strip("/")
    under = [
        f for f in _git(["ls-files", "-z", "--", rel], sc.workdir).split("\0") if f
    ]
    if not under:
        raise SystemExit(f"--path {path!r}: no git-tracked files under this folder")
    pats = ignore_patterns(sc.workdir)
    under = [f for f in under if not is_ignored(f, pats)]
    if not under:
        raise SystemExit(f"--path {path!r}: every path under it is excluded")
    if sc.changed_files:
        keep = set(under)
        sc.changed_files = [f for f in sc.changed_files if f in keep]
    else:
        sc.changed_files = under
    sc.label = f"{sc.label}:{rel}"
    return sc


def resolve(commit: str | None, staged: bool, path: str | None = None) -> Scope:
    root = repo_root()
    if commit:
        sha = _git(["rev-parse", commit], root).strip()
        tmp = tempfile.mkdtemp(prefix="gandalf-wt-")
        _git(["worktree", "add", "--detach", "--force", tmp, sha], root)
        files = _git(["diff", "--name-only", f"{sha}~1", sha], root).split()
        diff = _git(["show", "--stat", "--format=%s%n%b", sha], root)
        sc = Scope(sha[:10], tmp, files, diff, commit_info(sha, root), _worktree=tmp)
    elif staged:
        files = _git(["diff", "--cached", "--name-only"], root).split()
        diff = _git(["diff", "--cached"], root)
        sc = Scope("staged", root, files, diff, commit_info("HEAD", root))
    else:
        # Default: evaluate the tree as-is (empty changed_files → gates scan the whole
        # repo). Whole-tree scans target git-tracked files only (see plugins.tracked_files),
        # so untracked/vendored trees (e.g. a vendored llama.cpp) don't enter the scan or
        # blow the per-gate timeout. Scope with --commit/--staged to scan just a change.
        diff = _git(["status", "--short"], root)
        sc = Scope("working-tree", root, [], diff, commit_info("HEAD", root))
    return _narrow_to_path(sc, path) if path else sc
