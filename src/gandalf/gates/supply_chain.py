"""Supply-chain / dependency / IaC / tests gates:
osv (pip-audit), osv_scanner, trivy, checkov, hadolint, tests.
Ported from ai-harness. (gitleaks lives in secrets.py.)
"""

from __future__ import annotations

import asyncio
import json
import re
import shutil
from pathlib import Path

from gandalf.base import GateContext, GateOutcome, GateResult
from gandalf.plugins import (
    _TIMEOUT_RC,
    communicate,
    ignore_patterns,
    missing_result,
    run_tool,
    timeout_result,
)


class OsvGate:
    """pip-audit against the repo's requirements / project files."""

    name = "osv"
    blocking = False
    langs = frozenset({"python"})

    async def run(self, ctx: GateContext) -> GateResult:
        if (m := missing_result(self.name, "pip-audit")) is not None:
            return m
        root = Path(ctx.workdir)
        req_files = list(root.glob("requirements*.txt")) + list(
            root.glob("**/requirements*.txt")
        )
        req_files = [
            r
            for r in req_files
            if ".venv" not in r.parts and "node_modules" not in r.parts
        ]
        if not req_files:
            rc, out, _ = await run_tool(["pip-audit", "--format", "json"], ctx.workdir)
        else:
            # workdir-relative so the path resolves both on host and inside the container mount.
            rc, out, _ = await run_tool(
                [
                    "pip-audit",
                    "-r",
                    str(req_files[0].relative_to(root)),
                    "--format",
                    "json",
                ],
                ctx.workdir,
            )
        if (to := timeout_result(self.name, rc)) is not None:
            return to
        try:
            data = json.loads(out or "[]")
        except json.JSONDecodeError:
            return GateResult(
                self.name, GateOutcome.WARN, 0.8, "osv/pip-audit: unparsable output"
            )
        vulns = [
            v
            for item in (data if isinstance(data, list) else [])
            for v in item.get("vulns", [])
        ]
        n = len(vulns)
        if n == 0:
            return GateResult(
                self.name, GateOutcome.PASS, 1.0, "osv: no known vulnerabilities"
            )
        score = max(0.0, 1.0 - min(n, 10) / 10)
        outcome = GateOutcome.FAIL if n >= 3 else GateOutcome.WARN
        return GateResult(
            self.name, outcome, score, f"osv: {n} vulnerability(ies)", vulns
        )


class OsvScannerGate:
    name = "osv_scanner"
    blocking = False

    async def run(self, ctx: GateContext) -> GateResult:
        if (m := missing_result(self.name, "osv-scanner")) is not None:
            return m
        rc, out, _ = await run_tool(
            ["osv-scanner", "scan", "--recursive", "--format", "json", "."], ctx.workdir
        )
        if (to := timeout_result(self.name, rc)) is not None:
            return to
        try:
            data = json.loads(out or "{}")
        except json.JSONDecodeError:
            return GateResult(
                self.name, GateOutcome.WARN, 0.8, "osv-scanner: unparsable output"
            )
        results = data.get("results", [])
        vulns = [
            v
            for r in results
            for pkg in r.get("packages", [])
            for v in pkg.get("vulnerabilities", [])
        ]
        n = len(vulns)
        if n == 0:
            return GateResult(self.name, GateOutcome.PASS, 1.0, "osv-scanner: clean")
        score = max(0.0, 1.0 - min(n, 10) / 10)
        outcome = GateOutcome.FAIL if n >= 3 else GateOutcome.WARN
        return GateResult(
            self.name, outcome, score, f"osv-scanner: {n} vulnerability(ies)", vulns
        )


class TrivyGate:
    name = "trivy"
    blocking = False

    async def run(self, ctx: GateContext) -> GateResult:
        if (m := missing_result(self.name, "trivy")) is not None:
            return m
        # Pass every ignore to both --skip-dirs and --skip-files (trivy accepts a
        # comma list for each) so a pattern works whether it names a dir or a file.
        skip = ",".join(ignore_patterns(ctx.workdir))
        rc, out, _ = await run_tool(
            [
                "trivy",
                "fs",
                "--scanners",
                "vuln,secret,misconfig,license",
                "--format",
                "json",
                "--quiet",
                "--skip-dirs",
                skip,
                "--skip-files",
                skip,
                ".",
            ],
            ctx.workdir,
        )
        if (to := timeout_result(self.name, rc)) is not None:
            return to
        try:
            data = json.loads(out or "{}")
        except json.JSONDecodeError:
            return GateResult(
                self.name, GateOutcome.WARN, 0.8, "trivy: unparsable output"
            )
        results = data.get("Results", [])
        vulns = [v for r in results for v in r.get("Vulnerabilities", []) or []]
        secrets = [s for r in results for s in r.get("Secrets", []) or []]
        misconfigs = [m for r in results for m in r.get("Misconfigurations", []) or []]
        licenses = [lic for r in results for lic in r.get("Licenses", []) or []]
        n_v, n_s, n_m, n_l = len(vulns), len(secrets), len(misconfigs), len(licenses)
        total = n_v + n_s + n_m + n_l
        if total == 0:
            return GateResult(self.name, GateOutcome.PASS, 1.0, "trivy: clean")
        score = max(0.0, 1.0 - min(total, 10) / 10)
        outcome = (
            GateOutcome.FAIL if n_s > 0 or n_v >= 5 or n_m >= 5 else GateOutcome.WARN
        )
        return GateResult(
            self.name,
            outcome,
            score,
            f"trivy: {n_v} vuln(s), {n_s} secret(s), {n_m} misconfig(s), {n_l} license(s)",
            (vulns + secrets + misconfigs + licenses),
        )


