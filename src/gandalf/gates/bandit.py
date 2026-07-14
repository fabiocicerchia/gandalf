"""Bandit SAST gate. Ported from ai-harness BanditGate."""

from __future__ import annotations

import json

from gandalf.base import GateContext, GateOutcome, GateResult
from gandalf.plugins import run_tool, timeout_result, _scan_targets, missing_result


class BanditGate:
    name = "bandit"
    blocking = False
    langs = frozenset({"python"})

    async def run(self, ctx: GateContext) -> GateResult:
        if (m := missing_result(self.name, "bandit")) is not None:
            return m
        rc, out, _ = await run_tool(
            [
                "bandit",
                "-r",
                *_scan_targets(ctx, py_only=True),
                "-f",
                "json",
                "-q",
                # B101 (assert) is test noise; B404 (subprocess import) is informational.
                "-s",
                "B101,B404",
                "--exclude",
                ".venv,node_modules,reports,llama.cpp",
            ],
            ctx.workdir,
        )
        if (to := timeout_result(self.name, rc)) is not None:
            return to
        try:
            data = json.loads(out or "{}")
        except json.JSONDecodeError:
            return GateResult(
                self.name, GateOutcome.WARN, 0.8, "bandit: unparsable output"
            )
        results = data.get("results", [])
        n = len(results)
        if n == 0:
            return GateResult(self.name, GateOutcome.PASS, 1.0, "bandit: clean")
        high = sum(1 for r in results if r.get("issue_severity") == "HIGH")
        score = max(0.0, 1.0 - (high * 0.2 + (n - high) * 0.05))
        outcome = GateOutcome.FAIL if high > 0 else GateOutcome.WARN
        return GateResult(
            self.name, outcome, score, f"bandit: {n} issue(s), {high} HIGH", results
        )
