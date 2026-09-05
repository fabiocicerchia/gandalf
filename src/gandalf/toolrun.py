"""Resolving a scanner tool — host binary or gandalf-tools image — and running it.

Every gate that shells out goes through `run_tool`, so the choice between the
host PATH and the container, the per-gate timeout, the kill that actually stops
a `docker run`, and the record of where each tool came from all live here once.
"""

from __future__ import annotations

import asyncio
import contextlib
import contextvars
import itertools
import os
import re
import shutil
import subprocess
import time
from functools import lru_cache
from pathlib import Path

from . import debug

# Bounded so a hung tool degrades to WARN instead of stalling the run.
SUBPROCESS_TIMEOUT_SECONDS = int(os.environ.get("GANDALF_GATE_TIMEOUT", "120"))
_TIMEOUT_RC = -1

# Per-gate timeout override, set by the runner before each gate runs (see
# __main__._run_gates). run_tool reads it so a gate's tool calls honour its
# configured budget without the gate having to thread it through explicitly.
GATE_TIMEOUT: contextvars.ContextVar[int | None] = contextvars.ContextVar("gandalf_gate_timeout", default=None)

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
    r = subprocess.run(  # noqa: S603 — fixed docker argv, never a shell
        ["docker", "image", "inspect", TOOLS_IMAGE],  # noqa: S607 — docker is resolved from PATH on purpose
        capture_output=True,
        check=False,
    )
    return r.returncode == 0


@lru_cache(maxsize=1)
def tools_image_id() -> str:
    """The built image's content id, or "".

    The image tag is a moving target — `make tools` rebuilds `gandalf-tools:latest`
    from whatever the upstream package indexes serve that day. The id is what
    actually distinguishes one build from another, so it is the thing a report
    has to carry if "it passes on my machine" is ever going to be answerable.
    """
    if not _tools_image_available():
        return ""
    r = subprocess.run(  # nosec B603 B607 - fixed docker argv, no shell  # noqa: S603 — fixed argv, never a shell
        ["docker", "image", "inspect", "-f", "{{.Id}}", TOOLS_IMAGE],  # noqa: S607 — resolved from PATH on purpose: the tool may be a host binary or a shim
        capture_output=True,
        text=True,
        check=False,
    )
    return r.stdout.strip() if r.returncode == 0 else ""


def _via_image(binary: str) -> bool:
    """Whether a tool would run out of the image rather than off the host PATH."""
    return binary in IMAGE_TOOLS and _tools_image_available()


# binary → "host" | "image", for every tool a gate actually invoked this run.
# Two machines that resolve the same gate differently produce different findings
# and no way to tell why; recorded here so the report can simply say which.
_TOOL_SOURCE: dict[str, str] = {}


def _record_tool(binary: str, source: str) -> None:
    """First resolution wins — a tool resolves the same way all run long."""
    _TOOL_SOURCE.setdefault(binary, source)


def tool_sources() -> dict[str, str]:
    """binary → where it ran, for the tools invoked through `run_tool` this run.

    Gates that build their own `docker run` argv (kics, codeql) name their image
    in their own summary and are not in here.
    """
    return dict(_TOOL_SOURCE)


def reset_tool_sources() -> None:
    """Clear the record. Process state, so a second run in one process (the
    editor extension, the tests) must not inherit the first run's resolutions."""
    _TOOL_SOURCE.clear()


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
    if shutil.which(cmd[0]):
        _record_tool(cmd[0], "host")
        return cmd
    if not _via_image(cmd[0]):
        return cmd
    _record_tool(cmd[0], "image")
    return [
        "docker",
        "run",
        "--rm",
        *(["--name", name] if name else []),
        "--network",
        "host",
        "-v",
        f"{Path(workdir).resolve()}:/src",
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
    except (TimeoutError, OSError) as exc:  # best effort; already degrading
        debug.log(f"could not kill container {name}: {exc}")


async def communicate(
    proc: asyncio.subprocess.Process,
    timeout: float,  # noqa: ASYNC109 — the timeout is plumbed to asyncio.wait_for, which is the mechanism this rule asks for
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
    except TimeoutError:
        await _reap(proc, cmd or [""], container)
        return None


async def run_tool(cmd: list[str], cwd: str, timeout: int | None = None) -> tuple[int, str, str]:  # noqa: ASYNC109 — the timeout is plumbed to asyncio.wait_for, which is the mechanism this rule asks for
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
    except TimeoutError:
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

# First line of `<tool> --version` is the version for nearly every scanner here;
# the ones that disagree get "unknown" rather than a guess, which is still enough
# to answer "did these two machines run the same thing?" (they did not).
_VERSION_TIMEOUT = 30


async def tool_version(binary: str, workdir: str) -> str:
    """`<binary> --version`, routed the same way the gate's own calls were.

    Through `run_tool`, so an image-resolved tool is asked inside the image — the
    host may not even have the binary, and if it does, its version is not the one
    that produced the findings.
    """
    rc, out, err = await run_tool([binary, "--version"], workdir, _VERSION_TIMEOUT)
    text = (out or "").strip() or (err or "").strip()
    if rc != 0 or not text:
        return "unknown"
    return text.splitlines()[0].strip()[:120]


async def tool_versions(workdir: str) -> dict[str, str]:
    """Version of every tool that ran this run, probed concurrently."""
    names = sorted(_TOOL_SOURCE)
    if not names:
        return {}
    got = await asyncio.gather(*(tool_version(n, workdir) for n in names))
    return dict(zip(names, got, strict=False))
