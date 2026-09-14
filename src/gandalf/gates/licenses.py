"""Dependency-license gate — flags forbidden / restricted licenses out of the
run's `trivy fs` scan, which already asks for licences alongside everything else
it reads. Permissive licenses (LOW/UNKNOWN severity) are ignored so only real
obligations surface."""

from __future__ import annotations

from typing import Any

from gandalf.base import GateContext, GateOutcome, GateResult
from gandalf.gates._toolchain import obj, objects, parsed, scored, trivy_scan
from gandalf.plugins import (
    missing_result,
    timeout_result,
    unavailable,
)


def _flagged(data: object) -> list[dict[str, Any]]:
    """trivy's license findings that carry an obligation. LOW and UNKNOWN are
    the permissive ones and are not worth reporting."""
    return [
        lc
        for r in objects(obj(data).get("Results"))
        for lc in objects(r.get("Licenses"))
        if lc.get("Severity") not in ("LOW", "UNKNOWN")
    ]


class LicensesGate:
    name = "licenses"
    blocking = False
    category = "Licensing"

    async def run(self, ctx: GateContext) -> GateResult:
        if (m := missing_result(self.name, "trivy", tool="licenses: trivy")) is not None:
            return m
        # The scan the supply-chain gate runs, not one of its own: it already
        # asks trivy for licences, and a second `trivy fs` is a second walk of
        # the whole repository for answers the first one has.
        rc, out = await trivy_scan(ctx)
        if (to := timeout_result(self.name, rc)) is not None:
            return to
        data = parsed(out)
        if data is None:
            return unavailable(self.name, "licenses: unparsable output")
        lic = _flagged(data)
        if not lic:
            return GateResult(self.name, GateOutcome.PASS, 1.0, "licenses: no problematic licenses")
        bad = [lc for lc in lic if lc.get("Severity") in ("CRITICAL", "HIGH")]
        findings = [
            {
                "file": lc.get("FilePath", ""),
                "message": f"[{lc.get('Severity', '')}] {lc.get('PkgName', '')}: {lc.get('Name', '')}",
            }
            for lc in lic
        ]
        return scored(
            self.name,
            len(lic),
            f"licenses: {len(lic)} flagged ({len(bad)} forbidden/restricted)",
            findings,
            fail=bool(bad),
        )
