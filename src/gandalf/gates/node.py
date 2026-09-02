"""Node / TypeScript gates: eslint, tsc (type check), npm test.

Run against the host Node toolchain and the project's local config/deps (via
`npx --no-install`, which uses the repo's own node_modules) — not the gandalf-tools
image. Each self-skips when the relevant project file is absent. Node dependency
vulns are also covered by the osv_scanner/trivy gates (they read package-lock.json).
"""

from __future__ import annotations

import json
from pathlib import Path

from gandalf import suggest
from gandalf.base import GateContext, GateOutcome, GateResult
from gandalf.findings import relpath
from gandalf.gates._toolchain import merged, parsed, scored
from gandalf.plugins import (
    run_tool,
    timeout_result,
    tool_missing,
    unavailable,
)


def _no_pkg(ctx: GateContext) -> bool:
    return not (Path(ctx.workdir) / "package.json").exists()


def _item(m: dict, rel: str) -> dict:
    """One eslint message, in the keys the report, SARIF and the PR comments
    all read."""
    return {
        "path": rel,
        "line": m.get("line") or 0,
        "column": m.get("column") or 0,
        "rule_id": m.get("ruleId") or "eslint",
        "message": m.get("message", ""),
        "severity": "error" if m.get("severity") == 2 else "warning",
    }


def _fix_range(m: dict) -> list | None:
    """The character-offset span of the rule's own autofix, when it has one."""
    fix = m.get("fix") if isinstance(m.get("fix"), dict) else {}
    rng = fix.get("range")
    return rng if isinstance(rng, list) and len(rng) == 2 else None


def _messages(results: list, workdir: str) -> list[dict]:
    """eslint's per-message findings, flattened — and, for a rule eslint knows
    how to fix, a `_fix` block so the pull request can carry the fix as a
    suggestion.

    eslint reports a fix as a pair of character offsets into the file. Nothing
    downstream speaks offsets, so the translation happens here, once, where the
    file that produced them is at hand.
    """
    out: list[dict] = []
    for res in results:
        if not isinstance(res, dict):
            continue
        rel = relpath(res.get("filePath", ""), workdir)
        source: str | None = None
        for m in res.get("messages") or []:
            if not isinstance(m, dict):
                continue
            item = _item(m, rel)
            rng = _fix_range(m)
            if rng:
                if source is None:  # read once per file, only if a fix needs it
                    source = _read(workdir, rel)
                edit = suggest.utf16_edit(source, rng[0], rng[1], m["fix"].get("text"))
                if edit:
                    item["_fix"] = {"edits": [edit]}
            out.append(item)
    return out


def _eslint_counts(results: list) -> tuple[int, int]:
    """(errors, warnings) across eslint's per-file results."""
    return (
        sum(r.get("errorCount", 0) for r in results),
        sum(r.get("warningCount", 0) for r in results),
    )


def _read(workdir: str, rel: str) -> str:
    try:
        return (Path(workdir) / rel).read_text(errors="replace")
    except (OSError, ValueError):
        return ""


class EslintGate:
    name = "eslint"
    blocking = False
    langs = frozenset({"node", "ts"})

    async def run(self, ctx: GateContext) -> GateResult:
        if _no_pkg(ctx):
            return GateResult(self.name, GateOutcome.PASS, 1.0, "node: no package.json")
        if tool_missing("npx"):
            return unavailable(self.name, "npx/node not installed — skipped")
        rc, out, _err = await run_tool(
            ["npx", "--no-install", "eslint", "-f", "json", "."], ctx.workdir
        )
        if (to := timeout_result(self.name, rc)) is not None:
            return to
        if not (out or "").strip():
            # npx --no-install printed nothing → eslint isn't installed in the project.
            return unavailable(
                self.name, "eslint: not installed in project (npm i eslint) — skipped"
            )
        results = parsed(out, "")
        if results is None:
            return unavailable(self.name, "eslint: not configured in project — skipped")
        errors, warns = _eslint_counts(results)
        total = errors + warns
        if total == 0:
            return GateResult(self.name, GateOutcome.PASS, 1.0, "eslint: clean")
        return scored(
            self.name,
            total,
            f"eslint: {errors} error(s), {warns} warning(s)",
            _messages(results, ctx.workdir),
            fail=errors > 0,
        )

    async def fix(self, ctx: GateContext) -> tuple[bool, str]:
        """Apply eslint's autofixes in place (--fix). Called only under `--fix`.

        eslint exits non-zero whenever anything unfixable is left over, which is
        the normal outcome of a successful fix run — so what it rewrote is not
        read from the exit code but measured from the worktree by the runner."""
        if _no_pkg(ctx) or tool_missing("npx"):
            return (False, "eslint unavailable — nothing fixed")
        await run_tool(["npx", "--no-install", "eslint", "--fix", "."], ctx.workdir)
        return (False, "eslint --fix applied")


class TscGate:
    name = "tsc"
    blocking = False
    langs = frozenset({"ts"})

    async def run(self, ctx: GateContext) -> GateResult:
        if not (Path(ctx.workdir) / "tsconfig.json").exists():
            return GateResult(self.name, GateOutcome.PASS, 1.0, "tsc: no tsconfig.json")
        if tool_missing("npx"):
            return unavailable(self.name, "npx/node not installed — skipped")
        rc, out, err = await run_tool(
            ["npx", "--no-install", "tsc", "--noEmit"], ctx.workdir
        )
        if (to := timeout_result(self.name, rc)) is not None:
            return to
        combined = merged(out, err)
        n = combined.count("error TS")
        if rc == 0:
            return GateResult(self.name, GateOutcome.PASS, 1.0, "tsc: no type errors")
        if n == 0:
            # non-zero exit but no TS errors parsed → tsc missing or misconfigured, not a clean pass.
            return unavailable(
                self.name,
                "tsc: could not run (not installed or misconfigured) — skipped",
            )
        tail = "\n".join(ln for ln in combined.splitlines() if "error TS" in ln)[:1000]
        return scored(
            self.name,
            n,
            f"tsc: {n} type error(s)",
            [{"errors": tail}],
            fail=n > 10,
            cap=20,
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
            return unavailable(self.name, "npm/node not installed — skipped")
        rc, out, err = await run_tool(["npm", "test", "--silent"], ctx.workdir)
        if (to := timeout_result(self.name, rc)) is not None:
            return to
        if rc == 0:
            return GateResult(self.name, GateOutcome.PASS, 1.0, "npm test: passed")
        tail = "\n".join(((out or "") + (err or "")).strip().splitlines()[-5:])
        return GateResult(
            self.name, GateOutcome.FAIL, 0.0, f"npm test: failed — {tail}"
        )
