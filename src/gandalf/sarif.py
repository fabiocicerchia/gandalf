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

import hashlib

from . import findings
from .base import GateOutcome, GateResult
from .report import fmt_finding
from .suppress import fingerprint

# Code Scanning rejects an upload whose rule id exceeds this, and it rejects
# the whole file — one tool putting a message where an id belongs takes the
# entire run down with it.
_MAX_RULE_ID = 255

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


# The shared readers, under the names this module already uses.
_finding_severity = findings.severity_raw
_finding_line = findings.line
_relpath = findings.relpath


def _location(path: str, line: int, root: str = "") -> list[dict]:
    """SARIF locations for a finding, or [] when it names no file.

    A result with no location is not merely unhelpful: Code Scanning rejects
    the WHOLE upload with "locationFromSarifResult: expected at least one
    location", so one path-less finding loses every alert in the run. Callers
    must drop those results rather than emit them empty — see to_sarif.
    """
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


def _rule_id(gate: str, rule_name: str) -> str:
    """`gate/rule`, kept inside the length Code Scanning accepts.

    Truncated ids keep a digest of the original so two long ids that share a
    prefix stay two rules rather than collapsing into one.
    """
    rule_id = f"{gate}/{rule_name}" if rule_name and rule_name != gate else gate
    if len(rule_id) <= _MAX_RULE_ID:
        return rule_id
    digest = hashlib.sha256(rule_id.encode()).hexdigest()[:12]
    return f"{rule_id[: _MAX_RULE_ID - len(digest) - 1]}~{digest}"


def _collect(results: list[GateResult], root: str) -> tuple[dict[str, dict], list[dict], int]:
    """(rules by id, SARIF results, findings that could not be located).

    Findings without a resolvable location are counted rather than dropped — a
    total that quietly omits some of them is not a total, and one locationless
    result invalidates the entire upload.
    """
    rules: dict[str, dict] = {}
    sarif_results: list[dict] = []
    without_location = 0
    for r in results:
        gate_level = _OUTCOME_LEVEL[r.outcome]
        if not r.findings:
            # No structured findings. Only surface hard FAILs as gate-level
            # results — a location-less WARN ("judge unavailable", "no target —
            # skipped") is pure noise as a code-scanning alert. A gate that
            # failed without naming a file — a tool crash, a config error — has
            # nowhere to appear as an alert, but is still in the console output
            # and the PR review body.
            if r.outcome == GateOutcome.FAIL:
                without_location += 1
            continue
        for f in r.findings:
            rule_name = findings.rule(f) or r.name
            rule_id = _rule_id(r.name, rule_name)
            rule = rules.setdefault(rule_id, {"id": rule_id, "name": rule_name})
            sev = _finding_severity(f)
            level = _SEV_LEVEL.get(sev, gate_level)
            locations = _location(findings.path(f), _finding_line(f), root)
            if not locations:
                # Repo-level findings (no path) cannot be rendered as an alert
                # against anything. Counted rather than silently dropped.
                without_location += 1
                continue
            _bump_severity(rule, _SEV_SCORE.get(sev) or _LEVEL_SCORE[level])
            sarif_results.append(
                {
                    "ruleId": rule_id,
                    "level": level,
                    "message": {"text": fmt_finding(f)},
                    "locations": locations,
                    "partialFingerprints": {"gandalf/v1": fingerprint(r.name, f)},
                }
            )
    return rules, sarif_results, without_location


def to_sarif(results: list[GateResult], meta: dict | None = None) -> dict:
    """Render the results as a SARIF log.

    SARIF is what GitHub code scanning ingests, so this is how findings become
    annotations on a pull request instead of lines in a job log. Findings
    without a resolvable location are counted rather than dropped — a total
    that quietly omits some of them is not a total.
    """
    meta = meta or {}
    rules, sarif_results, without_location = _collect(results, meta.get("workdir", ""))

    driver = {
        "name": "gandalf",
        "informationUri": INFO_URI,
        "rules": [rules[k] for k in sorted(rules)],
    }
    version = meta.get("version")
    if version:
        driver["version"] = str(version)
    run: dict = {
        "tool": {"driver": driver},
        "automationDetails": {"id": "gandalf"},
        "results": sarif_results,
    }
    if without_location:
        # Recorded in the file itself, so "why is this finding not an alert?"
        # has an answer that does not require reading this source.
        run["properties"] = {"gandalf/findingsWithoutLocation": without_location}
    return {"$schema": SCHEMA, "version": "2.1.0", "runs": [run]}
