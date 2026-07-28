"""Plugin discovery + shared subprocess helpers for gates.

A gate is any class exposing `name`, `blocking`, and `async run(ctx)`. Drop a
`.py` file exporting such a class into gandalf/gates/ (or any dir on
GANDALF_GATES_PATH) and it's picked up — no registry to edit. That's the whole
extension mechanism.
"""

from __future__ import annotations

import asyncio
import contextvars
import importlib.util
import inspect
import os
import re
import shutil
import subprocess
import time
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
    if not shutil.which("docker"):
        return False
    r = subprocess.run(  # nosec B603 B607 - fixed docker argv, no shell
        ["docker", "image", "inspect", TOOLS_IMAGE], capture_output=True, check=False
    )
    return r.returncode == 0


def _via_image(binary: str) -> bool:
    return binary in IMAGE_TOOLS and _tools_image_available()


def tool_missing(binary: str) -> bool:
    """A gate tool is 'missing' only if it's neither on the host PATH nor provided
    by the gandalf-tools image — then the gate degrades to WARN."""
    return not shutil.which(binary) and not _via_image(binary)


def _dockerize(cmd: list[str], workdir: str) -> list[str]:
    """Prefer the host binary; else, if the image provides this tool, run it in a
    throwaway container mounting the worktree at /src. A named cache volume keeps
    tool DBs (trivy, semgrep rules) off the host and warm across runs. --network
    host so tools can fetch rule/vuln DBs and reach local targets."""
    if shutil.which(cmd[0]) or not _via_image(cmd[0]):
        return cmd
    return [
        "docker",
        "run",
        "--rm",
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


# Every tree-scanning gate (trivy/checkov/kics/…) skips these by default: build,
# vendor and report noise that isn't the repo's own source. This keeps the tool
# generic — it's used against many repos, so nothing repo-specific is hardcoded.
_DEFAULT_IGNORES = ("reports", "node_modules", "llama.cpp", ".venv", ".git")


@lru_cache(maxsize=8)
def ignore_patterns(workdir: str) -> tuple[str, ...]:
    """Paths tree-scanning gates should skip: the built-in defaults plus any lines
    from a repo-root ``.gandalfignore`` (one glob per line; blank lines and lines
    starting with ``#`` ignored). Deduped, order preserved. Each gate translates
    these into its own tool's exclude flag, so a dir name (``data``) or a file
    (``.env``) both work — the place to ignore a repo's local secrets/state."""
    pats = list(_DEFAULT_IGNORES)
    f = Path(workdir) / ".gandalfignore"
    if f.is_file():
        for line in f.read_text(errors="replace").splitlines():
            s = line.strip()
            if s and not s.startswith("#"):
                pats.append(s)
    return tuple(dict.fromkeys(pats))  # de-dup, order preserved


def _scan_targets(ctx: GateContext, *, py_only: bool = False) -> list[str]:
    """Files to scan: the change's own files (bounded runtime, scoring reflects
    the diff not pre-existing repo issues), falling back to the git-tracked tree
    when the changed set is empty. Deletions/non-existent paths are dropped.

    Whole-tree mode scans tracked files rather than '.', so an untracked/vendored
    subtree never enters the scan. Only when the workdir isn't a git repo (no
    tracked files) does it fall back to '.'."""
    root = Path(ctx.workdir)
    targets = []
    for rel in ctx.changed_files or []:
        if py_only and not rel.endswith(".py"):
            continue
        if (root / rel).is_file():
            targets.append(rel)
    if targets:
        return targets
    tracked = tracked_files(ctx.workdir)
    if py_only:
        tracked = tuple(p for p in tracked if p.endswith(".py"))
    return list(tracked) or ["."]


async def run_tool(
    cmd: list[str], cwd: str, timeout: int | None = None
) -> tuple[int, str, str]:
    """Run an external gate tool. On timeout the process is killed and _TIMEOUT_RC
    is returned so the gate degrades to WARN rather than hanging. With no explicit
    timeout, the per-gate budget (GATE_TIMEOUT contextvar) is used, else the
    global default."""
    if timeout is None:
        timeout = GATE_TIMEOUT.get() or SUBPROCESS_TIMEOUT_SECONDS
    cmd = _dockerize(cmd, cwd)
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
        proc.kill()
        await proc.wait()
        debug.log(f"timeout after {timeout}s: {cmd[0]}")
        return _TIMEOUT_RC, "", f"timed out after {timeout}s"
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
    dirs = [Path(__file__).parent / "gates"]
    for extra in filter(
        None, os.environ.get("GANDALF_GATES_PATH", "").split(os.pathsep)
    ):
        dirs.append(Path(extra))
    return [d for d in dirs if d.is_dir()]


def _load_module(path: Path):
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
