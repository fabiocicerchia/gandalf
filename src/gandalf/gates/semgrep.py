"""Semgrep SAST gate. Ported from ai-harness SemgrepGate."""

from __future__ import annotations

from gandalf.base import GateContext, GateOutcome, GateResult
from gandalf.gates._toolchain import parsed, scored
from gandalf.plugins import (
    _scan_targets,
    missing_result,
    run_tool,
    timeout_result,
    unavailable,
)

# More than a handful of findings fails, regardless of severity.
MAX_FINDINGS = 5


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


def _has_error(findings: list) -> bool:
    """Whether any finding is semgrep's ERROR severity, which makes the gate red."""
    return any(f.get("extra", {}).get("severity", "WARNING") == "ERROR" for f in findings)


def _flatten(findings: list) -> list[dict]:
    """semgrep nests message/rule under extra + check_id; flatten to the keys
    report.fmt_finding reads, so the report shows the actual issue not just a path."""
    return [{**_flat(f), **_autofix(f)} for f in findings]


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
        data = parsed(out)
        if data is None:
            return unavailable(self.name, "semgrep: unparsable output")
        findings = data.get("results", [])
        errors = data.get("errors", [])
        n = len(findings)
        if errors and n == 0:
            return unavailable(self.name, f"semgrep: {len(errors)} rule error(s), no findings")
        if n == 0:
            return GateResult(self.name, GateOutcome.PASS, 1.0, "semgrep: clean")
        return scored(
            self.name,
            n,
            f"semgrep: {n} finding(s)",
            _flatten(findings),
            fail=_has_error(findings) or n > MAX_FINDINGS,
        )
