"""Shared shape for the per-ecosystem toolchain gates (java, ruby, php, cpp, dotnet).

Every one of those gates answers the same three questions before it says anything
interesting: is this ecosystem even in the tree, is its toolchain installed, and
what did the command report. golang.py and rust.py answer them inline and pay for
it in repetition — five more ecosystems at three or four gates each would be
twenty copies of the same eight lines. So the answers live here once, and a gate
file carries only what actually differs: the marker files, the binary, the
command, and how to read its output.

`parsed` and `scored` are the two steps *every* gate shares, ecosystem or not:
read the tool's JSON, then turn a finding count into a score. They live here
rather than in plugins.py because they are the gate author's vocabulary, not the
runner's.

Underscore-prefixed on purpose: plugins.discover_gates skips `_*.py`, so the base
class here is never mistaken for a gate of its own.
"""

from __future__ import annotations

import asyncio
import fnmatch
import json
import re
from pathlib import Path

from gandalf.base import GateContext, GateOutcome, GateResult
from gandalf.plugins import (
    _TIMEOUT_RC,
    run_tool,
    scannable_files,
    timeout_result,
    tool_missing,
    unavailable,
)

# A syntax check spawns one process per file, so the tree it runs over is capped:
# past a few hundred files the gate is measuring the spawn cost, not the code.
MAX_SYNTAX_FILES = 400
# Enough to keep the cores busy without turning a whole-tree scan into a fork bomb.
_PARALLEL = 8


def project_dir(ctx: GateContext, markers: tuple[str, ...]) -> str | None:
    """Absolute path of the shallowest directory holding a marker file, else None.

    A directory rather than a bool, because a build tool has to run where its
    manifest is: a `.csproj` two levels down is still a .NET project, and
    `dotnet build` at the repo root would not find it. Shallowest wins — that is
    the solution/parent project in every layout that has more than one.

    Marker patterns are fnmatch globs against the basename (`*.csproj`), matched
    against git-tracked files so a build directory full of generated manifests
    never advertises an ecosystem the repo does not actually have.
    """
    best: tuple[int, str] | None = None
    for rel in scannable_files(ctx.workdir):
        name = rel.rsplit("/", 1)[-1]
        if not any(fnmatch.fnmatch(name, pat) for pat in markers):
            continue
        depth = rel.count("/")
        if best is None or depth < best[0]:
            best = (depth, rel)
    if best is None:
        return None
    parent = best[1].rsplit("/", 1)[0] if "/" in best[1] else ""
    return str(Path(ctx.workdir) / parent) if parent else ctx.workdir


def sources(ctx: GateContext, *suffixes: str) -> list[str]:
    """Repo-relative files with one of these suffixes: the change's own files when
    the scope is a change, else the whole tracked tree. Mirrors what the Python
    gates do — score the diff, not the repository's history."""
    changed = [f for f in (ctx.changed_files or []) if f.endswith(suffixes)]
    if changed:
        root = Path(ctx.workdir)
        return [f for f in changed if (root / f).is_file()]
    return [f for f in scannable_files(ctx.workdir) if f.endswith(suffixes)]


def named(ctx: GateContext, *globs: str) -> list[str]:
    """Repo-relative tracked, non-ignored files whose *name* matches one of these
    globs (`*.md`, `Dockerfile`, `requirements*.txt`).

    Whole-tree regardless of scope, unlike `sources`: the gates that want this
    are the ones that used to `rglob` the working directory themselves, and a
    raw rglob walks straight into `dist/`, `site/` and everything else git
    ignores. Tracked-and-not-excluded is the same answer every other gate gets.
    """
    return [
        f
        for f in scannable_files(ctx.workdir)
        if any(fnmatch.fnmatch(f.rsplit("/", 1)[-1], g) for g in globs)
    ]


def tail(text: str, lines: int = 5) -> str:
    return "\n".join((text or "").strip().splitlines()[-lines:])


def merged(out: str | None, err: str | None) -> str:
    """A tool's two streams as one text — several report on either or both."""
    return (out or "") + (err or "")


def nonblank(out: str | None) -> list[str]:
    """A tool's non-blank output lines."""
    return [ln for ln in (out or "").splitlines() if ln.strip()]


def parsed(out: str, empty: str = "{}"):
    """A tool's JSON stdout, or None when it did not emit JSON at all.

    None rather than an empty document, because "the scanner printed something
    we cannot read" is not "the scanner found nothing" — every caller turns it
    into `unavailable`, and an empty document would score as a clean pass.
    """
    try:
        return json.loads(out or empty)
    except json.JSONDecodeError:
        return None


def scored(
    gate: str,
    n: int,
    summary: str,
    findings: list[dict] | None = None,
    *,
    fail: bool,
    cap: int = 10,
) -> GateResult:
    """The tail every counting gate shares: a score that bottoms out at `cap`
    findings, and the caller's own red/amber call."""
    score = max(0.0, 1.0 - min(n, cap) / cap)
    outcome = GateOutcome.FAIL if fail else GateOutcome.WARN
    return GateResult(gate, outcome, score, summary, findings or [])


