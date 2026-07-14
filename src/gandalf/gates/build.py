"""Build gate: verify the changed Python actually compiles (syntax/parse pass).
Blocking — a syntactically broken tree must never pass. Ported from ai-harness.
"""

from __future__ import annotations

from pathlib import Path

from gandalf.base import GateContext, GateOutcome, GateResult
from gandalf.plugins import tracked_files


class BuildGate:
    name = "build"
    blocking = True
    langs = frozenset({"python"})

    async def run(self, ctx: GateContext) -> GateResult:
        py_files = [f for f in ctx.changed_files if f.endswith(".py")]
        if not py_files:
            # Whole-tree scope has no changed_files → compile every tracked .py.
            # Tracked-only skips untracked/vendored trees (.venv, node_modules,
            # a vendored llama.cpp) without hardcoding their names.
            py_files = [f for f in tracked_files(ctx.workdir) if f.endswith(".py")]
        if not py_files:
            return GateResult(self.name, GateOutcome.PASS, 1.0, "no Python files")

        root = Path(ctx.workdir)
        errors: list[dict[str, object]] = []
        for rel in py_files:
            path = root / rel
            try:
                source = path.read_text(errors="replace")
            except OSError:
                continue  # deleted by the diff — nothing to compile
            try:
                compile(source, rel, "exec")
            except SyntaxError as exc:
                errors.append(
                    {
                        "path": rel,
                        "line": exc.lineno,
                        "message": f"{exc.msg} (line {exc.lineno})",
                    }
                )

        if errors:
            first = errors[0]
            summary = f"{len(errors)} file(s) fail to compile — {first['path']}: {first['message']}"
            return GateResult(self.name, GateOutcome.FAIL, 0.0, summary, errors)
        return GateResult(
            self.name, GateOutcome.PASS, 1.0, f"{len(py_files)} file(s) compile"
        )
