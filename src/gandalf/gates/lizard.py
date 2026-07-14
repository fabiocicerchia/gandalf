"""Cyclomatic-complexity gate (lizard, polyglot). Flags functions that exceed
the complexity / length thresholds. Advisory, so capped at WARN."""

from __future__ import annotations

from gandalf.base import GateContext, GateOutcome, GateResult
from gandalf.plugins import run_tool, timeout_result, _scan_targets, missing_result


class LizardGate:
    name = "lizard"
    blocking = False
    langs = frozenset({"python", "go", "node", "ts"})
    category = "Complexity"

    async def run(self, ctx: GateContext) -> GateResult:
        if (m := missing_result(self.name, "lizard")) is not None:
            return m
        rc, out, _ = await run_tool(
            [
                "lizard",
                "--warnings_only",
                "-x",
                "*/.venv/*",
                "-x",
                "*/node_modules/*",
                "-x",
                "*/llama.cpp/*",
                *_scan_targets(ctx),
            ],
            ctx.workdir,
        )
        if (to := timeout_result(self.name, rc)) is not None:
            return to
        warnings = [ln for ln in (out or "").splitlines() if ": warning:" in ln]
        n = len(warnings)
        if n == 0:
            return GateResult(
                self.name, GateOutcome.PASS, 1.0, "lizard: no over-complex functions"
            )
        score = max(0.0, 1.0 - min(n, 20) / 20)
        return GateResult(
            self.name,
            GateOutcome.WARN,
            score,
            f"lizard: {n} function(s) over complexity threshold",
            [{"finding": w.strip()} for w in warnings],
        )
