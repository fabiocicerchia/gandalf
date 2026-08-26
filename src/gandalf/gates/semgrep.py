"""Semgrep SAST gate. Ported from ai-harness SemgrepGate."""

from __future__ import annotations

import json

from gandalf.base import GateContext, GateOutcome, GateResult
from gandalf.plugins import _scan_targets, missing_result, run_tool, timeout_result


def _flat(f: dict) -> dict:
    return {
        "path": f.get("path", ""),
        "line": f.get("start", {}).get("line", ""),
        "check_id": f.get("check_id", ""),
        "message": f.get("extra", {}).get("message", "") or f.get("check_id", ""),
    }


def _autofix(f: dict) -> dict:
    """The rule's own autofix, kept whole when it has one.

    A rule that ships `extra.fix` knows the exact replacement text, and that is
    what becomes a one-click suggestion on the pull request (see suggest.py) —
    so for those findings the position keys travel with the flattened finding
    instead of being flattened away.
    """
    if not (f.get("extra") or {}).get("fix"):
        return {}
    return {
        "start": f.get("start") or {},
        "end": f.get("end") or {},
        "extra": {"fix": f["extra"]["fix"]},
    }


class SemgrepGate:
    name = "semgrep"
    blocking = False

    async def run(self, ctx: GateContext) -> GateResult:
        if (m := missing_result(self.name, "semgrep")) is not None:
            return m
        rc, out, _ = await run_tool(
            [
                "semgrep",
                "scan",
                "--json",
                "--quiet",
                "--config",
                "p/python",
                "--config",
                "p/golang",
                "--config",
                "p/javascript",
                "--config",
                "p/typescript",
                "--config",
                "p/owasp-top-ten",
                "--config",
                "p/secrets",
                "--exclude",
                "reports",
                "--exclude",
                ".venv",
                "--exclude",
                "node_modules",
                "--exclude",
                "llama.cpp",
                *_scan_targets(ctx),
            ],
            ctx.workdir,
        )
        if (to := timeout_result(self.name, rc)) is not None:
            return to
        try:
            data = json.loads(out or "{}")
        except json.JSONDecodeError:
            return GateResult(
                self.name, GateOutcome.WARN, 0.8, "semgrep: unparsable output"
            )
        findings = data.get("results", [])
        errors = data.get("errors", [])
        n = len(findings)
        if errors and n == 0:
            return GateResult(
                self.name,
                GateOutcome.WARN,
                0.8,
                f"semgrep: {len(errors)} rule error(s), no findings",
            )
        if n == 0:
            return GateResult(self.name, GateOutcome.PASS, 1.0, "semgrep: clean")
        severities = [f.get("extra", {}).get("severity", "WARNING") for f in findings]
        has_error = any(s == "ERROR" for s in severities)
        score = max(0.0, 1.0 - min(n, 10) / 10)
        outcome = GateOutcome.FAIL if has_error or n > 5 else GateOutcome.WARN
        # semgrep nests message/rule under extra + check_id; flatten to the keys
        # report.fmt_finding reads, so the report shows the actual issue not just a path.
        flat = [{**_flat(f), **_autofix(f)} for f in findings]
        return GateResult(self.name, outcome, score, f"semgrep: {n} finding(s)", flat)
