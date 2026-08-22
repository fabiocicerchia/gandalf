"""Severity-weighted gate scoring.

Most gates score by finding *count* — one critical vuln counts the same as one
style nit. When enabled (`[gandalf.severity] weight = true` / `--severity-weight`)
this recomputes a gate's numeric score from the severities its findings carry, so
a single CRITICAL sinks the score more than a handful of LOWs.

Only findings that actually report a severity (security / dependency / IaC gates —
bandit, trivy, semgrep, licenses, osv…) are weighted; gates whose findings have
no severity (ruff, mypy…) are left exactly as the gate scored them. The gate's
RAG outcome is never changed — only the 0..1 score that feeds the composite.
"""

from __future__ import annotations

from . import findings as findings_mod
from .base import GateResult

_WEIGHT = {
    "critical": 2.0,
    "high": 1.0,
    "medium": 0.5,
    "low": 0.2,
    "info": 0.05,
    "unknown": 0.5,
}
# total weight at which the score floors to 0 (≈ two-and-a-half critical findings).
_FLOOR_AT = 5.0

def of(f) -> str:
    """Normalized severity of a finding, or '' if it reports none."""
    return findings_mod.severity(f)


def score(findings: list) -> float | None:
    """Severity-weighted 0..1 score, or None when no finding carries a severity
    (so the caller keeps the gate's own count-based score)."""
    weights = [_WEIGHT[s] for s in (of(f) for f in findings) if s]
    if not weights:
        return None
    return max(0.0, 1.0 - sum(weights) / _FLOOR_AT)


def reweight(res: GateResult) -> GateResult:
    """Return the gate result with a severity-weighted score, or unchanged when
    its findings carry no severity. Outcome, summary and findings are preserved."""
    s = score(res.findings)
    if s is None:
        return res
    out = GateResult(res.name, res.outcome, round(s, 3), res.summary, res.findings)
    for attr in ("_blocking", "_category"):
        if hasattr(res, attr):
            setattr(out, attr, getattr(res, attr))
    return out
