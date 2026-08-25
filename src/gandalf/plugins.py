"""Plugin discovery + shared subprocess helpers for gates.

A gate is any class exposing `name`, `blocking`, and `async run(ctx)`. Drop a
`.py` file exporting such a class into gandalf/gates/ (or any dir on
GANDALF_GATES_PATH) and it's picked up — no registry to edit. That's the whole
extension mechanism.
"""

from __future__ import annotations

import asyncio
import contextlib
import contextvars
import itertools
import importlib.util
import inspect
import os
import re
import shutil
import subprocess
import time
from fnmatch import translate
from functools import lru_cache
from pathlib import Path

from . import debug
from .base import Gate, GateContext, GateOutcome, GateResult

# Bounded so a hung tool degrades to WARN instead of stalling the run.
SUBPROCESS_TIMEOUT_SECONDS = int(os.environ.get("GANDALF_GATE_TIMEOUT", "120"))
_TIMEOUT_RC = -1

# Per-gate timeout override, set by the runner before each gate runs (see
# __main__._run_gates). run_tool reads it so a gate's tool calls honour its
# configured budget without the gate having to thread it through explicitly.
GATE_TIMEOUT: contextvars.ContextVar[int | None] = contextvars.ContextVar(
    "gandalf_gate_timeout", default=None
)

# Scanner tools run inside this image when not present on the host PATH, so the
# host stays clean. Build it with `make tools` (gandalf/tools.Dockerfile).
TOOLS_IMAGE = os.environ.get("GANDALF_TOOLS_IMAGE", "gandalf-tools")

# The tools gandalf/tools.Dockerfile actually installs. A gate only falls back to
# the container for a tool in this set; language toolchains (go, node, npm and the
# linters that need them) stay host-only, since you already have them installed.
IMAGE_TOOLS = frozenset(
    {
        "ruff",
        "semgrep",
        "bandit",
        "pip-audit",
        "osv-scanner",
        "trivy",
        "gitleaks",
        "checkov",
        "hadolint",
        "mypy",
        "vulture",
        "codespell",
        "yamllint",
        "shellcheck",
        "actionlint",
        "mdl",
        "sqlfluff",
        "squawk",
        "interrogate",
        "lizard",
        "scorecard",
    }
)


@lru_cache(maxsize=1)
def _tools_image_available() -> bool:
    """Whether the scanner-tools image is built and present locally.

    Checked, never pulled: a quality gate must not reach the network on its own
    initiative, and `make tools` is the explicit step that builds it.
    """
    if not shutil.which("docker"):
        return False
    r = subprocess.run(  # nosec B603 B607 - fixed docker argv, no shell
        ["docker", "image", "inspect", TOOLS_IMAGE], capture_output=True, check=False
    )
    return r.returncode == 0


def _via_image(binary: str) -> bool:
    """Whether a tool would run out of the image rather than off the host PATH."""
    return binary in IMAGE_TOOLS and _tools_image_available()


def tool_missing(binary: str) -> bool:
    """A gate tool is 'missing' only if it's neither on the host PATH nor provided
    by the gandalf-tools image — then the gate degrades to WARN."""
    return not shutil.which(binary) and not _via_image(binary)


def _dockerize(cmd: list[str], workdir: str, name: str = "") -> list[str]:
    """Prefer the host binary; else, if the image provides this tool, run it in a
    throwaway container mounting the worktree at /src. A named cache volume keeps
    tool DBs (trivy, semgrep rules) off the host and warm across runs. --network
    host so tools can fetch rule/vuln DBs and reach local targets.

    `name` is what makes the container killable on timeout — without it there is
    no handle to stop, only the client process, and stopping that stops nothing.
    """
    if shutil.which(cmd[0]) or not _via_image(cmd[0]):
        return cmd
    return [
        "docker",
        "run",
        "--rm",
        *(["--name", name] if name else []),
        "--network",
        "host",
        "-v",
        f"{os.path.abspath(workdir)}:/src",
        # Cache path matches the image's non-root user HOME (tools.Dockerfile).
        # New volume name so it's created fresh with gandalf ownership rather than
        # inheriting the old root-owned gandalf-cache volume.
        "-v",
        "gandalf-tools-cache:/home/gandalf/.cache",
        "-w",
        "/src",
        TOOLS_IMAGE,
        *cmd,
    ]


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

    def alternation(pats):
        return (
            re.compile("|".join(f"(?:{translate(g)})" for g in pats)) if pats else None
        )

    # A glob is tried against the whole path as well, because fnmatch's `*`
    # spans separators — `*.min.js` is expected to match `web/app.min.js`.
    return (
        names,
        tuple(prefixes),
        alternation(segment_globs),
        alternation(path_globs + segment_globs),
    )


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
    if any(p == pre or p.startswith(pre + "/") for pre in prefixes):
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
    root = Path(ctx.workdir)
    pats = ignore_patterns(ctx.workdir)
    targets = []
    for rel in ctx.changed_files or []:
        if py_only and not rel.endswith(".py"):
            continue
        if is_ignored(rel, pats):
            continue
        if (root / rel).is_file():
            targets.append(rel)
    if targets:
        return targets
    tracked = scannable_files(ctx.workdir)
    if py_only:
        tracked = tuple(p for p in tracked if p.endswith(".py"))
    return list(tracked) or ["."]


_CONTAINER_SEQ = itertools.count()


