"""Autofixes, and what they actually rewrote.

A fixer reports its work in whatever words its tool prints, so the worktree is
diffed either side of it instead — see `_tree_state`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .base import Gate, GateContext

import hashlib
import subprocess

from . import debug


def _tree_state(workdir: str) -> dict[str, str]:
    """path → a hash of that file's uncommitted content, for every file git
    currently sees as modified.

    A fixer reports what it did in whatever words its tool prints, and the tools
    disagree wildly: ruff counts what it fixed, `eslint --fix` says nothing at
    all and exits non-zero whenever anything unfixable is left over. Diffing the
    worktree either side of a fixer answers the question none of them answer —
    which files it actually rewrote — and answers it the same way for a plugin's
    fixer as for a built-in one. Empty, and so silent, outside a git worktree.
    """
    try:
        out = subprocess.run(  # nosec B603 B607 - fixed git argv, no shell
            ["git", "diff", "--no-color", "--no-ext-diff"],  # noqa: S607 — resolved from PATH on purpose: the tool may be a host binary or a shim
            cwd=workdir,
            capture_output=True,
            text=True,
            check=False,
        ).stdout
    except OSError:
        return {}
    chunks: dict[str, list[str]] = {}
    body: list[str] | None = None
    for line in out.splitlines():
        if line.startswith("diff --git "):
            body = chunks.setdefault(line.split(" b/", 1)[-1], [])
        elif body is not None:
            body.append(line)
    return {path: hashlib.sha256("\n".join(lines).encode()).hexdigest() for path, lines in chunks.items()}


def _touched(before: dict[str, str], after: dict[str, str]) -> list[str]:
    """Files whose content differs between two worktree states."""
    return sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))


def _files_note(paths: list[str], limit: int = 5) -> str:
    """The rewritten files, named — and counted instead once there are too many
    of them to read in a terminal line."""
    shown = ", ".join(paths[:limit])
    return f"{shown}, …+{len(paths) - limit} more" if len(paths) > limit else shown


async def run_fixers(gates: list[Gate], ctx: GateContext) -> list[tuple[str, bool, str]]:
    """Apply autofixes from gates that expose `async def fix(ctx)`. Sequential —
    fixers edit files (e.g. ruff --fix then ruff format on the same files), so
    order matters and concurrent writes would race. Returns [(name, changed, msg)].

    What each fixer changed is measured from the worktree rather than taken from
    its own word — see _tree_state."""
    out = []
    before = _tree_state(ctx.workdir)
    for g in gates:
        fix = getattr(g, "fix", None)
        if fix is None:
            continue
        try:
            changed, msg = await fix(ctx)
        except Exception as exc:
            changed, msg = False, f"fix errored: {exc}"
        after = _tree_state(ctx.workdir)
        if touched := _touched(before, after):
            changed, msg = True, f"{msg} — {_files_note(touched)}"
            debug.log(f"fix {g.name}: rewrote {len(touched)} file(s)")
        before = after
        out.append((g.name, changed, msg))
    return out
