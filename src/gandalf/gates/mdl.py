"""Markdown lint gate (mdl / markdownlint). Style smell, so capped at WARN.
Self-skips when the repo has no markdown."""

from __future__ import annotations

from pathlib import Path

from gandalf.base import GateContext, GateOutcome, GateResult
from gandalf.plugins import run_tool, timeout_result, missing_result

_SKIP = (".venv", "node_modules", "llama.cpp", ".git", "reports")


class MdlGate:
    name = "mdl"
    blocking = False

    async def run(self, ctx: GateContext) -> GateResult:
        root = Path(ctx.workdir)
        mds = [
            str(p.relative_to(root))
            for p in root.rglob("*.md")
            if not any(s in p.parts for s in _SKIP)
            # Skip hidden/generated artifacts (e.g. .aider.chat.history.md) at any depth.
            and not any(part.startswith(".") for part in p.relative_to(root).parts)
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
