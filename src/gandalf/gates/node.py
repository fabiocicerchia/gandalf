"""Node / TypeScript gates: eslint, tsc (type check), npm test.

Run against the host Node toolchain and the project's local config/deps (via
`npx --no-install`, which uses the repo's own node_modules) — not the gandalf-tools
image. Each self-skips when the relevant project file is absent. Node dependency
vulns are also covered by the osv_scanner/trivy gates (they read package-lock.json).
"""

from __future__ import annotations

import json
from pathlib import Path

from gandalf.base import GateContext, GateOutcome, GateResult
from gandalf.plugins import run_tool, timeout_result, tool_missing


def _no_pkg(ctx: GateContext) -> bool:
    return not (Path(ctx.workdir) / "package.json").exists()


class EslintGate:
    name = "eslint"
    blocking = False
    langs = frozenset({"node", "ts"})

    async def run(self, ctx: GateContext) -> GateResult:
        if _no_pkg(ctx):
            return GateResult(self.name, GateOutcome.PASS, 1.0, "node: no package.json")
        if tool_missing("npx"):
            return GateResult(
                self.name, GateOutcome.WARN, 0.8, "npx/node not installed — skipped"
            )
        rc, out, _err = await run_tool(
            ["npx", "--no-install", "eslint", "-f", "json", "."], ctx.workdir
        )
        if (to := timeout_result(self.name, rc)) is not None:
            return to
        if not (out or "").strip():
            # npx --no-install printed nothing → eslint isn't installed in the project.
            return GateResult(
                self.name,
                GateOutcome.WARN,
                0.8,
                "eslint: not installed in project (npm i eslint) — skipped",
            )
        try:
            results = json.loads(out)
        except json.JSONDecodeError:
            return GateResult(
                self.name,
                GateOutcome.WARN,
                0.8,
                "eslint: not configured in project — skipped",
            )
        errors = sum(r.get("errorCount", 0) for r in results)
        warns = sum(r.get("warningCount", 0) for r in results)
        total = errors + warns
        if total == 0:
            return GateResult(self.name, GateOutcome.PASS, 1.0, "eslint: clean")
        score = max(0.0, 1.0 - min(total, 10) / 10)
        outcome = GateOutcome.FAIL if errors > 0 else GateOutcome.WARN
        return GateResult(
            self.name, outcome, score, f"eslint: {errors} error(s), {warns} warning(s)"
        )

    async def fix(self, ctx: GateContext) -> tuple[bool, str]:
        """Apply eslint's autofixes in place (--fix). Called only under `--fix`."""
        if _no_pkg(ctx) or tool_missing("npx"):
            return (False, "eslint unavailable — nothing fixed")
        rc, _out, _err = await run_tool(
            ["npx", "--no-install", "eslint", "--fix", "."], ctx.workdir
        )
        # eslint --fix is silent on success; a clean rc means fixes (if any) applied.
        return (rc == 0, "eslint --fix applied")


class TscGate:
    name = "tsc"
    blocking = False
    langs = frozenset({"ts"})

    async def run(self, ctx: GateContext) -> GateResult:
        if not (Path(ctx.workdir) / "tsconfig.json").exists():
            return GateResult(self.name, GateOutcome.PASS, 1.0, "tsc: no tsconfig.json")
        if tool_missing("npx"):
            return GateResult(
                self.name, GateOutcome.WARN, 0.8, "npx/node not installed — skipped"
            )
        rc, out, err = await run_tool(
            ["npx", "--no-install", "tsc", "--noEmit"], ctx.workdir
        )
        if (to := timeout_result(self.name, rc)) is not None:
            return to
        combined = (out or "") + (err or "")
        n = combined.count("error TS")
        if rc == 0:
            return GateResult(self.name, GateOutcome.PASS, 1.0, "tsc: no type errors")
        if n == 0:
            # non-zero exit but no TS errors parsed → tsc missing or misconfigured, not a clean pass.
            return GateResult(
                self.name,
                GateOutcome.WARN,
                0.8,
                "tsc: could not run (not installed or misconfigured) — skipped",
            )
        score = max(0.0, 1.0 - min(n, 20) / 20)
        outcome = GateOutcome.FAIL if n > 10 else GateOutcome.WARN
        tail = "\n".join(ln for ln in combined.splitlines() if "error TS" in ln)[:1000]
        return GateResult(
            self.name, outcome, score, f"tsc: {n} type error(s)", [{"errors": tail}]
        )


class NodeTestGate:
    name = "node_test"
    blocking = False
    langs = frozenset({"node", "ts"})

    async def run(self, ctx: GateContext) -> GateResult:
        pkg = Path(ctx.workdir) / "package.json"
        if not pkg.exists():
            return GateResult(self.name, GateOutcome.PASS, 1.0, "node: no package.json")
        try:
            scripts = json.loads(pkg.read_text(errors="replace")).get("scripts", {})
        except (json.JSONDecodeError, OSError):
            scripts = {}
        if "test" not in scripts:
            return GateResult(self.name, GateOutcome.PASS, 1.0, "node: no test script")
        if tool_missing("npm"):
            return GateResult(
                self.name, GateOutcome.WARN, 0.8, "npm/node not installed — skipped"
            )
        rc, out, err = await run_tool(["npm", "test", "--silent"], ctx.workdir)
        if (to := timeout_result(self.name, rc)) is not None:
            return to
        if rc == 0:
            return GateResult(self.name, GateOutcome.PASS, 1.0, "npm test: passed")
        tail = "\n".join(((out or "") + (err or "")).strip().splitlines()[-5:])
        return GateResult(
            self.name, GateOutcome.FAIL, 0.0, f"npm test: failed — {tail}"
        )
