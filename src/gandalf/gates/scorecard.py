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

import json

from gandalf.base import GateContext, GateOutcome, GateResult
from gandalf.plugins import missing_result, run_tool, timeout_result

# Scorecard's aggregate is a 0–10 float. Bands are generous: local mode drops the
# GitHub-API checks entirely, so a clean file-based posture already sits high.
PASS_AT = 7.0
WARN_AT = 4.0
_MAX_CHECK_SCORE = 10


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
        try:
            data = json.loads(out or "{}")
        except json.JSONDecodeError:
            # A non-local run would ask for a token; local mode shouldn't, but be safe.
            if err and ("token" in err.lower() or "auth" in err.lower()):
                return GateResult(
                    self.name,
                    GateOutcome.WARN,
                    0.8,
                    "scorecard: needs GITHUB_AUTH_TOKEN — skipped",
                )
            return GateResult(
                self.name, GateOutcome.WARN, 0.8, "scorecard: unparsable output"
            )

        checks = data.get("checks") or []
        try:
            aggregate = float(data.get("score", -1))
        except (TypeError, ValueError):
            aggregate = -1.0
        # score -1 = scorecard couldn't compute an aggregate (every check inconclusive).
        if aggregate < 0 or not checks:
            return GateResult(
                self.name,
                GateOutcome.WARN,
                0.8,
                "scorecard: no conclusive checks (local mode) — skipped",
            )

        # Findings: each check that ran (score >= 0) below a perfect 10, with its reason.
        findings = [
            {"check": c.get("name"), "score": c.get("score"), "reason": c.get("reason")}
            for c in checks
            if isinstance(c.get("score"), (int, float))
            and 0 <= c["score"] < _MAX_CHECK_SCORE
        ]
        score = max(0.0, min(1.0, aggregate / 10.0))
        if aggregate >= PASS_AT:
            outcome = GateOutcome.PASS
        elif aggregate >= WARN_AT:
            outcome = GateOutcome.WARN
        else:
            outcome = GateOutcome.FAIL
        summary = f"scorecard: {aggregate:.1f}/10 · {len(findings)} check(s) below max"
        return GateResult(self.name, outcome, score, summary, findings)
