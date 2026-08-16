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
    # go_build is absent for the reason in test_results_without_a_location_are_left_out.
    assert "ruff/E501" in ids and "ruff/F401" in ids


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
    # A failing gate with no findings does NOT surface here. It has no file to
    # attach an alert to, and Code Scanning rejects the entire upload — every
    # alert in the run — over a single locationless result:
    #   locationFromSarifResult: expected at least one location
    # It is still reported in the console output and the PR review body.
    assert "go_build" not in by_rule


def test_passing_gate_emits_nothing():
    ids = {r["ruleId"] for r in _doc()["runs"][0]["results"]}
    assert "gitleaks" not in ids


def test_results_without_a_location_are_left_out():
    # Nothing locationless may reach the file: one such result makes GitHub
    # reject the upload wholesale, which is how a single repo-level finding
    # used to lose every alert in the run.
    doc = _doc()
    for result in doc["runs"][0]["results"]:
        assert result.get("locations"), result["ruleId"]
    ids = {r["ruleId"] for r in doc["runs"][0]["results"]}
    assert "codespell" not in ids  # WARN, no findings
    assert "go_build" not in ids  # FAIL, no findings


def test_the_count_of_dropped_findings_is_recorded():
    # Dropped, not disappeared: the number is in the file so "why is this not
    # an alert?" has an answer without reading the source.
    run = _doc()["runs"][0]
    assert run["properties"]["gandalf/findingsWithoutLocation"] >= 1


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
    test_results_without_a_location_are_left_out()
    test_the_count_of_dropped_findings_is_recorded()
    test_security_severity_on_rules()
    test_partial_fingerprints_present_and_stable()
    test_automation_details_category()
    test_paths_made_repo_relative()
    print("ok")


def test_bandit_findings_are_identified_by_test_id():
    # bandit's `code` is the offending source snippet. Reading it as the rule
    # id produced a multi-line, 400-character id, and Code Scanning rejects the
    # whole upload over one id past 255 characters.
    res = [
        GateResult(
            "bandit",
            GateOutcome.WARN,
            0.8,
            "1 issue",
            [
                {
                    "filename": "a.py",
                    "line_number": 27,
                    "issue_text": "partial path",
                    "test_id": "B607",
                    "code": "27 p = subprocess.run(\n28     ['kubectl'],\n",
                }
            ],
        )
    ]
    ids = [
        r["id"] for r in sarif.to_sarif(res, {})["runs"][0]["tool"]["driver"]["rules"]
    ]
    assert ids == ["bandit/B607"]


def test_over_long_rule_ids_are_truncated_and_stay_distinct():
    res = [
        GateResult(
            "tool",
            GateOutcome.WARN,
            0.5,
            "2",
            [
                {"path": "a.py", "line": 1, "message": "m", "rule_id": "x" * 400},
                {"path": "b.py", "line": 2, "message": "m", "rule_id": "x" * 400 + "y"},
            ],
        )
    ]
    ids = [
        r["id"] for r in sarif.to_sarif(res, {})["runs"][0]["tool"]["driver"]["rules"]
    ]
    assert len(ids) == 2, "two distinct ids must not collapse into one rule"
    assert all(len(i) <= 255 for i in ids)
