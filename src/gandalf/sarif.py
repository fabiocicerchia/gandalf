"""Render gate results as SARIF 2.1.0 — the format GitHub code scanning and most
CI dashboards ingest. Stdlib only; produces a plain dict the caller json-dumps.

Each finding becomes one SARIF result located at its (repo-relative) file:line,
carrying a stable `partialFingerprints` so GitHub dedups and tracks the alert
across runs. Rules collect into tool.driver.rules, each tagged with a
`security-severity` score so code-scanning alerts get a Critical/High/… rank.
A hard-FAIL gate with no structured findings becomes a single gate-level result
so the failure still surfaces; a location-less WARN is dropped as noise. The run
carries `automationDetails.id = "gandalf"` so its alerts stay a distinct set.
"""

from __future__ import annotations

from .base import GateOutcome, GateResult
from .report import fmt_finding
from .suppress import finding_path, finding_rule, fingerprint

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
# severity word → GitHub code-scanning `security-severity` score (CVSS-like 0-10;
# GitHub ranks >=9 critical, >=7 high, >=4 medium, >=0.1 low). Falls back to the
# SARIF level so every rule still carries a rank.
_SEV_SCORE = {
    "CRITICAL": "9.0",
    "HIGH": "7.0",
    "ERROR": "7.0",
    "MEDIUM": "5.0",
    "MODERATE": "5.0",
    "WARNING": "4.0",
    "LOW": "2.0",
    "INFO": "1.0",
    "NOTE": "1.0",
    "UNKNOWN": "4.0",
}
_LEVEL_SCORE = {"error": "7.0", "warning": "4.0", "note": "1.0"}


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


def _relpath(path: str, root: str) -> str:
    """Repo-relative, forward-slashed — GitHub code scanning rejects absolute
    paths. Strips a leading workdir prefix (the container mounts the repo at
    /src) and a leading './'."""
    p = path.strip().replace("\\", "/")
    root = (root or "").replace("\\", "/").rstrip("/")
    if root and (p == root or p.startswith(root + "/")):
        p = p[len(root) :]
    return p.lstrip("/").removeprefix("./")


def _location(path: str, line: int, root: str = "") -> list[dict]:
    path = _relpath(path, root)
    if not path:
        return []
    region = {"startLine": line} if line > 0 else {}
    phys: dict[str, dict] = {"artifactLocation": {"uri": path}}
    if region:
        phys["region"] = region
    return [{"physicalLocation": phys}]


def _bump_severity(rule: dict, score: str) -> None:
    """Keep the highest security-severity seen for a rule (findings on one rule
    may carry different severities; GitHub ranks the alert by the rule's score)."""
    props = rule.setdefault("properties", {})
    prev = props.get("security-severity")
    if prev is None or float(score) > float(prev):
        props["security-severity"] = score


def to_sarif(results: list[GateResult], meta: dict | None = None) -> dict:
    meta = meta or {}
    root = meta.get("workdir", "")
    rules: dict[str, dict] = {}
    sarif_results: list[dict] = []

    for r in results:
        gate_level = _OUTCOME_LEVEL[r.outcome]
        if not r.findings:
            # No structured findings. Only surface hard FAILs as gate-level
            # results — a location-less WARN ("judge unavailable", "no target —
            # skipped") is pure noise as a code-scanning alert.
            if r.outcome == GateOutcome.FAIL:
                rule = rules.setdefault(r.name, {"id": r.name, "name": r.name})
                _bump_severity(rule, _LEVEL_SCORE[gate_level])
                sarif_results.append(
                    {
                        "ruleId": r.name,
                        "level": gate_level,
                        "message": {"text": r.summary or r.name},
                        "partialFingerprints": {
                            "gandalf/v1": fingerprint(r.name, {"issue": r.summary})
                        },
                    }
                )
            continue
        for f in r.findings:
            rule_name = finding_rule(f) or r.name
            rule_id = (
                f"{r.name}/{rule_name}" if rule_name and rule_name != r.name else r.name
            )
            rule = rules.setdefault(rule_id, {"id": rule_id, "name": rule_name})
            sev = _finding_severity(f)
            level = _SEV_LEVEL.get(sev, gate_level)
            _bump_severity(rule, _SEV_SCORE.get(sev) or _LEVEL_SCORE[level])
            sarif_results.append(
                {
                    "ruleId": rule_id,
                    "level": level,
                    "message": {"text": fmt_finding(f)},
                    "locations": _location(finding_path(f), _finding_line(f), root),
                    "partialFingerprints": {"gandalf/v1": fingerprint(r.name, f)},
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
        "runs": [
            {
                "tool": {"driver": driver},
                "automationDetails": {"id": "gandalf"},
                "results": sarif_results,
            }
        ],
    }
