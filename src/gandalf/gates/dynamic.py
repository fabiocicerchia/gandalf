"""Dynamic / fuzz gates: atheris, nikto, sqlmap, dalfox. Ported from ai-harness.

Only meaningful against a live target. With no target (ctx.meta['target'] absent
— i.e. you didn't pass --target) they degrade to WARN so static runs aren't
blocked. SAFETY: non-localhost targets are refused unless meta['allow_remote'].
"""

from __future__ import annotations

import asyncio
import re
import shutil
import sys
from pathlib import Path
from urllib.parse import urlparse

from gandalf.base import GateContext, GateOutcome, GateResult
from gandalf.gates._toolchain import scored
from gandalf.plugins import (
    communicate,
    unavailable,
)

_DEFAULT_FUZZ_TIME = 60
_DAST_TIMEOUT = 300


# A handful of real findings warns; beyond that the scan has failed.
MAX_FINDINGS = 3


def _is_local(url: str) -> bool:
    host = urlparse(url).hostname or ""
    return host in ("localhost", "127.0.0.1", "0.0.0.0", "::1")  # noqa: S104 — compared against, never bound  # nosec B104 — host equality check, not a bind


async def _run(cmd: list[str], cwd: str, timeout: int = _DAST_TIMEOUT) -> tuple[int, str, str]:  # noqa: ASYNC109 — the timeout is plumbed to asyncio.wait_for, which is the mechanism this rule asks for
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    streams = await communicate(proc, timeout)
    if streams is None:
        return -1, "", f"timed out after {timeout}s"
    out, err = streams
    return (
        proc.returncode if proc.returncode is not None else -1,
        out.decode(errors="replace"),
        err.decode(errors="replace"),
    )


def _guard(ctx: GateContext, name: str) -> tuple[str | None, GateResult | None]:
    """Return (target_url, None) or (None, skip_result)."""
    target = (ctx.meta or {}).get("target", "")
    if not target:
        return None, unavailable(name, f"{name}: no target URL — skipped (pass --target)")
    if not _is_local(target) and not (ctx.meta or {}).get("allow_remote", False):
        return None, unavailable(name, f"{name}: refusing active scan against non-local target '{target}'")
    return target, None


def _endpoint(ctx: GateContext, target: str) -> tuple[str, str]:
    """(API base, bearer token) for an active scan against `target`."""
    meta = ctx.meta or {}
    return meta.get("api", target.rstrip("/") + "/api/v1"), meta.get("bearer", "")


# nikto always reports these, on any server; they are not findings.
_NIKTO_BANNER = ("Server:", "Retrieved", "Allowed HTTP")


def _nikto_lines(out: str) -> tuple[list[str], list[str]]:
    """(every `+ ` result line, the ones that are not nikto's standard banner)."""
    found = [ln for ln in out.strip().splitlines() if ln.startswith("+ ")]
    return found, [f for f in found if not any(k in f for k in _NIKTO_BANNER)]


def _dalfox_vulns(text: str) -> list[str]:
    """dalfox's confirmed-XSS lines."""
    return [ln for ln in text.splitlines() if "[V]" in ln or "VULN" in ln.upper()]


async def _atheris_installed(workdir: str) -> bool:
    """Is the atheris package importable in the target workdir?

    Split out so the log-parsing tests can stub it: they exercise how libFuzzer
    output is interpreted, which has nothing to do with whether the fuzzer is
    installed on the machine running the suite. Inline, the probe made those
    tests pass only on a developer box that happened to have atheris.
    """
    # sys.executable, not "python": that name does not exist on a stock Ubuntu
    # (only python3), and the probe has to use the same interpreter that will
    # then run the harness — otherwise it answers about the wrong one.
    rc, _, _ = await _run([sys.executable, "-c", "import atheris"], workdir, timeout=30)
    return rc == 0