def counted(
    gate: str,
    n: int,
    label: str,
    findings: list[dict] | None = None,
    *,
    warn_max: int = 3,
    noun: str = "issue(s)",
) -> GateResult:
    """The scoring every counting gate in this repo already uses: clean is a pass,
    a handful is amber, more than that is red, and ten is as bad as it gets."""
    if n <= 0:
        return GateResult(gate, GateOutcome.PASS, 1.0, f"{label}: clean")
    return scored(gate, n, f"{label}: {n} {noun}", findings, fail=n > warn_max)


async def exit_code(
    gate: str,
    argv: list[str],
    cwd: str,
    *,
    ok: str,
    bad: str,
    fail_re: str = "",
) -> GateResult:
    """Run a command whose exit code is the verdict — a build, a test suite.

    `fail_re` counts individual failures in the output so the score reflects one
    broken test rather than a whole red suite; without a match the gate still
    fails, it just cannot say how badly.
    """
    rc, out, err = await run_tool(argv, cwd)
    if (to := timeout_result(gate, rc)) is not None:
        return to
    if rc == 0:
        return GateResult(gate, GateOutcome.PASS, 1.0, ok)
    combined = (out or "") + (err or "")
    n = len(re.findall(fail_re, combined, re.MULTILINE)) if fail_re else 0
    score = max(0.0, 1.0 - min(n, 10) / 10) if n else 0.0
    return GateResult(
        gate,
        GateOutcome.FAIL,
        score,
        f"{bad} — {tail(combined)}",
        [{"output": combined[-1000:]}],
    )


async def _check_one(
    rel: str, argv: list[str], workdir: str, limit: asyncio.Semaphore
) -> tuple[str, int, str]:
    """Run the per-file checker over one file → (path, exit code, output)."""
    async with limit:
        rc, out, err = await run_tool([*argv, rel], workdir)
        return rel, rc, (out or "") + (err or "")


async def per_file(
    gate: str,
    argv: list[str],
    ctx: GateContext,
    suffixes: tuple[str, ...],
    *,
    label: str,
) -> GateResult:
    """A one-file-at-a-time checker (`ruby -c`, `php -l`) run over the scope.

    Blocking gates are built on this, so a tool that did not run has to be told
    apart from a file that did not parse: a timeout is dropped, never counted as
    a syntax error.
    """
    files = sources(ctx, *suffixes)
    if not files:
        return GateResult(gate, GateOutcome.PASS, 1.0, f"{label}: no files in scope")
    capped = files[:MAX_SYNTAX_FILES]
    limit = asyncio.Semaphore(_PARALLEL)
    results = await asyncio.gather(
        *(_check_one(rel, argv, ctx.workdir, limit) for rel in capped)
    )
    broken = [(rel, txt) for rel, rc, txt in results if rc not in (0, _TIMEOUT_RC)]
    scanned = f"{len(capped)} file(s)" + (
        f" (of {len(files)}, capped)" if len(files) > len(capped) else ""
    )
    if not broken:
        return GateResult(gate, GateOutcome.PASS, 1.0, f"{label}: {scanned} parse")
    findings = [
        {"file": rel, "message": tail(txt, 2), "severity": "error"}
        for rel, txt in broken[:20]
    ]
    return GateResult(
        gate,
        GateOutcome.FAIL,
        0.0,
        f"{label}: {len(broken)} file(s) do not parse — {broken[0][0]}",
        findings,
    )


class ToolchainGate:
    """One command, in an ecosystem that may not be present and a toolchain that
    may not be installed.

    Subclasses set `name`, `langs`, `markers`, `binary` and implement `check`.
    Absent ecosystem is a PASS (nothing to say about a language the repo does not
    use); absent toolchain is a WARN (there *was* something to say and we could
    not say it) — the same split rust.py and golang.py make.
    """

    blocking = False
    ecosystem = ""
    markers: tuple[str, ...] = ()
    #: Binary that must exist for `check` to run. Empty when the gate picks its
    #: own tool at runtime (maven vs gradle) and reports the miss itself.
    binary = ""

    async def run(self, ctx: GateContext) -> GateResult:
        root = project_dir(ctx, self.markers)
        if root is None:
            return GateResult(
                self.name,  # type: ignore[attr-defined]
                GateOutcome.PASS,
                1.0,
                f"{self.ecosystem}: not in this tree (no {', '.join(self.markers)})",
            )
        if self.binary and tool_missing(self.binary):
            return unavailable(
                self.name,  # type: ignore[attr-defined]
                f"{self.binary} not installed — skipped",
            )
        return await self.check(ctx, root)

    async def check(self, ctx: GateContext, root: str) -> GateResult:
        raise NotImplementedError

    def missing(self, binary: str) -> GateResult:
        """WARN for a toolchain the gate resolved itself (see `binary`)."""
        return unavailable(
            self.name,  # type: ignore[attr-defined]
            f"{binary} not installed — skipped",
        )
