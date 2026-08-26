"""SQL lint gate (sqlfluff). Self-skips when the repo has no .sql files.
Dialect via GANDALF_SQL_DIALECT (default ansi)."""

from __future__ import annotations

import json
import os
from pathlib import Path

from gandalf.base import GateContext, GateOutcome, GateResult
from gandalf.plugins import missing_result, run_tool, timeout_result, tool_missing

_SKIP = (".venv", "node_modules", "llama.cpp", ".git", "reports")
_DIALECT = os.environ.get("GANDALF_SQL_DIALECT", "ansi")


def _sql_files(root: Path) -> list[str]:
    return [
        str(p.relative_to(root))
        for p in root.rglob("*.sql")
        if not any(s in p.parts for s in _SKIP)
    ]


class SqlfluffGate:
    name = "sqlfluff"
    blocking = False
    langs = frozenset({"sql"})
    category = "Database"

    async def run(self, ctx: GateContext) -> GateResult:
        sqls = _sql_files(Path(ctx.workdir))
        if not sqls:
            return GateResult(
                self.name, GateOutcome.PASS, 1.0, "sqlfluff: no SQL files"
            )
        if (m := missing_result(self.name, "sqlfluff")) is not None:
            return m
        rc, out, _ = await run_tool(
            ["sqlfluff", "lint", "--format", "json", "--dialect", _DIALECT, *sqls],
            ctx.workdir,
        )
        if (to := timeout_result(self.name, rc)) is not None:
            return to
        try:
            data = json.loads(out or "[]")
        except json.JSONDecodeError:
            return GateResult(
                self.name, GateOutcome.WARN, 0.8, "sqlfluff: unparsable output"
            )
        findings = [
            {
                "file": f.get("filepath", ""),
                "line": v.get("line_no", ""),
                "message": f"[{v.get('code', '')}] {v.get('description', '')}",
            }
            for f in data
            for v in f.get("violations", [])
        ]
        n = len(findings)
        if n == 0:
            return GateResult(
                self.name, GateOutcome.PASS, 1.0, f"sqlfluff: {len(sqls)} file(s) clean"
            )
        score = max(0.0, 1.0 - min(n, 20) / 20)
        outcome = GateOutcome.WARN if n <= 10 else GateOutcome.FAIL
        return GateResult(
            self.name, outcome, score, f"sqlfluff: {n} lint issue(s)", findings
        )

    async def fix(self, ctx: GateContext) -> tuple[bool, str]:
        """Rewrite the SQL with `sqlfluff fix`. Called only under `--fix`.

        `--force` is tried first and dropped on the retry: sqlfluff 2.x prompts
        before writing unless it is passed, and sqlfluff 3.x removed the flag
        because it stopped prompting. Asking the tool which it is costs another
        subprocess; letting the wrong one fail and retrying costs the same and
        cannot go stale.
        """
        sqls = _sql_files(Path(ctx.workdir))
        if not sqls:
            return (False, "sqlfluff: no SQL files")
        if tool_missing("sqlfluff"):
            return (False, "sqlfluff unavailable — nothing fixed")
        base = ["sqlfluff", "fix", "--disable-progress-bar", "--dialect", _DIALECT]
        rc, out, err = await run_tool([*base, "--force", *sqls], ctx.workdir)
        if rc != 0 and "no such option" in (out + err).lower():
            rc, out, err = await run_tool([*base, *sqls], ctx.workdir)
        if rc < 0:
            return (False, "sqlfluff: did not run")
        return (False, f"sqlfluff fix: {len(sqls)} file(s) processed")
