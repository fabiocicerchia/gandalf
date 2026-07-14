"""Postgres migration-safety gate (squawk) — flags unsafe DDL (blocking locks,
dropped columns, missing concurrent indexes, …). Self-skips without .sql files.
Best on migration files; on non-migration SQL it degrades to WARN gracefully."""

from __future__ import annotations

import json
from pathlib import Path

from gandalf.base import GateContext, GateOutcome, GateResult
from gandalf.plugins import run_tool, timeout_result, missing_result

_SKIP = (".venv", "node_modules", "llama.cpp", ".git", "reports")


class SquawkGate:
    name = "squawk"
    blocking = False
    langs = frozenset({"sql"})
    category = "Database"

    async def run(self, ctx: GateContext) -> GateResult:
        root = Path(ctx.workdir)
        sqls = [
            str(p.relative_to(root))
            for p in root.rglob("*.sql")
            if not any(s in p.parts for s in _SKIP)
        ]
        if not sqls:
            return GateResult(self.name, GateOutcome.PASS, 1.0, "squawk: no SQL files")
        if (m := missing_result(self.name, "squawk")) is not None:
            return m
        rc, out, _ = await run_tool(
            ["squawk", "--reporter", "json", *sqls], ctx.workdir
        )
        if (to := timeout_result(self.name, rc)) is not None:
            return to
        try:
            data = json.loads(out or "[]")
        except json.JSONDecodeError:
            return GateResult(
                self.name,
                GateOutcome.WARN,
                0.8,
                "squawk: unparsable output (not Postgres migrations?) — skipped",
            )
        findings = []
        for v in data if isinstance(data, list) else []:
            msgs = v.get("messages") or []
            detail = (
                msgs[0].get("message", "") if msgs and isinstance(msgs[0], dict) else ""
            )
            rule = v.get("rule_name", "")
            findings.append(
                {
                    "file": v.get("file", ""),
                    "line": v.get("line", ""),
                    "message": f"{rule}: {detail}" if detail else rule,
                }
            )
        n = len(findings)
        if n == 0:
            return GateResult(
                self.name, GateOutcome.PASS, 1.0, "squawk: migrations look safe"
            )
        score = max(0.0, 1.0 - min(n, 10) / 10)
        # Migration risk is advisory (context-dependent) — cap at WARN.
        return GateResult(
            self.name,
            GateOutcome.WARN,
            score,
            f"squawk: {n} migration warning(s)",
            findings,
        )