async def _reap(proc: asyncio.subprocess.Process, cmd: list[str], name: str) -> None:
    """Stop a timed-out/cancelled tool, including the container it may be inside.

    `proc.kill()` on a `docker run` kills the *client*: the container keeps
    running, keeps its CPU, and `--rm` never fires, because that only removes a
    container that exited on its own. semgrep and trivy are the ones you notice
    — a scan that "timed out" ten minutes ago is still pegging a core, and the
    next run starts a second one beside it.
    """
    with contextlib.suppress(ProcessLookupError):
        proc.kill()
    await proc.wait()
    if cmd[0] != "docker" or not name:
        return
    try:
        killer = await asyncio.create_subprocess_exec(
            "docker",
            "kill",
            name,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await asyncio.wait_for(killer.communicate(), timeout=15)
    except (OSError, asyncio.TimeoutError) as exc:  # best effort; already degrading
        debug.log(f"could not kill container {name}: {exc}")


async def communicate(
    proc: asyncio.subprocess.Process,
    timeout: float,
    cmd: list[str] | None = None,
    container: str = "",
) -> tuple[bytes, bytes] | None:
    """`proc.communicate()` with the child actually killed on timeout, or None.

    `asyncio.wait_for` cancels the *await*, not the process. Without the kill a
    timed-out gate reports its timeout and leaves the tool running: a fuzzer
    burning a core for the rest of the session, an `act` run still spawning
    containers. Gates that build their own Process (different stream wiring than
    run_tool's) must reap it through here.

    Pass `cmd`/`container` when the process is a `docker run` — killing that
    client does not stop the container behind it.
    """
    try:
        return await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        await _reap(proc, cmd or [""], container)
        return None


async def run_tool(
    cmd: list[str], cwd: str, timeout: int | None = None
) -> tuple[int, str, str]:
    """Run an external gate tool. On timeout the process is killed and _TIMEOUT_RC
    is returned so the gate degrades to WARN rather than hanging. With no explicit
    timeout, the per-gate budget (GATE_TIMEOUT contextvar) is used, else the
    global default."""
    if timeout is None:
        timeout = GATE_TIMEOUT.get() or SUBPROCESS_TIMEOUT_SECONDS
    container = f"gandalf-{os.getpid()}-{next(_CONTAINER_SEQ)}"
    cmd = _dockerize(cmd, cwd, container)
    debug.log(f"run (timeout={timeout}s): {' '.join(cmd)}")
    t0 = time.monotonic()
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        await _reap(proc, cmd, container)
        debug.log(f"timeout after {timeout}s: {cmd[0]}")
        return _TIMEOUT_RC, "", f"timed out after {timeout}s"
    except asyncio.CancelledError:
        # Ctrl-C, or the editor's cancel button: same leak, same cleanup.
        await _reap(proc, cmd, container)
        raise
    rc = proc.returncode if proc.returncode is not None else _TIMEOUT_RC
    debug.log(f"done rc={rc} in {time.monotonic() - t0:.2f}s: {cmd[0]}")
    errs = err.decode(errors="replace")
    # A dockerized tool that isn't actually in the image (or a missing image) must
    # NOT be read as a clean run — its empty stdout would parse as "no findings".
    if rc and _DOCKER_UNAVAILABLE.search(errs):
        return _TIMEOUT_RC, "", errs
    return rc, out.decode(errors="replace"), errs


_DOCKER_UNAVAILABLE = re.compile(
    r"executable file not found|Unable to find image|No such image|"
    r"failed to create task for container",
    re.IGNORECASE,
)


def timeout_result(name: str, rc: int) -> GateResult | None:
    """WARN sentinel: the tool did not actually run (timeout, or a dockerized tool
    missing from the image). Never let that masquerade as a clean pass."""
    if rc == _TIMEOUT_RC:
        return GateResult(
            name,
            GateOutcome.WARN,
            0.8,
            f"{name}: did not run (timeout or tool unavailable) — skipped",
        )
    return None


def missing_result(
    name: str, binary: str, *, tool: str | None = None
) -> GateResult | None:
    """WARN sentinel for a gate whose `binary` is neither on PATH nor in the tools
    image, else None so the gate proceeds. Mirrors timeout_result's idiom. `tool`
    overrides the name shown in the message (e.g. the licenses gate runs trivy)."""
    if not tool_missing(binary):
        return None
    return GateResult(
        name,
        GateOutcome.WARN,
        0.8,
        f"{tool or binary} unavailable (no host binary or gandalf-tools image) — skipped",
    )


def _gate_dirs() -> list[Path]:
    """Every directory gates are discovered from.

    The built-in directory first, then anything on GANDALF_GATES_PATH — which
    is how a project adds its own gate without vendoring gandalf.
    """
    dirs = [Path(__file__).parent / "gates"]
    for extra in filter(
        None, os.environ.get("GANDALF_GATES_PATH", "").split(os.pathsep)
    ):
        dirs.append(Path(extra))
    return [d for d in dirs if d.is_dir()]


def _load_module(path: Path):
    """Import one gate file by path, under a namespaced module name.

    Namespaced so two gate directories can hold files with the same basename
    without the second silently shadowing the first.
    """
    spec = importlib.util.spec_from_file_location(f"gandalf_gate_{path.stem}", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load gate module from {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def discover_gates() -> list[Gate]:
    """Instantiate every Gate-shaped class found in the plugin dirs."""
    gates: dict[str, Gate] = {}
    for d in _gate_dirs():
        for path in sorted(d.glob("*.py")):
            if path.name.startswith("_"):
                continue
            mod = _load_module(path)
            for _, obj in inspect.getmembers(mod, inspect.isclass):
                if obj.__module__ != mod.__name__:
                    continue  # skip imported symbols (GateResult, etc.)
                if not (
                    hasattr(obj, "name")
                    and hasattr(obj, "blocking")
                    and hasattr(obj, "run")
                ):
                    continue
                inst = obj()
                if isinstance(inst, Gate):
                    gates[inst.name] = (
                        inst  # name wins on collision → override built-ins
                    )
    return list(gates.values())
