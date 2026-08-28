"""Markdown lint gate (mdl / markdownlint). Style smell, so capped at WARN.
Self-skips when the repo has no markdown."""

from __future__ import annotations

from gandalf.base import GateContext, GateOutcome, GateResult
from gandalf.gates._toolchain import named
from gandalf.plugins import missing_result, run_tool, timeout_result


class MdlGate:
    name = "mdl"
    blocking = False

    async def run(self, ctx: GateContext) -> GateResult:
        mds = [
            f
            for f in named(ctx, "*.md")
            # Skip hidden/generated artifacts (e.g. .aider.chat.history.md) at any depth.
            if not any(part.startswith(".") for part in f.split("/"))
        ]
        if not mds:
            return GateResult(
                self.name, GateOutcome.PASS, 1.0, "mdl: no markdown files"
            )
        if (m := missing_result(self.name, "mdl")) is not None:
            return m
        rc, out, _ = await run_tool(["mdl", *mds], ctx.workdir)
        if (to := timeout_result(self.name, rc)) is not None:
            return to
        issues = [ln for ln in (out or "").splitlines() if ": MD" in ln]
        n = len(issues)
        if n == 0:
            return GateResult(
                self.name, GateOutcome.PASS, 1.0, f"mdl: {len(mds)} file(s) clean"
            )
        score = max(0.0, 1.0 - min(n, 20) / 20)
        # Markdown style is cosmetic — cap at WARN.
        return GateResult(
            self.name,
            GateOutcome.WARN,
            score,
            f"mdl: {n} issue(s)",
            [{"issue": i} for i in issues],
        )
