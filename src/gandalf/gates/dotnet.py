""".NET gates: build, format, vulnerable packages, test.

All four are the `dotnet` CLI itself — no plugin, no extra install, nothing to
configure. That is the reason this suite is the tidiest of the five: the SDK
already ships the linter (`dotnet format`), the audit (`dotnet list package
--vulnerable`) and the test runner.

Everything runs in the directory holding the solution or project file, which is
usually not the repo root — `dotnet build` at the root of a monorepo finds
nothing.
"""

from __future__ import annotations

import re

from gandalf.base import GateContext, GateOutcome, GateResult
from gandalf.gates._toolchain import (
    ToolchainGate,
    counted,
    exit_code,
    project_dir,
    tail,
)
from gandalf.plugins import (
    run_tool,
    timeout_result,
    unavailable,
)

_MARKERS = ("*.sln", "*.slnx", "*.csproj", "*.fsproj", "*.vbproj")
_LANGS = frozenset({"dotnet"})

# `dotnet format` reports one line per fix it would make.
_FORMAT_HIT = re.compile(r"^(?P<file>.+?)\((?P<line>\d+),(?P<col>\d+)\): (?P<msg>.+)$")
# `dotnet list package --vulnerable` marks each hit with a leading '>'.
_VULN_HIT = re.compile(
    r"^\s*>\s+(?P<pkg>\S+)\s+(?P<req>\S+)\s+(?P<res>\S+)\s+(?P<sev>\S+)"
)


class DotnetBuildGate(ToolchainGate):
    """`dotnet build` — does the solution still compile. Blocking."""

    name = "dotnet_build"
    blocking = True
    ecosystem = "dotnet"
    langs = _LANGS
    markers = _MARKERS
    binary = "dotnet"

    async def check(self, ctx: GateContext, root: str) -> GateResult:
        return await exit_code(
            self.name,
            ["dotnet", "build", "--nologo", "-v", "quiet"],
            root,
            ok="dotnet build: compiles",
            bad="dotnet build: does not compile",
        )


class DotnetFormatGate(ToolchainGate):
    """`dotnet format --verify-no-changes` — formatting and style drift.

    Reports only; the SDK's own fixer rewrites the tree under `--fix`.
    """

    name = "dotnet_format"
    ecosystem = "dotnet"
    langs = _LANGS
    markers = _MARKERS
    binary = "dotnet"

    async def check(self, ctx: GateContext, root: str) -> GateResult:
        rc, out, err = await run_tool(
            ["dotnet", "format", "--verify-no-changes", "--no-restore"], root
        )
        if (to := timeout_result(self.name, rc)) is not None:
            return to
        if rc == 0:
            return GateResult(self.name, GateOutcome.PASS, 1.0, "dotnet format: clean")
        combined = (out or "") + (err or "")
        findings = [
            {
                "file": m["file"],
                "line": int(m["line"]),
                "column": int(m["col"]),
                "message": m["msg"],
            }
            for m in (_FORMAT_HIT.match(ln.strip()) for ln in combined.splitlines())
            if m
        ]
        if not findings:
            # No restore, no SDK for this project, an analyser that crashed: the
            # command failed without telling us anything about the code.
            return unavailable(
                self.name, f"dotnet format: did not run — {tail(combined, 2)}"
            )
        return counted(
            self.name,
            len(findings),
            "dotnet format",
            findings[:50],
            noun="fix(es) needed",
        )

    async def fix(self, ctx: GateContext) -> tuple[bool, str]:
        """`dotnet format` — rewrites the tree. Called only under `--fix`."""
        root = project_dir(ctx, self.markers)
        if root is None:
            return (False, "dotnet unavailable — nothing fixed")
        await run_tool(["dotnet", "format", "--no-restore"], root)
        return (False, "dotnet format applied")


class DotnetAuditGate(ToolchainGate):
    """`dotnet list package --vulnerable` — NuGet advisories, transitive included."""

    name = "dotnet_audit"
    ecosystem = "dotnet"
    langs = _LANGS
    markers = _MARKERS
    binary = "dotnet"

    async def check(self, ctx: GateContext, root: str) -> GateResult:
        rc, out, err = await run_tool(
            ["dotnet", "list", "package", "--vulnerable", "--include-transitive"], root
        )
        if (to := timeout_result(self.name, rc)) is not None:
            return to
        combined = (out or "") + (err or "")
        hits = [m for m in (_VULN_HIT.match(ln) for ln in combined.splitlines()) if m]
        if not hits:
            if rc != 0:
                return unavailable(
                    self.name, f"dotnet audit: did not run — {tail(combined, 2)}"
                )
            return GateResult(
                self.name, GateOutcome.PASS, 1.0, "dotnet audit: no vulnerable packages"
            )
        n = len(hits)
        score = max(0.0, 1.0 - min(n, 10) / 10)
        return GateResult(
            self.name,
            GateOutcome.FAIL,
            score,
            f"dotnet audit: {n} vulnerable package(s)",
            [
                {
                    "message": f"{m['pkg']} {m['res']} — {m['sev']}",
                    "severity": m["sev"].lower(),
                }
                for m in hits[:50]
            ],
        )


class DotnetTestGate(ToolchainGate):
    name = "dotnet_test"
    ecosystem = "dotnet"
    langs = _LANGS
    markers = _MARKERS
    binary = "dotnet"

    async def check(self, ctx: GateContext, root: str) -> GateResult:
        return await exit_code(
            self.name,
            ["dotnet", "test", "--nologo", "-v", "quiet"],
            root,
            ok="dotnet test: passed",
            bad="dotnet test: failed",
            fail_re=r"^\s*(?:Failed|error)\s+\S+",
        )