class AtherisGate:
    """Coverage-guided fuzzing of Python parsers via atheris.
    Requires a harness at tests/fuzz/fuzz_adapters.py and the atheris package."""

    name = "atheris"
    blocking = False

    async def run(self, ctx: GateContext) -> GateResult:
        harness = Path(ctx.workdir) / "tests" / "fuzz" / "fuzz_adapters.py"
        if not harness.exists():
            return unavailable(self.name, "atheris: no fuzz harness at tests/fuzz/fuzz_adapters.py")
        if not await _atheris_installed(ctx.workdir):
            return unavailable(self.name, "atheris: package not installed — skipped")
        fuzz_time = int((ctx.meta or {}).get("fuzz_time", _DEFAULT_FUZZ_TIME))
        rc, out, err = await _run(
            [
                sys.executable,
                str(harness),
                f"-max_total_time={fuzz_time}",
                "-artifact_prefix=/tmp/atheris-crash-",
            ],
            ctx.workdir,
            timeout=fuzz_time + 30,
        )
        combined = out + err
        if rc == -1:
            return unavailable(self.name, f"atheris: timed out (budget={fuzz_time}s)")
        # Match libFuzzer's own crash markers, not a bare "crash" substring —
        # the harness is invoked with -artifact_prefix=/tmp/atheris-crash-,
        # which libFuzzer echoes back in its startup banner and would always
        # self-match. A nonzero exit is the authoritative signal (libFuzzer
        # exits 0 after a clean time-budget run); the marker check is belt
        # and suspenders for when exit codes get lost through a wrapper.
        if rc != 0 or "ERROR: libFuzzer" in combined or "Uncaught Python exception" in combined:
            return GateResult(
                self.name,
                GateOutcome.FAIL,
                0.0,
                "atheris: crash detected in parser",
                [{"log": combined[-500:]}],
            )
        return GateResult(
            self.name,
            GateOutcome.PASS,
            1.0,
            f"atheris: {fuzz_time}s fuzz run — no crashes",
        )


class NiktoGate:
    """Server misconfiguration sweep via nikto."""

    name = "nikto"
    blocking = False

    async def run(self, ctx: GateContext) -> GateResult:
        target, skip = _guard(ctx, self.name)
        if skip:
            return skip
        if not shutil.which("nikto"):
            return unavailable(self.name, "nikto not installed — skipped")
        rc, out, _ = await _run(
            ["nikto", "-h", target, "-ask", "no", "-nointeractive", "-Format", "txt"],
            ctx.workdir,
        )
        if rc == -1:
            return unavailable(self.name, "nikto: timed out")
        findings, real = _nikto_lines(out)
        if not findings:
            return GateResult(self.name, GateOutcome.PASS, 1.0, "nikto: no findings")
        return scored(
            self.name,
            len(real),
            f"nikto: {len(real)} issue(s)",
            [{"finding": f} for f in real],
            fail=len(real) > MAX_FINDINGS,
        )


class SqlmapGate:
    """SQL injection probe via sqlmap."""

    name = "sqlmap"
    blocking = False

    async def run(self, ctx: GateContext) -> GateResult:
        target, skip = _guard(ctx, self.name)
        if skip:
            return skip
        if not shutil.which("sqlmap"):
            return unavailable(self.name, "sqlmap not installed — skipped")
        api, bearer = _endpoint(ctx, target)
        cmd = [
            "sqlmap",
            "-u",
            f"{api}/findings?page=1&severity=high",
            "-p",
            "page,severity",
            "--batch",
            "--level=2",
            "--risk=2",
            "--random-agent",
            "--output-dir=/tmp/sqlmap-harness",
            "--forms",
            "--crawl=2",
        ]
        if bearer:
            cmd += [f"--header=Authorization: Bearer {bearer}"]
        rc, out, err = await _run(cmd, ctx.workdir)
        if rc == -1:
            return unavailable(self.name, "sqlmap: timed out")
        combined = out + err
        if re.search(r"(is vulnerable|parameter.*injectable)", combined, re.IGNORECASE):
            return GateResult(
                self.name,
                GateOutcome.FAIL,
                0.0,
                "sqlmap: injectable parameter found",
                [{"log": combined[-800:]}],
            )
        return GateResult(self.name, GateOutcome.PASS, 1.0, "sqlmap: no injection found")


class DalfoxGate:
    """XSS probe via dalfox."""

    name = "dalfox"
    blocking = False

    async def run(self, ctx: GateContext) -> GateResult:
        target, skip = _guard(ctx, self.name)
        if skip:
            return skip
        if not shutil.which("dalfox"):
            return unavailable(self.name, "dalfox not installed — skipped")
        api, bearer = _endpoint(ctx, target)
        cmd = [
            "dalfox",
            "url",
            f"{api}/findings?cluster=FUZZ&severity=FUZZ",
            "--skip-bav",
            "--no-spinner",
            "--silence",
        ]
        if bearer:
            cmd += ["-H", f"Authorization: Bearer {bearer}"]
        rc, out, err = await _run(cmd, ctx.workdir)
        if rc == -1:
            return unavailable(self.name, "dalfox: timed out")
        vuln_lines = _dalfox_vulns(out + err)
        if vuln_lines:
            return GateResult(
                self.name,
                GateOutcome.FAIL,
                0.0,
                f"dalfox: {len(vuln_lines)} XSS finding(s)",
                [{"finding": ln} for ln in vuln_lines],
            )
        return GateResult(self.name, GateOutcome.PASS, 1.0, "dalfox: no XSS found")
