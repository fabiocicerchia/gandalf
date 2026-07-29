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
from gandalf.plugins import ignore_patterns, run_tool, timeout_result

_IMAGE = os.environ.get("GANDALF_KICS_IMAGE", "checkmarx/kics:latest")


class KicsGate:
    name = "kics"
    blocking = False

    async def run(self, ctx: GateContext) -> GateResult:
        have_host = shutil.which("kics") is not None
        if not have_host and not shutil.which("docker"):
            return GateResult(
                self.name,
                GateOutcome.WARN,
                0.8,
                "kics unavailable (no host binary and no docker) — skipped",
            )

        outdir = tempfile.mkdtemp(prefix="gandalf-kics-")
        try:
            common = [
                "scan",
                "--no-progress",
                "--no-color",
                "--report-formats",
                "json",
                "--exclude-paths",
                ",".join(ignore_patterns(ctx.workdir)),
            ]
            if have_host:
                cmd = ["kics", *common, "-p", ".", "-o", outdir]
            else:
                cmd = [
                    "docker",
                    "run",
                    "--rm",
                    "-v",
                    f"{os.path.abspath(ctx.workdir)}:/src",
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
            rc, _out, _err = await run_tool(cmd, ctx.workdir)
            if (to := timeout_result(self.name, rc)) is not None:
                return to
            results = os.path.join(outdir, "results.json")
            if not os.path.exists(results):
                return GateResult(
                    self.name,
                    GateOutcome.WARN,
                    0.8,
                    "kics: no results produced — skipped",
                )
            # Small local results read right after the subprocess completes —
            # not worth a thread hop.
            with open(results, errors="replace") as fh:  # noqa: ASYNC230
                data = json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            return GateResult(self.name, GateOutcome.WARN, 0.8, f"kics: {exc}")
        finally:
            shutil.rmtree(outdir, ignore_errors=True)

        sev = data.get("severity_counters", {}) or {}
        high, med, low = sev.get("HIGH", 0), sev.get("MEDIUM", 0), sev.get("LOW", 0)
        findings = [
            {
                "file": f.get("file_name", ""),
                "line": f.get("line", ""),
                "message": f"[{q.get('severity', '')}] {q.get('query_name', '')}",
            }
            for q in data.get("queries", [])
            for f in q.get("files", [])
        ]
        if high + med + low + sev.get("INFO", 0) == 0 and not findings:
            return GateResult(
                self.name, GateOutcome.PASS, 1.0, "kics: no misconfigurations"
            )
        score = max(0.0, 1.0 - min(high * 2 + med, 10) / 10)
        outcome = GateOutcome.FAIL if high > 0 else GateOutcome.WARN
        return GateResult(
            self.name,
            outcome,
            score,
            f"kics: {high} HIGH, {med} MEDIUM, {low} LOW",
            findings,
        )
