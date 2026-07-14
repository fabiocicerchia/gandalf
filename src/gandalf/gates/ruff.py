"""Ruff lint gate. Ported from ai-harness RuffGate."""

from __future__ import annotations

import json
import re

from gandalf.base import GateContext, GateOutcome, GateResult
from gandalf.plugins import run_tool, timeout_result, tool_missing, _scan_targets, missing_result


class RuffGate:
    name = "ruff"
    blocking = False
    langs = frozenset({"python"})

    async def run(self, ctx: GateContext) -> GateResult:
        if (m := missing_result(self.name, "ruff")) is not None:
            return m
        rc, out, _ = await run_tool(
            [
                "ruff",
                "check",
                "--no-cache",  # don't drop a (root-owned) .ruff_cache into the scanned repo
                "--output-format",
                "json",
                *_scan_targets(ctx, py_only=True),
            ],
            ctx.workdir,
        )
        if (to := timeout_result(self.name, rc)) is not None:
            return to
        try:
            findings = json.loads(out or "[]")
        except json.JSONDecodeError:
            findings = []
        n = len(findings)
        if n == 0:
            return GateResult(self.name, GateOutcome.PASS, 1.0, "ruff clean")
        score = max(0.0, 1.0 - min(n, 10) / 10)
        outcome = GateOutcome.WARN if n <= 3 else GateOutcome.FAIL
        return GateResult(self.name, outcome, score, f"ruff: {n} finding(s)", findings)

    async def fix(self, ctx: GateContext) -> tuple[bool, str]:
        """Apply ruff's autofixes in place (--fix). Called only under `--fix`."""
        if tool_missing("ruff"):
            return (False, "ruff unavailable — nothing fixed")
        rc, out, err = await run_tool(
            [
                "ruff",
                "check",
                "--fix",
                "--no-cache",
                *_scan_targets(ctx, py_only=True),
            ],
            ctx.workdir,
        )
        # ruff reports "Found N errors (M fixed, K remaining)." on stderr.
        m = re.search(r"\((\d+) fixed", out + err)
        fixed = int(m.group(1)) if m else 0
        return (fixed > 0, f"ruff: {fixed} finding(s) autofixed")
