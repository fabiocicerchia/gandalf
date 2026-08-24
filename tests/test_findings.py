"""Tests for the shared finding reader. Run: pytest tests/test_findings.py"""

from __future__ import annotations

from gandalf import findings, suppress

# One finding per shape gandalf actually receives, named by the tool that emits it.
RUFF = {
    "filename": "src/a.py",
    "location": {"row": 12, "column": 4},
    "code": "E501",
    "message": "line too long",
}
SEMGREP = {
    "path": "src/b.py",
    "start": {"line": 7, "col": 3},
    "check_id": "py.lang.x",
    "extra": {"severity": "WARNING"},
    "message": "semgrep hit",
}
BANDIT = {
    "filename": "src/c.py",
    "line_number": 42,
    "test_id": "B105",
    "test_name": "hardcoded_password_string",
    "issue_text": "Possible hardcoded password",
    "issue_severity": "HIGH",
    # bandit's `code` is the offending source, not an identifier.
    "code": '41 def login():\n42     password = "hunter2"\n',
}
TRIVY = {
    "Target": "alpine:3.1",
    "VulnerabilityID": "CVE-2021-1",
    "Severity": "CRITICAL",
    "Description": "boom",
}
MYPY = {"error": 'src/d.py:552: error: "Gate" has no attribute "langs"  [attr-defined]'}
FORMAT = {"file": "Would reformat: src/e.py"}


def test_bandit_rule_is_the_test_id_not_the_source_snippet():
    """The regression this module exists for: `code` must not beat `test_id`.

    The VS Code extension's own key list omitted test_id, so every bandit
    finding was identified by three lines of source.
    """
    assert findings.rule(BANDIT) == "B105"
    assert "\n" not in findings.rule(BANDIT)


def test_rule_reading_across_tools():
    assert findings.rule(RUFF) == "E501"
    assert findings.rule(SEMGREP) == "py.lang.x"
    assert findings.rule(TRIVY) == "CVE-2021-1"
    assert findings.rule(MYPY) == ""


def test_nested_positions():
    assert (findings.line(RUFF), findings.column(RUFF)) == (12, 4)
    assert (findings.line(SEMGREP), findings.column(SEMGREP)) == (7, 3)
    assert findings.line(BANDIT) == 42
    assert findings.line(TRIVY) == 0


def test_severity_normalisation():
    assert findings.severity(BANDIT) == "high"
    assert findings.severity(TRIVY) == "critical"
    # semgrep nests it; only severity.py used to look there.
    assert findings.severity(SEMGREP) == "medium"
    # No severity field at all is not the same as an explicit "unknown".
    assert findings.severity(MYPY) == ""
    assert findings.severity({"severity": "UNKNOWN"}) == "unknown"
    assert findings.severity({"severity": "nonsense"}) == ""


def test_every_normalised_severity_is_a_known_level():
    for word in (
        "CRITICAL",
        "high",
        "Error",
        "moderate",
        "warn",
        "minor",
        "note",
        "informational",
    ):
        assert findings.severity({"severity": word}) in findings.LEVELS


def test_normalise_shape():
    n = findings.normalise(BANDIT)
    assert n == {
        "path": "src/c.py",
        "line": 42,
        "column": 0,
        "rule": "B105",
        "message": "Possible hardcoded password",
        "severity": "high",
        "url": "",
    }


def test_severity_folded_into_the_message():
    """kics and the licenses gate write `[HIGH] ...` rather than a severity key."""
    n = findings.normalise({"finding": "[HIGH] world-readable secret"})
    assert (n["severity"], n["message"]) == ("high", "world-readable secret")


def test_bracket_that_is_not_a_severity_is_left_alone():
    for text in ("[B603] subprocess call", "x has no attribute [attr-defined]"):
        n = findings.normalise({"finding": text})
        assert (n["severity"], n["message"]) == ("", text)


def test_rule_documentation_url():
    assert (
        findings.normalise({"finding": "x", "url": "https://d/r"})["url"]
        == "https://d/r"
    )
    assert (
        findings.normalise({"finding": "x", "PrimaryURL": "https://d/c"})["url"]
        == "https://d/c"
    )


def test_location_scraped_from_prose_and_trimmed(tmp_path):
    """mypy/tsc/codeql carry their location only in the message text."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "d.py").write_text("x = 1\n")
    n = findings.normalise(MYPY, str(tmp_path))
    assert (n["path"], n["line"]) == ("src/d.py", 552)
    # The location has its own fields now, so it is not repeated in the message.
    assert n["message"].startswith("error:")


def test_prose_that_merely_looks_like_a_path_is_not_trusted(tmp_path):
    n = findings.normalise(
        {"finding": "see docs/missing.md:12 for details"}, str(tmp_path)
    )
    assert n["path"] == "" and n["line"] == 0


def test_sentence_in_a_location_key_becomes_the_message(tmp_path):
    """The format gate puts the whole finding in `file`."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "e.py").write_text("x = 1\n")
    n = findings.normalise(FORMAT, str(tmp_path))
    assert n["message"] == "Would reformat: src/e.py"
    assert n["path"] == "src/e.py"


def test_relpath_rebases_container_paths():
    assert findings.relpath("/src/a.py", "/src") == "a.py"
    assert findings.relpath("./a.py") == "a.py"
    assert findings.relpath("a\\b.py") == "a/b.py"


def test_annotate_keeps_the_tools_own_keys():
    out = findings.annotate(BANDIT)
    assert out["test_id"] == "B105"  # untouched
    assert out["_gandalf"]["rule"] == "B105"
    # A non-dict finding has nowhere to put the block.
    assert findings.annotate("a bare string") == "a bare string"


def test_non_dict_findings_are_survivable():
    for reader in (findings.path, findings.rule, findings.message, findings.severity):
        assert reader("a bare string") == ""
    assert findings.line(None) == 0


# --- the frozen half ---------------------------------------------------------


def test_fingerprint_vocabulary_is_frozen():
    """Widening the shared lists must not move a fingerprint: a baseline file is
    a list of these hashes sitting in someone's repository."""
    # `Target` is readable by the shared reader but deliberately invisible here.
    assert findings.path(TRIVY) == "alpine:3.1"
    assert findings.fingerprint_keys(TRIVY)[0] == ""
    # `check` likewise.
    assert findings.rule({"check": "X"}) == "X"
    assert findings.fingerprint_keys({"check": "X"})[1] == ""


def test_fingerprint_is_stable_for_known_findings():
    """Golden hashes, taken from the implementation that predates findings.py.

    If one of these moves, every `.gandalf-baseline.json` in existence stops
    matching the findings it accepted — so they are here to make that a failing
    test rather than a support question.
    """
    assert (
        suppress.fingerprint("ruff", RUFF) == "7b959079a6b363f06dd56522357092823810133f"
    )
    assert (
        suppress.fingerprint("bandit", BANDIT)
        == "e18dc25e2f9d074cc726c914f925f3db3432da56"
    )
    assert (
        suppress.fingerprint("semgrep", SEMGREP)
        == "1f95489d888b00dbcf02041e0eff8383dc40b548"
    )
    assert (
        suppress.fingerprint("trivy", TRIVY)
        == "c4f79753892ee22c50032f9c77cdee3a33fe6cc3"
    )


def test_fingerprint_still_line_insensitive():
    a = suppress.fingerprint(
        "ruff", {"path": "a.py", "code": "E501", "message": "x", "line": 1}
    )
    b = suppress.fingerprint(
        "ruff", {"path": "a.py", "code": "E501", "message": "x", "line": 99}
    )
    assert a == b
