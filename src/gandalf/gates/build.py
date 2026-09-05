"""Build gate: verify the changed Python actually compiles (syntax/parse pass).
Blocking — a syntactically broken tree must never pass. Ported from ai-harness.
"""

from __future__ import annotations

from pathlib import Path

from gandalf.base import GateContext, GateOutcome, GateResult
from gandalf.plugins import ignore_patterns, is_ignored, scannable_files


def _syntax_errors(root: Path, rels: list[str]) -> list[dict[str, object]]:
    """Every file in `rels` that will not compile, with its parse error."""
    errors: list[dict[str, object]] = []
    for rel in rels:
        try:
            source = (root / rel).read_text(errors="replace")
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
    return errors


class BuildGate:
    name = "build"
    blocking = True
    langs = frozenset({"python"})

    async def run(self, ctx: GateContext) -> GateResult:
        pats = ignore_patterns(ctx.workdir)
        py_files = [f for f in ctx.changed_files if f.endswith(".py") and not is_ignored(f, pats)]
        if not py_files:
            # Whole-tree scope has no changed_files → compile every scannable .py.
            # Tracked-only skips untracked/vendored trees (.venv, node_modules,
            # a vendored llama.cpp) without hardcoding their names, and the
            # ignore patterns drop what the repo or the caller excluded.
            py_files = [f for f in scannable_files(ctx.workdir) if f.endswith(".py")]
        if not py_files:
            return GateResult(self.name, GateOutcome.PASS, 1.0, "no Python files")

        errors = _syntax_errors(Path(ctx.workdir), py_files)
        if errors:
            first = errors[0]
            summary = f"{len(errors)} file(s) fail to compile — {first['path']}: {first['message']}"
            return GateResult(self.name, GateOutcome.FAIL, 0.0, summary, errors)
        return GateResult(self.name, GateOutcome.PASS, 1.0, f"{len(py_files)} file(s) compile")
