"""Docstring-coverage gate (interrogate, Python). WARNs below the threshold set
by GANDALF_DOCSTRING_MIN (default 60%). Self-skips without Python files."""

from __future__ import annotations

import os
import re

from gandalf.base import GateContext, GateOutcome, GateResult
from gandalf.plugins import _scan_targets, missing_result, run_tool, timeout_result

_MIN = float(os.environ.get("GANDALF_DOCSTRING_MIN", "60"))


class InterrogateGate:
    name = "interrogate"
    blocking = False
    langs = frozenset({"python"})
    category = "Documentation"

    async def run(self, ctx: GateContext) -> GateResult:
        targets = _scan_targets(ctx, py_only=True)
        if (m := missing_result(self.name, "interrogate")) is not None:
            return m
        rc, out, err = await run_tool(
            [
                "interrogate",
                *targets,
                "--fail-under",
                str(_MIN),
                "-e",
                ".venv",
                "-e",
                "node_modules",
                "-e",
                "llama.cpp",
                "-e",
                "reports",
            ],
            ctx.workdir,
        )
        if (to := timeout_result(self.name, rc)) is not None:
            return to
        match = re.search(r"actual:\s*([\d.]+)%", (out or "") + (err or ""))
        if not match:
            return GateResult(
                self.name, GateOutcome.PASS, 1.0, "interrogate: no Python to document"
            )
        actual = float(match.group(1))
        score = actual / 100
        if actual >= _MIN:
            return GateResult(
                self.name,
                GateOutcome.PASS,
                score,
                f"docstring coverage {actual:.0f}% (>= {_MIN:.0f}%)",
            )
        return GateResult(
            self.name,
            GateOutcome.WARN,
            score,
            f"docstring coverage {actual:.0f}% (< {_MIN:.0f}%)",
        )
