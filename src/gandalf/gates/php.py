"""PHP gates: syntax, phpcs, composer audit, phpunit.

Like Ruby, PHP has nothing to compile, so the build slot is `php -l` over the
files in scope. Lint and tests prefer the project's own `vendor/bin/` binaries
over anything global — a repo pins the phpcs and phpunit it expects to be judged
by, and a different global version reports different things.

`composer audit` needs no plugin and no extra install: it is part of Composer,
and it reads the same lock file the generic osv_scanner/trivy gates do — but it
knows Packagist's advisory feed directly.
"""

from __future__ import annotations

import json
from pathlib import Path

from gandalf.base import GateContext, GateOutcome, GateResult
from gandalf.gates._toolchain import (
    ToolchainGate,
    counted,
    exit_code,
    per_file,
    project_dir,
    tail,
)
from gandalf.plugins import (
    run_tool,
    timeout_result,
    tool_missing,
    unavailable,
)

_MARKERS = ("composer.json", "*.php")
_LANGS = frozenset({"php"})


def _vendored(root: str, binary: str) -> str | None:
    """The project's own `vendor/bin/<binary>`, a global one, or neither."""
    local = Path(root) / "vendor" / "bin" / binary
    if local.is_file():
        return str(local)
    return None if tool_missing(binary) else binary


class PhpSyntaxGate(ToolchainGate):
    """`php -l` over the PHP in scope. Blocking — a parse error is never amber."""

    name = "php_syntax"
    blocking = True
    ecosystem = "php"
    langs = _LANGS
    markers = _MARKERS
    binary = "php"

    async def check(self, ctx: GateContext, root: str) -> GateResult:
        return await per_file(
            self.name, ["php", "-l", "-n"], ctx, (".php",), label="php -l"
        )


class PhpcsGate(ToolchainGate):
    """PHP_CodeSniffer — style/lint against the repo's standard, else PSR-12."""

    name = "phpcs"
    ecosystem = "php"
    langs = _LANGS
    markers = _MARKERS

    def _standard(self, root: str) -> list[str]:
        # A repo shipping a ruleset has already said what clean means here.
        for rel in ("phpcs.xml", "phpcs.xml.dist", "ruleset.xml"):
            if (Path(root) / rel).is_file():
                return []
        return ["--standard=PSR12"]

    async def check(self, ctx: GateContext, root: str) -> GateResult:
        phpcs = _vendored(root, "phpcs")
        if phpcs is None:
            return self.missing("phpcs")
        rc, out, err = await run_tool(
            [phpcs, "--report=json", "--no-colors", *self._standard(root), "."], root
        )
        if (to := timeout_result(self.name, rc)) is not None:
            return to
        try:
            data = json.loads(out or "{}")
        except json.JSONDecodeError:
            return unavailable(
                self.name, f"phpcs: did not run — {tail((out or '') + (err or ''), 2)}"
            )
        findings = [
            {
                "file": path,
                "line": m.get("line", 0),
                "column": m.get("column", 0),
                "rule": m.get("source", ""),
                "message": m.get("message", ""),
                "severity": (m.get("type") or "").lower(),
            }
            for path, f in (data.get("files") or {}).items()
            for m in f.get("messages") or []
        ]
        totals = data.get("totals") or {}
        n = totals.get("errors", 0) + totals.get("warnings", 0) or len(findings)
        return counted(self.name, n, "phpcs", findings[:50], noun="violation(s)")

    async def fix(self, ctx: GateContext) -> tuple[bool, str]:
        """`phpcbf` — the sniffer's own fixer. Under `--fix`."""
        root = project_dir(ctx, self.markers)
        if root is None:
            return (False, "phpcs unavailable — nothing fixed")
        phpcbf = _vendored(root, "phpcbf")
        if phpcbf is None:
            return (False, "phpcbf unavailable — nothing fixed")
        # phpcbf exits 1 when it fixed something and 2 when it could not fix
        # everything, so what it rewrote is read from the worktree, not the code.
        await run_tool([phpcbf, "--no-colors", *self._standard(root), "."], root)
        return (False, "phpcbf applied")


class ComposerAuditGate(ToolchainGate):
    """`composer audit` — Packagist security advisories for the locked deps."""

    name = "composer_audit"
    ecosystem = "php"
    langs = _LANGS
    markers = ("composer.lock",)
    binary = "composer"

    async def check(self, ctx: GateContext, root: str) -> GateResult:
        rc, out, err = await run_tool(
            ["composer", "audit", "--format=json", "--no-interaction"], root
        )
        if (to := timeout_result(self.name, rc)) is not None:
            return to
        try:
            data = json.loads(out or "{}")
        except json.JSONDecodeError:
            return unavailable(
                self.name,
                f"composer audit: did not run — {tail((out or '') + (err or ''), 2)}",
            )
        advisories = [
            {
                "message": f"{pkg}: {a.get('title', '')}",
                "url": a.get("link", ""),
                "severity": a.get("severity", ""),
            }
            for pkg, items in (data.get("advisories") or {}).items()
            for a in items
        ]
        if not advisories:
            return GateResult(
                self.name, GateOutcome.PASS, 1.0, "composer audit: no known advisories"
            )
        n = len(advisories)
        score = max(0.0, 1.0 - min(n, 10) / 10)
        return GateResult(
            self.name,
            GateOutcome.FAIL,
            score,
            f"composer audit: {n} advisory(ies)",
            advisories[:50],
        )


class PhpunitGate(ToolchainGate):
    name = "php_test"
    ecosystem = "php"
    langs = _LANGS
    markers = _MARKERS

    async def check(self, ctx: GateContext, root: str) -> GateResult:
        phpunit = _vendored(root, "phpunit")
        if phpunit is None:
            return self.missing("phpunit")
        if not any(
            (Path(root) / rel).is_file() for rel in ("phpunit.xml", "phpunit.xml.dist")
        ):
            return GateResult(
                self.name, GateOutcome.PASS, 1.0, "php: no phpunit configuration"
            )
        return await exit_code(
            self.name,
            [phpunit, "--no-coverage", "--colors=never"],
            root,
            ok="phpunit: passed",
            bad="phpunit: failed",
            fail_re=r"^\d+\)\s",
        )
