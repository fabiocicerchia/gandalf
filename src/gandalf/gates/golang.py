"""Go gates: build, golangci-lint, govulncheck, test.

These need the Go toolchain, so they run against the host `go`/linters (you have
them) — not the gandalf-tools image. Each self-skips (PASS) when the workdir has no
go.mod. Dependency vulns for Go are ALSO covered by the multi-ecosystem osv_scanner
and trivy gates (they read go.mod/go.sum); govulncheck adds reachability analysis.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from gandalf.base import GateContext, GateOutcome, GateResult
from gandalf.plugins import run_tool, timeout_result, tool_missing


def _no_module(ctx: GateContext) -> bool:
    return not (Path(ctx.workdir) / "go.mod").exists()


class GoBuildGate:
    """`go build ./...` — the Go analogue of the Python build gate. Blocking."""

    name = "go_build"
    blocking = True
    langs = frozenset({"go"})

    async def run(self, ctx: GateContext) -> GateResult:
        if _no_module(ctx):
            return GateResult(
                self.name, GateOutcome.PASS, 1.0, "go: no module (no go.mod)"
            )
        if tool_missing("go"):
            return GateResult(
                self.name, GateOutcome.WARN, 0.8, "go not installed — skipped"
            )
        rc, _out, err = await run_tool(["go", "build", "./..."], ctx.workdir)
        if (to := timeout_result(self.name, rc)) is not None:
            return to
        if rc == 0:
            return GateResult(self.name, GateOutcome.PASS, 1.0, "go build: compiles")
        tail = "\n".join((err or "").strip().splitlines()[-5:])
        return GateResult(
            self.name,
            GateOutcome.FAIL,
            0.0,
            f"go build: does not compile — {tail}",
            [{"stderr": err[-1000:]}],
        )


class GolangciLintGate:
    """golangci-lint — meta-linter (govet, staticcheck, errcheck, unused, …)."""

    name = "golangci_lint"
    blocking = False
    langs = frozenset({"go"})

    async def run(self, ctx: GateContext) -> GateResult:
        if _no_module(ctx):
            return GateResult(
                self.name, GateOutcome.PASS, 1.0, "go: no module (no go.mod)"
            )
        if tool_missing("golangci-lint"):
            return GateResult(
                self.name,
                GateOutcome.WARN,
                0.8,
                "golangci-lint not installed — skipped",
            )
        rc, out, _ = await run_tool(
            ["golangci-lint", "run", "--out-format", "json", "./..."], ctx.workdir
        )
        if (to := timeout_result(self.name, rc)) is not None:
            return to
        try:
            issues = json.loads(out or "{}").get("Issues") or []
        except json.JSONDecodeError:
            issues = []
        n = len(issues)
        if n == 0:
            return GateResult(self.name, GateOutcome.PASS, 1.0, "golangci-lint: clean")
        score = max(0.0, 1.0 - min(n, 10) / 10)
        outcome = GateOutcome.WARN if n <= 3 else GateOutcome.FAIL
        return GateResult(
            self.name, outcome, score, f"golangci-lint: {n} issue(s)", issues
        )

    async def fix(self, ctx: GateContext) -> tuple[bool, str]:
        """`golangci-lint run --fix` — applies the fixes its linters ship
        (gofmt/gofumpt, goimports, misspell, …). Called only under `--fix`.

        Exits non-zero whenever anything unfixable is left, which is the usual
        end of a successful fix run, so what it rewrote is measured from the
        worktree rather than read from the exit code."""
        if _no_module(ctx) or tool_missing("golangci-lint"):
            return (False, "golangci-lint unavailable — nothing fixed")
        await run_tool(["golangci-lint", "run", "--fix", "./..."], ctx.workdir)
        return (False, "golangci-lint --fix applied")


class GovulncheckGate:
    name = "govulncheck"
    blocking = False
    langs = frozenset({"go"})

    async def run(self, ctx: GateContext) -> GateResult:
        if _no_module(ctx):
            return GateResult(
                self.name, GateOutcome.PASS, 1.0, "go: no module (no go.mod)"
            )
        if tool_missing("govulncheck"):
            return GateResult(
                self.name, GateOutcome.WARN, 0.8, "govulncheck not installed — skipped"
            )
        rc, out, _ = await run_tool(["govulncheck", "./..."], ctx.workdir)
        if (to := timeout_result(self.name, rc)) is not None:
            return to
        n = len((out or "").split("Vulnerability #")) - 1
        if n <= 0:
            return GateResult(
                self.name,
                GateOutcome.PASS,
                1.0,
                "govulncheck: no known vulnerabilities",
            )
        score = max(0.0, 1.0 - min(n, 10) / 10)
        outcome = GateOutcome.FAIL if n >= 1 else GateOutcome.WARN
        return GateResult(
            self.name, outcome, score, f"govulncheck: {n} vulnerability(ies)"
        )


class GoTestGate:
    name = "go_test"
    blocking = False
    langs = frozenset({"go"})

    async def run(self, ctx: GateContext) -> GateResult:
        if _no_module(ctx):
            return GateResult(
                self.name, GateOutcome.PASS, 1.0, "go: no module (no go.mod)"
            )
        if tool_missing("go"):
            return GateResult(
                self.name, GateOutcome.WARN, 0.8, "go not installed — skipped"
            )
        rc, out, err = await run_tool(["go", "test", "./..."], ctx.workdir)
        if (to := timeout_result(self.name, rc)) is not None:
            return to
        combined = (out or "") + (err or "")
        if rc == 0:
            return GateResult(self.name, GateOutcome.PASS, 1.0, "go test: passed")
        fails = len(re.findall(r"^--- FAIL", combined, re.MULTILINE))
        score = 0.0 if not fails else max(0.0, 1.0 - min(fails, 10) / 10)
        tail = "\n".join(combined.strip().splitlines()[-5:])
        return GateResult(
            self.name,
            GateOutcome.FAIL,
            score,
            f"go test: {fails or '?'} failure(s) — {tail}",
        )