class CheckovGate:
    name = "checkov"
    blocking = False

    async def run(self, ctx: GateContext) -> GateResult:
        if (m := missing_result(self.name, "checkov")) is not None:
            return m
        skip_args = []
        for p in ignore_patterns(ctx.workdir):
            skip_args += ["--skip-path", p]
        rc, out, _ = await run_tool(
            [
                "checkov",
                "-d",
                ".",
                "--output",
                "json",
                "--compact",
                "--quiet",
                *skip_args,
            ],
            ctx.workdir,
        )
        if (to := timeout_result(self.name, rc)) is not None:
            return to
        try:
            raw = json.loads(out or "{}")
            data = (raw[0] if raw else {}) if isinstance(raw, list) else raw
        except json.JSONDecodeError:
            return GateResult(
                self.name, GateOutcome.WARN, 0.8, "checkov: unparsable output"
            )
        summary = data.get("summary", {})
        failed = summary.get("failed", 0)
        passed = summary.get("passed", 0)
        total = failed + passed
        if failed == 0:
            return GateResult(
                self.name, GateOutcome.PASS, 1.0, f"checkov: {passed} check(s) passed"
            )
        score = max(0.0, passed / total) if total else 0.0
        outcome = GateOutcome.FAIL if failed >= 5 else GateOutcome.WARN
        failed_checks = data.get("results", {}).get("failed_checks", [])
        return GateResult(
            self.name,
            outcome,
            score,
            f"checkov: {failed} failed / {total} checks",
            failed_checks,
        )


class HadolintGate:
    name = "hadolint"
    blocking = False
    langs = frozenset({"docker"})

    async def run(self, ctx: GateContext) -> GateResult:
        if (m := missing_result(self.name, "hadolint")) is not None:
            return m
        root = Path(ctx.workdir)
        dockerfiles = (
            list(root.rglob("Dockerfile"))
            + list(root.rglob("Dockerfile.*"))
            + list(root.rglob("*.dockerfile"))
        )
        dockerfiles = [
            d
            for d in dockerfiles
            if ".venv" not in d.parts and "node_modules" not in d.parts
        ]
        if not dockerfiles:
            return GateResult(
                self.name, GateOutcome.PASS, 1.0, "hadolint: no Dockerfiles found"
            )
        all_findings: list[dict] = []
        for df in dockerfiles:
            # workdir-relative so the path resolves inside the container mount too.
            rc, out, _ = await run_tool(
                ["hadolint", "--format", "json", str(df.relative_to(root))], ctx.workdir
            )
            if rc == _TIMEOUT_RC:
                return GateResult(
                    self.name,
                    GateOutcome.WARN,
                    0.8,
                    f"{self.name}: timed out on {df.name} — skipped",
                )
            try:
                all_findings.extend(json.loads(out or "[]"))
            except json.JSONDecodeError:
                pass
        n = len(all_findings)
        if n == 0:
            return GateResult(
                self.name,
                GateOutcome.PASS,
                1.0,
                f"hadolint: {len(dockerfiles)} Dockerfile(s) clean",
            )
        errors = sum(1 for f in all_findings if f.get("level") == "error")
        score = max(0.0, 1.0 - min(n, 10) / 10)
        outcome = GateOutcome.FAIL if errors > 0 else GateOutcome.WARN
        return GateResult(
            self.name,
            outcome,
            score,
            f"hadolint: {n} issue(s) in {len(dockerfiles)} Dockerfile(s)",
            all_findings,
        )


class TestsGate:
    """Run the project's pytest suite and report pass/fail."""

    name = "tests"
    blocking = False
    langs = frozenset({"python"})

    async def run(self, ctx: GateContext) -> GateResult:
        root = Path(ctx.workdir)
        # Don't collect vendored/untracked trees (e.g. llama.cpp, node_modules) —
        # their own suites fail to import here and would spuriously fail this gate.
        base = ["--tb=no", "-q", "--no-header"]
        for p in ignore_patterns(ctx.workdir):
            base += ["--ignore", p]
        if (
            (root / "pytest.ini").exists()
            or (root / "pyproject.toml").exists()
            or (root / "setup.cfg").exists()
        ):
            runner = ["python", "-m", "pytest", *base]
        elif shutil.which("pytest"):
            runner = ["pytest", *base]
        else:
            return GateResult(
                self.name, GateOutcome.WARN, 0.8, "tests: no pytest found — skipped"
            )
        proc = await asyncio.create_subprocess_exec(
            *runner,
            cwd=ctx.workdir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        streams = await communicate(proc, 120)
        if streams is None:
            return GateResult(
                self.name, GateOutcome.FAIL, 0.0, "tests: timed out after 120s"
            )
        out_b, _ = streams
        out = out_b.decode(errors="replace") if out_b else ""
        tail = "\n".join(out.strip().splitlines()[-5:])
        if proc.returncode == 0:
            return GateResult(
                self.name, GateOutcome.PASS, 1.0, f"tests: passed — {tail}"
            )
        m = re.search(r"(\d+) failed", out)
        n_fail = int(m.group(1)) if m else None
        score = 0.0 if n_fail is None else max(0.0, 1.0 - min(n_fail, 10) / 10)
        return GateResult(
            self.name,
            GateOutcome.FAIL,
            score,
            f"tests: {n_fail if n_fail is not None else '?'} failure(s) — {tail}",
        )
