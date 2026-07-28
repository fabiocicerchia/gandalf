"""Secret-scan gate (gitleaks). Blocking — a leaked secret is a hard stop.
Ported from ai-harness GitleaksGate.
"""

from __future__ import annotations

import json

from gandalf.base import GateContext, GateOutcome, GateResult
from gandalf.plugins import missing_result, run_tool, timeout_result


class GitleaksGate:
    name = "gitleaks"
    blocking = True

    async def run(self, ctx: GateContext) -> GateResult:
        if (m := missing_result(self.name, "gitleaks")) is not None:
            return m
        rc, out, _ = await run_tool(
            [
                "gitleaks",
                "detect",
                "--no-banner",
                "--redact",
                "--report-format",
                "json",
                "--report-path",
                "/dev/stdout",
                "--source",
                ".",
            ],
            ctx.workdir,
        )
        if (to := timeout_result(self.name, rc)) is not None:
            return to
        try:
            findings = json.loads(out or "[]") if out.strip().startswith("[") else []
        except json.JSONDecodeError:
            findings = []
        n = len(findings)
        if n == 0:
            return GateResult(
                self.name, GateOutcome.PASS, 1.0, "gitleaks: no secrets found"
            )
        return GateResult(
            self.name,
            GateOutcome.FAIL,
            0.0,
            f"gitleaks: {n} potential secret(s) detected",
            findings,
        )
