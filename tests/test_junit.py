"""Tests for JUnit XML rendering. Run: pytest gandalf/test_junit.py"""

from __future__ import annotations

import xml.etree.ElementTree as ET

from gandalf import junit
from gandalf.base import GateOutcome, GateResult

_RESULTS = [
    GateResult(
        "ruff",
        GateOutcome.FAIL,
        0.4,
        "ruff: 2 findings",
        [
            {
                "filename": "a.py",
                "code": "E501",
                "message": "long",
                "location": {"row": 12},
            }
        ],
    ),
    GateResult("bandit", GateOutcome.WARN, 0.8, "1 issue", [{"issue_text": "assert"}]),
    GateResult("gitleaks", GateOutcome.PASS, 1.0, "clean", []),
]


def _doc():
    return junit.to_junit(_RESULTS, {})


def test_shape_and_parseable():
    doc = _doc()
    root = ET.fromstring(doc)  # must be well-formed XML
    assert root.tag == "testsuite"
    assert root.attrib["tests"] == "3"
    assert root.attrib["failures"] == "1"
    assert len(root.findall("testcase")) == 3


def test_fail_becomes_failure_element():
    root = ET.fromstring(_doc())
    ruff = next(tc for tc in root.findall("testcase") if tc.attrib["name"] == "ruff")
    failure = ruff.find("failure")
    assert failure is not None
    assert failure.attrib["message"] == "ruff: 2 findings"
    assert "long" in (failure.text or "")


def test_warn_stays_passing_with_system_out():
    root = ET.fromstring(_doc())
    bandit = next(
        tc for tc in root.findall("testcase") if tc.attrib["name"] == "bandit"
    )
    assert bandit.find("failure") is None
    out = bandit.find("system-out")
    assert out is not None and "1 issue" in out.text


def test_passing_gate_has_no_failure_or_system_out():
    root = ET.fromstring(_doc())
    clean = next(
        tc for tc in root.findall("testcase") if tc.attrib["name"] == "gitleaks"
    )
    assert clean.find("failure") is None
    assert clean.find("system-out") is None


if __name__ == "__main__":
    test_shape_and_parseable()
    test_fail_becomes_failure_element()
    test_warn_stays_passing_with_system_out()
    test_passing_gate_has_no_failure_or_system_out()
    print("ok")
