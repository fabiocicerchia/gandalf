"""Python quality gates beyond lint: type checking, dead code, format drift."""

from __future__ import annotations

from gandalf.base import GateContext, GateOutcome, GateResult
from gandalf.plugins import (
    _scan_targets,
    missing_result,
    run_tool,
    timeout_result,
    tool_missing,
)

# More than this many issues fails rather than warns.
MAX_ISSUES = 10


def _has_python(ctx: GateContext) -> bool:
    return any(t == "." or t.endswith(".py") for t in _scan_targets(ctx, py_only=True))


class MypyGate:
    name = "mypy"
    blocking = False
    langs = frozenset({"python"})

    async def run(self, ctx: GateContext) -> GateResult:
        if (m := missing_result(self.name, "mypy")) is not None:
            return m
        if not _has_python(ctx):
            return GateResult(self.name, GateOutcome.PASS, 1.0, "mypy: no Python files")
        rc, out, _err = await run_tool(
            [
                "mypy",
                "--ignore-missing-imports",
                "--no-error-summary",
                "--no-color-output",
                "--show-error-codes",
                # Don't drop a .mypy_cache into the scanned repo (matches ruff's
                # --no-cache); also avoids a stale root-owned cache breaking reruns.
                "--cache-dir=/dev/null",
                *_scan_targets(ctx, py_only=True),
            ],
            ctx.workdir,
        )
        if (to := timeout_result(self.name, rc)) is not None:
            return to
        errors = [ln for ln in (out or "").splitlines() if ": error:" in ln]
        n = len(errors)
        if n == 0:
            return GateResult(self.name, GateOutcome.PASS, 1.0, "mypy: no type errors")
        score = max(0.0, 1.0 - min(n, 20) / 20)
        outcome = GateOutcome.FAIL if n > MAX_ISSUES else GateOutcome.WARN
        return GateResult(
            self.name,
            outcome,
            score,
            f"mypy: {n} type error(s)",
            [{"error": e} for e in errors],
        )


class VultureGate:
    name = "vulture"
    blocking = False
    langs = frozenset({"python"})

    async def run(self, ctx: GateContext) -> GateResult:
        if (m := missing_result(self.name, "vulture")) is not None:
            return m
        if not _has_python(ctx):
            return GateResult(self.name, GateOutcome.PASS, 1.0, "vulture: no Python files")
        rc, out, _ = await run_tool(
            ["vulture", "--min-confidence", "80", *_scan_targets(ctx, py_only=True)],
            ctx.workdir,
        )
        if (to := timeout_result(self.name, rc)) is not None:
            return to
        findings = [ln for ln in (out or "").splitlines() if ln.strip()]
        n = len(findings)
        if n == 0:
            return GateResult(self.name, GateOutcome.PASS, 1.0, "vulture: no dead code")
        score = max(0.0, 1.0 - min(n, 20) / 20)
        # Dead code is a smell, not a defect — cap at WARN.
        return GateResult(
            self.name,
            GateOutcome.WARN,
            score,
            f"vulture: {n} unused item(s)",
            [{"finding": f} for f in findings],
        )


class FormatGate:
    """`ruff format --check` — reports formatting drift (does not rewrite)."""

    name = "format"
    blocking = False
    langs = frozenset({"python"})

    async def run(self, ctx: GateContext) -> GateResult:
        if (m := missing_result(self.name, "ruff")) is not None:
            return m
        if not _has_python(ctx):
            return GateResult(self.name, GateOutcome.PASS, 1.0, "format: no Python files")
        rc, out, _ = await run_tool(
            [
                "ruff",
                "format",
                "--no-cache",
                "--check",
                *_scan_targets(ctx, py_only=True),
            ],
            ctx.workdir,
        )
        if (to := timeout_result(self.name, rc)) is not None:
            return to
        drift = [ln for ln in (out or "").splitlines() if ln.startswith("Would reformat")]
        if rc == 0 or not drift:
            return GateResult(self.name, GateOutcome.PASS, 1.0, "format: all files formatted")
        n = len(drift)
        score = max(0.0, 1.0 - min(n, 10) / 10)
        return GateResult(
            self.name,
            GateOutcome.WARN,
            score,
            f"format: {n} file(s) need formatting",
            [{"file": d} for d in drift],
        )

    async def fix(self, ctx: GateContext) -> tuple[bool, str]:
        """Rewrite files with `ruff format` (no --check). Called only under `--fix`."""
        if tool_missing("ruff"):
            return (False, "ruff unavailable — nothing formatted")
        _rc, out, err = await run_tool(
            ["ruff", "format", "--no-cache", *_scan_targets(ctx, py_only=True)],
            ctx.workdir,
        )
        line = next(
            (ln for ln in (out + err).splitlines() if "reformatted" in ln.lower()),
            "",
        )
        changed = "reformatted" in (out + err).lower() and not line.startswith("0 ")
        return (changed, line or "format: nothing to reformat")
