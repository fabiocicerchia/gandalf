"""Local GitHub Actions runner gate — runs .github/workflows/* via `act` in Docker.
Ported from ai-harness; ai-harness settings replaced with env vars.

  no workflows        -> PASS
  act/Docker missing  -> WARN (can't verify, don't block)
  act passes / fails  -> PASS / FAIL

Disable with GANDALF_ACT=0. Event via GANDALF_ACT_EVENT (default pull_request),
timeout via GANDALF_ACT_TIMEOUT (default 900s), runner image via GANDALF_ACT_PLATFORM.
"""

from __future__ import annotations

import asyncio
import os
import shutil
from pathlib import Path

from gandalf.base import GateContext, GateOutcome, GateResult
from gandalf.plugins import communicate

_EVENT = os.environ.get("GANDALF_ACT_EVENT", "pull_request")
_PLATFORM = os.environ.get(
    "GANDALF_ACT_PLATFORM", "ubuntu-latest=catthehacker/ubuntu:act-latest"
)
_TIMEOUT = int(os.environ.get("GANDALF_ACT_TIMEOUT", "900"))
_BINARY = os.environ.get("GANDALF_ACT_BINARY", "act")


class ActGate:
    name = "ci_act"
    blocking = False

    async def run(self, ctx: GateContext) -> GateResult:
        if os.environ.get("GANDALF_ACT", "1") == "0":
            return GateResult(
                self.name, GateOutcome.PASS, 1.0, "act gate disabled (GANDALF_ACT=0)"
            )
        wf_dir = Path(ctx.workdir) / ".github" / "workflows"
        workflows = (
            (list(wf_dir.glob("*.yml")) + list(wf_dir.glob("*.yaml")))
            if wf_dir.is_dir()
            else []
        )
        if not workflows:
            return GateResult(self.name, GateOutcome.PASS, 1.0, "no workflows to run")
        if shutil.which(_BINARY) is None:
            return GateResult(
                self.name,
                GateOutcome.WARN,
                0.5,
                f"'{_BINARY}' not found; CI not verified locally",
            )
        if shutil.which("docker") is None:
            return GateResult(
                self.name,
                GateOutcome.WARN,
                0.5,
                "Docker not available; act cannot run; CI not verified locally",
            )
        cmd = [_BINARY, _EVENT, "--platform", _PLATFORM]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=ctx.workdir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            streams = await communicate(proc, _TIMEOUT)
            if streams is None:
                return GateResult(
                    self.name, GateOutcome.FAIL, 0.0, f"act timed out after {_TIMEOUT}s"
                )
            out_b, _ = streams
        except Exception as exc:  # noqa: BLE001
            return GateResult(
                self.name, GateOutcome.WARN, 0.5, f"act failed to launch: {exc}"
            )
        out = (out_b or b"").decode(errors="replace")
        tail = "\n".join(out.strip().splitlines()[-8:])
        if proc.returncode == 0:
            return GateResult(
                self.name,
                GateOutcome.PASS,
                1.0,
                f"act: {len(workflows)} workflow(s) passed locally",
                [{"log_tail": tail}],
            )
        return GateResult(
            self.name,
            GateOutcome.FAIL,
            0.0,
            f"act: workflow(s) failed locally (exit {proc.returncode})",
            [{"log_tail": tail}],
        )
