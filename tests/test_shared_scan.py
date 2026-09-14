"""One `trivy fs` per run, read by every gate that wants part of it.

Two gates used to ask trivy for a whole-tree scan each — the supply-chain gate
for vulnerabilities, secrets and misconfigurations, the licensing gate for
licences that the first scan had already collected. That is two walks of the
repository, and two trivy processes contending over one shared vulnerability
database, for one set of answers.

Run: pytest tests/test_shared_scan.py
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator
from pathlib import Path

import pytest

from gandalf import toolrun
from gandalf.base import GateContext, GateOutcome
from gandalf.gates import _toolchain
from gandalf.gates.licenses import LicensesGate
from gandalf.gates.supply_chain import TrivyGate

# One scan carrying both gates' answers: a vulnerability for the supply-chain
# gate, a copyleft licence for the licensing one.
_REPORT = json.dumps(
    {
        "Results": [
            {
                "Target": "requirements.txt",
                "Vulnerabilities": [{"VulnerabilityID": "CVE-1", "PkgName": "x"}],
                "Licenses": [{"Severity": "HIGH", "PkgName": "y", "Name": "GPL-3.0", "FilePath": "y"}],
            }
        ]
    }
)


def _on_path(binary: str) -> str:
    return "/usr/bin/" + binary


@pytest.fixture(autouse=True)
def _clean() -> Iterator[None]:
    _toolchain.reset_shared_scans()
    yield
    _toolchain.reset_shared_scans()


def test_both_gates_read_one_scan(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    async def _fake_run_tool(cmd: list[str], cwd: str, timeout: int | None = None) -> tuple[int, str, str]:
        calls.append(cmd)
        await asyncio.sleep(0)  # let the other gate reach the memo mid-flight
        return 0, _REPORT, ""

    monkeypatch.setattr(toolrun.shutil, "which", _on_path)  # trivy "installed"
    monkeypatch.setattr(_toolchain, "run_tool", _fake_run_tool)
    ctx = GateContext(repo=str(tmp_path), workdir=str(tmp_path), changed_files=[])

    async def _both() -> tuple[object, object]:
        return await asyncio.gather(TrivyGate().run(ctx), LicensesGate().run(ctx))  # type: ignore[return-value]

    trivy, licenses = asyncio.run(_both())

    assert len(calls) == 1, f"trivy walked the tree {len(calls)} times"
    assert calls[0][:2] == ["trivy", "fs"]
    # ...and each gate still reports what it is for, out of that one scan.
    assert trivy.outcome is not GateOutcome.PASS
    assert "vuln" in trivy.summary
    assert "GPL-3.0" in json.dumps(licenses.findings)


def test_the_scan_is_not_kept_between_runs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Process state: the editor runs two scans in one process, and the second
    must not be handed the first one's tree."""
    calls: list[list[str]] = []

    async def _fake_run_tool(cmd: list[str], cwd: str, timeout: int | None = None) -> tuple[int, str, str]:
        calls.append(cmd)
        return 0, _REPORT, ""

    monkeypatch.setattr(toolrun.shutil, "which", _on_path)
    monkeypatch.setattr(_toolchain, "run_tool", _fake_run_tool)
    ctx = GateContext(repo=str(tmp_path), workdir=str(tmp_path), changed_files=[])

    asyncio.run(TrivyGate().run(ctx))
    _toolchain.reset_shared_scans()
    asyncio.run(TrivyGate().run(ctx))

    assert len(calls) == 2
