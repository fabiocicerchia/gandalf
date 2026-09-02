"""Supply-chain / dependency / IaC / tests gates:
osv (pip-audit), osv_scanner, trivy, checkov, hadolint, tests.
Ported from ai-harness. (gitleaks lives in secrets.py.)
"""

from __future__ import annotations

import asyncio
import importlib.util
import re
import shutil
import sys
from pathlib import Path

from gandalf.base import GateContext, GateOutcome, GateResult
from gandalf.gates._toolchain import named, parsed, scored
from gandalf.plugins import (
    _TIMEOUT_RC,
    communicate,
    ignore_patterns,
    missing_result,
    run_tool,
    timeout_result,
    unavailable,
)


def _flat(results: list[dict], key: str) -> list[dict]:
    """One kind of finding, flattened across a scanner's per-target results."""
    return [item for r in results for item in r.get(key) or []]


def _checkov_report(out: str) -> dict | None:
    """checkov's report object. It emits a bare object, or a list of them — one
    per framework — when the tree has more than one; the first is the summary
    every caller here reads. None when the output is not JSON at all."""
    raw = parsed(out)
    if raw is None:
        return None
    if isinstance(raw, list):
        return raw[0] if raw else {}
    return raw


async def _hadolint_findings(
    dockerfiles: list[str], workdir: str
) -> tuple[list[dict], str]:
    """Every Dockerfile's hadolint findings, and the file it timed out on ("" if
    none). A file whose output will not parse contributes nothing rather than
    sinking the whole gate."""
    found: list[dict] = []
    for df in dockerfiles:
        # workdir-relative so the path resolves inside the container mount too.
        rc, out, _ = await run_tool(["hadolint", "--format", "json", df], workdir)
        if rc == _TIMEOUT_RC:
            return found, df
        if (items := parsed(out, "[]")) is not None:
            found.extend(items)
    return found, ""


def _pytest_runner(root: Path, base: list[str]) -> list[str] | None:
    """The argv that runs this repo's pytest suite, or None when pytest is not
    installed for the interpreter that would run it.

    A config file says the repo *uses* pytest, not that pytest is installed:
    `python -m pytest` then exits non-zero with "No module named pytest", which
    reads exactly like a failing suite. Ask the interpreter that would run it,
    and run it through sys.executable so the answer is about that interpreter.
    """
    configured = any(
        (root / f).exists() for f in ("pytest.ini", "pyproject.toml", "setup.cfg")
    )
    if configured and importlib.util.find_spec("pytest") is not None:
        return [sys.executable, "-m", "pytest", *base]
    if shutil.which("pytest"):
        return ["pytest", *base]
    return None


class OsvGate:
    """pip-audit against the repo's requirements / project files."""

    name = "osv"
    blocking = False
    langs = frozenset({"python"})

    async def run(self, ctx: GateContext) -> GateResult:
        if (m := missing_result(self.name, "pip-audit")) is not None:
            return m
        argv = ["pip-audit", "--format", "json"]
        if req_files := named(ctx, "requirements*.txt"):
            # workdir-relative so the path resolves both on host and inside the container mount.
            argv = ["pip-audit", "-r", req_files[0], "--format", "json"]
        rc, out, _ = await run_tool(argv, ctx.workdir)
        if (to := timeout_result(self.name, rc)) is not None:
            return to
        data = parsed(out, "[]")
        if data is None:
            return unavailable(self.name, "osv/pip-audit: unparsable output")
        vulns = _flat(data if isinstance(data, list) else [], "vulns")
        n = len(vulns)
        if n == 0:
            return GateResult(
                self.name, GateOutcome.PASS, 1.0, "osv: no known vulnerabilities"
            )
        return scored(self.name, n, f"osv: {n} vulnerability(ies)", vulns, fail=n >= 3)


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
        data = parsed(out)
        if data is None:
            return unavailable(self.name, "osv-scanner: unparsable output")
        vulns = _flat(_flat(data.get("results", []), "packages"), "vulnerabilities")
        n = len(vulns)
        if n == 0:
            return GateResult(self.name, GateOutcome.PASS, 1.0, "osv-scanner: clean")
        return scored(
            self.name, n, f"osv-scanner: {n} vulnerability(ies)", vulns, fail=n >= 3
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
        data = parsed(out)
        if data is None:
            return unavailable(self.name, "trivy: unparsable output")
        results = data.get("Results", [])
        vulns = _flat(results, "Vulnerabilities")
        secrets = _flat(results, "Secrets")
        misconfigs = _flat(results, "Misconfigurations")
        licenses = _flat(results, "Licenses")
        n_v, n_s, n_m, n_l = len(vulns), len(secrets), len(misconfigs), len(licenses)
        total = n_v + n_s + n_m + n_l
        if total == 0:
            return GateResult(self.name, GateOutcome.PASS, 1.0, "trivy: clean")
        return scored(
            self.name,
            total,
            f"trivy: {n_v} vuln(s), {n_s} secret(s), {n_m} misconfig(s), {n_l} license(s)",
            vulns + secrets + misconfigs + licenses,
            fail=n_s > 0 or n_v >= 5 or n_m >= 5,
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
        data = _checkov_report(out)
        if data is None:
            return unavailable(self.name, "checkov: unparsable output")
        summary = data.get("summary", {})
        failed = summary.get("failed", 0)
        passed = summary.get("passed", 0)
        total = failed + passed
        if failed == 0:
            return GateResult(
                self.name, GateOutcome.PASS, 1.0, f"checkov: {passed} check(s) passed"
            )
        # checkov scores by the share of checks that passed, not by finding count,
        # so it builds its own GateResult rather than going through `scored`.
        score = max(0.0, passed / total) if total else 0.0
        outcome = GateOutcome.FAIL if failed >= 5 else GateOutcome.WARN
        return GateResult(
            self.name,
            outcome,
            score,
            f"checkov: {failed} failed / {total} checks",
            data.get("results", {}).get("failed_checks", []),
        )


class HadolintGate:
    name = "hadolint"
    blocking = False
    langs = frozenset({"docker"})

    async def run(self, ctx: GateContext) -> GateResult:
        if (m := missing_result(self.name, "hadolint")) is not None:
            return m
        dockerfiles = named(ctx, "Dockerfile", "Dockerfile.*", "*.dockerfile")
        if not dockerfiles:
            return GateResult(
                self.name, GateOutcome.PASS, 1.0, "hadolint: no Dockerfiles found"
            )
        all_findings, timed_out = await _hadolint_findings(dockerfiles, ctx.workdir)
        if timed_out:
            return unavailable(
                self.name, f"{self.name}: timed out on {timed_out} — skipped"
            )
        n = len(all_findings)
        if n == 0:
            return GateResult(
                self.name,
                GateOutcome.PASS,
                1.0,
                f"hadolint: {len(dockerfiles)} Dockerfile(s) clean",
            )
        errors = sum(1 for f in all_findings if f.get("level") == "error")
        return scored(
            self.name,
            n,
            f"hadolint: {n} issue(s) in {len(dockerfiles)} Dockerfile(s)",
            all_findings,
            fail=errors > 0,
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
        runner = _pytest_runner(root, base)
        if runner is None:
            return unavailable(self.name, "tests: pytest not installed — skipped")
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
