"""Tests for SARIF rendering. Run: pytest gandalf/test_sarif.py"""

from __future__ import annotations

import json

from gandalf import sarif
from gandalf.base import GateOutcome, GateResult

_RESULTS = [
    GateResult(
        "ruff",
        GateOutcome.FAIL,
        0.4,
        "ruff: 2",
        [
            {
                "filename": "a.py",
                "code": "E501",
                "message": "long",
                "location": {"row": 12},
            },
            {"path": "b.py", "rule_id": "F401", "message": "unused", "line": 3},
        ],
    ),
    GateResult(
        "bandit",
        GateOutcome.WARN,
        0.8,
        "1 issue",
        [
            {
                "filename": "c.py",
                "line_number": 9,
                "issue_text": "assert",
                "issue_severity": "LOW",
                "check_id": "B101",
            }
        ],
    ),
    GateResult("gitleaks", GateOutcome.PASS, 1.0, "clean", []),
    GateResult("go_build", GateOutcome.FAIL, 0.0, "compile error", []),
    # WARN with no structured findings — a "skipped/unavailable" gate, which is
    # noise as a code-scanning alert and must be dropped from SARIF.
    GateResult("codespell", GateOutcome.WARN, 0.5, "codespell: unavailable", []),
]


def _doc():
    return sarif.to_sarif(_RESULTS, {})


def test_shape_and_serializable():
    doc = _doc()
    assert doc["version"] == "2.1.0" and doc["$schema"].endswith("sarif-2.1.0.json")
    json.dumps(doc)  # must be JSON-serializable


def test_rules_deduped_and_sorted():
    ids = [r["id"] for r in _doc()["runs"][0]["tool"]["driver"]["rules"]]
    assert ids == sorted(ids)
    assert "ruff/E501" in ids and "ruff/F401" in ids and "go_build" in ids


def test_levels_and_locations():
    results = _doc()["runs"][0]["results"]
    by_rule = {}
    for r in results:
        by_rule.setdefault(r["ruleId"], r)
    # severity LOW downgrades bandit's warning to note
    assert by_rule["bandit/B101"]["level"] == "note"
    # ruff findings are error (gate FAIL), located at file:line
    e501 = by_rule["ruff/E501"]
    assert e501["level"] == "error"
    loc = e501["locations"][0]["physicalLocation"]
    assert loc["artifactLocation"]["uri"] == "a.py" and loc["region"]["startLine"] == 12
    # a failing gate with no findings still surfaces as a gate-level result
    assert by_rule["go_build"]["level"] == "error"


def test_passing_gate_emits_nothing():
    ids = {r["ruleId"] for r in _doc()["runs"][0]["results"]}
    assert "gitleaks" not in ids


def test_warn_without_findings_dropped():
    # A location-less WARN (skipped/unavailable gate) is noise for code scanning.
    ids = {r["ruleId"] for r in _doc()["runs"][0]["results"]}
    assert "codespell" not in ids
    # ...but a hard FAIL with no findings still surfaces (see go_build below).
    assert "go_build" in ids


def test_security_severity_on_rules():
    rules = {r["id"]: r for r in _doc()["runs"][0]["tool"]["driver"]["rules"]}
    # every rule carries a numeric security-severity so GitHub can rank the alert
    for r in rules.values():
        assert "security-severity" in r["properties"]
    # CRITICAL/HIGH-ish (ruff FAIL → error) ranks above a LOW finding (bandit)
    assert float(rules["ruff/E501"]["properties"]["security-severity"]) > float(
        rules["bandit/B101"]["properties"]["security-severity"]
    )


def test_partial_fingerprints_present_and_stable():
    results = _doc()["runs"][0]["results"]
    for r in results:
        assert r["partialFingerprints"]["gandalf/v1"]
    # stable across runs (same inputs → same fingerprint)
    again = {
        r["ruleId"]: r["partialFingerprints"]["gandalf/v1"]
        for r in sarif.to_sarif(_RESULTS, {})["runs"][0]["results"]
    }
    first = {r["ruleId"]: r["partialFingerprints"]["gandalf/v1"] for r in results}
    assert first == again


def test_automation_details_category():
    assert _doc()["runs"][0]["automationDetails"]["id"] == "gandalf"


def test_paths_made_repo_relative():
    # Absolute / container-mount paths get rebased to repo-relative via meta.workdir.
    res = GateResult(
        "ruff",
        GateOutcome.FAIL,
        0.4,
        "ruff: 1",
        [{"filename": "/src/pkg/a.py", "code": "E501", "message": "x", "line": 5}],
    )
    doc = sarif.to_sarif([res], {"workdir": "/src"})
    uri = doc["runs"][0]["results"][0]["locations"][0]["physicalLocation"][
        "artifactLocation"
    ]["uri"]
    assert uri == "pkg/a.py"


if __name__ == "__main__":
    test_shape_and_serializable()
    test_rules_deduped_and_sorted()
    test_levels_and_locations()
    test_passing_gate_emits_nothing()
    test_warn_without_findings_dropped()
    test_security_severity_on_rules()
    test_partial_fingerprints_present_and_stable()
    test_automation_details_category()
    test_paths_made_repo_relative()
    print("ok")
