"""OSSF Scorecard gate — the repository's security-posture score (0–10).

https://github.com/ossf/scorecard runs a suite of security best-practice checks
(Binary-Artifacts, Dangerous-Workflow, License, Pinned-Dependencies, SAST,
Security-Policy, Token-Permissions, …) and emits an aggregate 0–10 score.

We run it in **local mode** (`--local .`), which uses only the file-based checks
and needs no GitHub token — so it works offline and against any checkout. The
API-only checks (Branch-Protection, Code-Review, Maintained, …) simply aren't
run in local mode; they don't drag the aggregate down.
"""

from __future__ import annotations

from gandalf.base import GateContext, GateOutcome, GateResult
from gandalf.gates._toolchain import parsed
from gandalf.plugins import (
    missing_result,
    run_tool,
    timeout_result,
    unavailable,
)

# Scorecard's aggregate is a 0–10 float. Bands are generous: local mode drops the
# GitHub-API checks entirely, so a clean file-based posture already sits high.
PASS_AT = 7.0
WARN_AT = 4.0
_MAX_CHECK_SCORE = 10


def _unreadable(gate: str, err: str) -> GateResult:
    """Scorecard printed something that is not JSON. A non-local run would ask
    for a token; local mode shouldn't, but be safe."""
    if err and ("token" in err.lower() or "auth" in err.lower()):
        return unavailable(gate, "scorecard: needs GITHUB_AUTH_TOKEN — skipped")
    return unavailable(gate, "scorecard: unparsable output")


def _aggregate(data: dict) -> float:
    """Scorecard's 0–10 aggregate, or -1 when every check was inconclusive."""
    try:
        return float(data.get("score", -1))
    except (TypeError, ValueError):
        return -1.0


def _below_max(checks: list) -> list[dict]:
    """Each check that ran (score >= 0) below a perfect 10, with its reason."""
    return [
        {"check": c.get("name"), "score": c.get("score"), "reason": c.get("reason")}
        for c in checks
        if isinstance(c.get("score"), (int, float))
        and 0 <= c["score"] < _MAX_CHECK_SCORE
    ]


def _outcome(aggregate: float) -> GateOutcome:
    if aggregate >= PASS_AT:
        return GateOutcome.PASS
    return GateOutcome.WARN if aggregate >= WARN_AT else GateOutcome.FAIL


class ScorecardGate:
    """OSSF Scorecard — security best-practices posture of the repository."""

    name = "scorecard"
    blocking = False

    async def run(self, ctx: GateContext) -> GateResult:
        if (m := missing_result(self.name, "scorecard")) is not None:
            return m
        rc, out, err = await run_tool(
            ["scorecard", "--local", ".", "--format", "json"],
            ctx.workdir,
        )
        if (to := timeout_result(self.name, rc)) is not None:
            return to
        data = parsed(out)
        if data is None:
            return _unreadable(self.name, err)

        checks = data.get("checks") or []
        aggregate = _aggregate(data)
        # score -1 = scorecard couldn't compute an aggregate (every check inconclusive).
        if aggregate < 0 or not checks:
            return unavailable(
                self.name, "scorecard: no conclusive checks (local mode) — skipped"
            )

        findings = _below_max(checks)
        score = max(0.0, min(1.0, aggregate / 10.0))
        summary = f"scorecard: {aggregate:.1f}/10 · {len(findings)} check(s) below max"
        return GateResult(self.name, _outcome(aggregate), score, summary, findings)
