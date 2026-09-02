"""KICS IaC scanner (Checkmarx) — misconfig across Terraform / k8s / Docker /
Ansible / CloudFormation, etc. Complements checkov and trivy's misconfig scan.

KICS needs its query assets, which the standalone binary doesn't ship, so this
gate runs the official `checkmarx/kics` image (it bundles them) — unless `kics`
is already on the host PATH. Override the image with GANDALF_KICS_IMAGE.

It writes a JSON report to a temp dir and reads it back, so the scorecard carries
the full per-issue finding list (file + line + query), not just severity counts.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile

from gandalf.base import GateContext, GateOutcome, GateResult
from gandalf.plugins import (
    ignore_patterns,
    run_tool,
    timeout_result,
    unavailable,
)

_IMAGE = os.environ.get("GANDALF_KICS_IMAGE", "checkmarx/kics:latest")


def _argv(workdir: str, outdir: str, have_host: bool) -> list[str]:
    """kics on the host, or the checkmarx/kics image, which bundles the query
    assets the standalone binary does not ship."""
    common = [
        "scan",
        "--no-progress",
        "--no-color",
        "--report-formats",
        "json",
        "--exclude-paths",
        ",".join(ignore_patterns(workdir)),
    ]
    if have_host:
        return ["kics", *common, "-p", ".", "-o", outdir]
    return [
        "docker",
        "run",
        "--rm",
        "-v",
        f"{os.path.abspath(workdir)}:/src",
        "-v",
        f"{outdir}:/out",
        "-w",
        "/src",
        _IMAGE,
        *common,
        "-p",
        "/src",
        "-o",
        "/out",
    ]


def _findings(data: dict) -> list[dict]:
    """Every matched file of every failing query, as file/line/message."""
    return [
        {
            "file": f.get("file_name", ""),
            "line": f.get("line", ""),
            "message": f"[{q.get('severity', '')}] {q.get('query_name', '')}",
        }
        for q in data.get("queries", [])
        for f in q.get("files", [])
    ]


def _result(gate: str, data: dict) -> GateResult:
    """Score the report: a HIGH counts double and any HIGH makes the gate red."""
    sev = data.get("severity_counters", {}) or {}
    high, med, low = sev.get("HIGH", 0), sev.get("MEDIUM", 0), sev.get("LOW", 0)
    findings = _findings(data)
    if high + med + low + sev.get("INFO", 0) == 0 and not findings:
        return GateResult(gate, GateOutcome.PASS, 1.0, "kics: no misconfigurations")
    score = max(0.0, 1.0 - min(high * 2 + med, 10) / 10)
    outcome = GateOutcome.FAIL if high > 0 else GateOutcome.WARN
    summary = f"kics: {high} HIGH, {med} MEDIUM, {low} LOW"
    return GateResult(gate, outcome, score, summary, findings)


class KicsGate:
    name = "kics"
    blocking = False

    async def run(self, ctx: GateContext) -> GateResult:
        have_host = shutil.which("kics") is not None
        if not have_host and not shutil.which("docker"):
            return unavailable(
                self.name, "kics unavailable (no host binary and no docker) — skipped"
            )

        outdir = tempfile.mkdtemp(prefix="gandalf-kics-")
        try:
            rc, _out, _err = await run_tool(
                _argv(ctx.workdir, outdir, have_host), ctx.workdir
            )
            if (to := timeout_result(self.name, rc)) is not None:
                return to
            results = os.path.join(outdir, "results.json")
            if not os.path.exists(results):
                return unavailable(self.name, "kics: no results produced — skipped")
            # Small local results read right after the subprocess completes —
            # not worth a thread hop.
            with open(results, errors="replace") as fh:  # noqa: ASYNC230
                data = json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            return unavailable(self.name, f"kics: {exc}")
        finally:
            shutil.rmtree(outdir, ignore_errors=True)

        return _result(self.name, data)
