"""Render gate results as SARIF 2.1.0 — the format GitHub code scanning and most
CI dashboards ingest. Stdlib only; produces a plain dict the caller json-dumps.

Each finding becomes one SARIF result located at its file:line; a non-passing
gate with no structured findings becomes a single gate-level result so the
outcome still surfaces. Rules are collected into tool.driver.rules.
"""

from __future__ import annotations

from .base import GateOutcome, GateResult
from .report import fmt_finding
from .suppress import finding_path, finding_rule

SCHEMA = "https://json.schemastore.org/sarif-2.1.0.json"
INFO_URI = "https://github.com/fabiocicerchia/local-ai-lab"

# gate outcome → SARIF level
_OUTCOME_LEVEL = {
    GateOutcome.PASS: "note",
    GateOutcome.WARN: "warning",
    GateOutcome.FAIL: "error",
}
# common per-finding severity words → SARIF level (used when a finding carries one)
_SEV_LEVEL = {
    "CRITICAL": "error",
    "HIGH": "error",
    "ERROR": "error",
    "MEDIUM": "warning",
    "MODERATE": "warning",
    "WARNING": "warning",
    "LOW": "note",
    "INFO": "note",
    "NOTE": "note",
    "UNKNOWN": "warning",
}


def _finding_severity(f: dict) -> str:
    for k in ("severity", "Severity", "issue_severity", "level", "Level"):
        v = f.get(k) if isinstance(f, dict) else None
        if v:
            return str(v).upper()
    return ""


def _finding_line(f: dict) -> int:
    if not isinstance(f, dict):
        return 0
    for k in ("line", "line_number", "Line", "startLine"):
        v = f.get(k)
        if isinstance(v, int) and v > 0:
            return v
        if isinstance(v, str) and v.isdigit():
            return int(v)
    loc = f.get("location")
    if isinstance(loc, dict) and isinstance(loc.get("row"), int):
        return loc["row"]
    return 0


def _location(path: str, line: int) -> list[dict]:
    if not path:
        return []
    region = {"startLine": line} if line > 0 else {}
    phys: dict[str, dict] = {"artifactLocation": {"uri": path}}
    if region:
        phys["region"] = region
    return [{"physicalLocation": phys}]


def to_sarif(results: list[GateResult], meta: dict | None = None) -> dict:
    meta = meta or {}
    rules: dict[str, dict] = {}
    sarif_results: list[dict] = []

    for r in results:
        gate_level = _OUTCOME_LEVEL[r.outcome]
        if not r.findings:
            # No structured findings — surface the gate outcome itself if not clean.
            if r.outcome != GateOutcome.PASS:
                rules.setdefault(r.name, {"id": r.name, "name": r.name})
                sarif_results.append(
                    {
                        "ruleId": r.name,
                        "level": gate_level,
                        "message": {"text": r.summary or r.name},
                    }
                )
            continue
        for f in r.findings:
            rule = finding_rule(f) or r.name
            rule_id = f"{r.name}/{rule}" if rule and rule != r.name else r.name
            rules.setdefault(rule_id, {"id": rule_id, "name": rule})
            sev = _finding_severity(f)
            level = _SEV_LEVEL.get(sev, gate_level)
            sarif_results.append(
                {
                    "ruleId": rule_id,
                    "level": level,
                    "message": {"text": fmt_finding(f)},
                    "locations": _location(finding_path(f), _finding_line(f)),
                }
            )

    driver = {
        "name": "gandalf",
        "informationUri": INFO_URI,
        "rules": [rules[k] for k in sorted(rules)],
    }
    version = meta.get("version")
    if version:
        driver["version"] = str(version)
    return {
        "$schema": SCHEMA,
        "version": "2.1.0",
        "runs": [{"tool": {"driver": driver}, "results": sarif_results}],
    }
