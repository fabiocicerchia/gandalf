"""Dependency-license gate — flags forbidden / restricted licenses via trivy's
license scanner (reuses the trivy binary already in the image). Permissive
licenses (LOW/UNKNOWN severity) are ignored so only real obligations surface."""

from __future__ import annotations

import json

from gandalf.base import GateContext, GateOutcome, GateResult
from gandalf.plugins import missing_result, run_tool, timeout_result


class LicensesGate:
    name = "licenses"
    blocking = False
    category = "Licensing"

    async def run(self, ctx: GateContext) -> GateResult:
        if (
            m := missing_result(self.name, "trivy", tool="licenses: trivy")
        ) is not None:
            return m
        rc, out, _ = await run_tool(
            [
                "trivy",
                "fs",
                "--scanners",
                "license",
                "--format",
                "json",
                "--quiet",
                "--skip-dirs",
                "reports",
                "--skip-dirs",
                "node_modules",
                "--skip-dirs",
                "llama.cpp",
                ".",
            ],
            ctx.workdir,
        )
        if (to := timeout_result(self.name, rc)) is not None:
            return to
        try:
            data = json.loads(out or "{}")
        except json.JSONDecodeError:
            return GateResult(
                self.name, GateOutcome.WARN, 0.8, "licenses: unparsable output"
            )
        lic = [
            lc
            for r in data.get("Results", [])
            for lc in (r.get("Licenses") or [])
            if lc.get("Severity") not in ("LOW", "UNKNOWN")  # skip permissive
        ]
        if not lic:
            return GateResult(
                self.name, GateOutcome.PASS, 1.0, "licenses: no problematic licenses"
            )
        bad = [lc for lc in lic if lc.get("Severity") in ("CRITICAL", "HIGH")]
        findings = [
            {
                "file": lc.get("FilePath", ""),
                "message": f"[{lc.get('Severity', '')}] {lc.get('PkgName', '')}: {lc.get('Name', '')}",
            }
            for lc in lic
        ]
        score = max(0.0, 1.0 - min(len(lic), 10) / 10)
        outcome = GateOutcome.FAIL if bad else GateOutcome.WARN
        return GateResult(
            self.name,
            outcome,
            score,
            f"licenses: {len(lic)} flagged ({len(bad)} forbidden/restricted)",
            findings,
        )
