"""The kics gate's SOPS handling: encrypted values are not leaked secrets, plain ones still are."""

from __future__ import annotations

from pathlib import Path

from gandalf.base import GateOutcome
from gandalf.gates.kics import _drop_encrypted, _result

SOPS_FILE = """apiVersion: v1
kind: Secret
stringData:
    DB_PASSWORD: ENC[AES256_GCM,data:q3Nl,iv:abc=,tag:def=,type:str]
    SMTP_PASSWORD: hunter2
sops:
    mac: ENC[AES256_GCM,data:zz,type:str]
"""


def _report(file_name: str) -> dict:
    return {
        "severity_counters": {"HIGH": 2, "MEDIUM": 1, "LOW": 0, "INFO": 0},
        "queries": [
            {
                "query_name": "Passwords And Secrets - Generic Password",
                "severity": "HIGH",
                "files": [{"file_name": file_name, "line": 4}, {"file_name": file_name, "line": 5}],
            },
            {
                "query_name": "Missing User Instruction",
                "severity": "MEDIUM",
                "files": [{"file_name": "Dockerfile", "line": 1}],
            },
        ],
    }


def test_encrypted_secret_dropped_plain_one_kept(tmp_path: Path) -> None:
    (tmp_path / "k8s").mkdir()
    (tmp_path / "k8s" / "app.sops.yaml").write_text(SOPS_FILE)
    data = _drop_encrypted(_report("/src/k8s/app.sops.yaml"), str(tmp_path))  # the path as the docker image reports it
    secret = next(q for q in data["queries"] if q["query_name"].startswith("Passwords"))
    assert [f["line"] for f in secret["files"]] == [5]  # the plain hunter2 is still a finding
    assert data["severity_counters"] == {"HIGH": 1, "MEDIUM": 1}
    assert any(q["query_name"] == "Missing User Instruction" for q in data["queries"])  # other queries untouched
    assert "1 HIGH, 1 MEDIUM" in _result("kics", data).summary


def test_all_encrypted_leaves_only_real_findings(tmp_path: Path) -> None:
    (tmp_path / "s.sops.yaml").write_text(SOPS_FILE.replace("hunter2", "ENC[AES256_GCM,data:x,type:str]"))
    data = _drop_encrypted(_report("./s.sops.yaml"), str(tmp_path))  # the path as a host kics reports it
    assert [q["query_name"] for q in data["queries"]] == ["Missing User Instruction"]
    result = _result("kics", data)
    assert result.outcome == GateOutcome.WARN  # no HIGH left: no longer red
    assert result.summary == "kics: 0 HIGH, 1 MEDIUM, 0 LOW"


def test_nothing_encrypted_keeps_kics_counters(tmp_path: Path) -> None:
    (tmp_path / "plain.yaml").write_text("a: 1\nb: 2\nc: 3\npassword: hunter2\npassword: hunter3\n")
    report = _report("plain.yaml")
    assert _drop_encrypted(report, str(tmp_path)) is report


def test_unreadable_file_keeps_the_finding(tmp_path: Path) -> None:
    data = _drop_encrypted(_report("/src/missing.sops.yaml"), str(tmp_path))
    assert len(data["queries"][0]["files"]) == 2  # cannot tell it is encrypted: report it
