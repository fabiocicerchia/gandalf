"""CodeQL SAST gate — GitHub's semantic code-analysis engine (https://codeql.github.com/).

Unlike the pattern-based scanners (semgrep, bandit) this one builds a queryable
*database* from the source and runs GitHub's standard "code-scanning" query packs
against it — the same analysis GitHub Advanced Security runs on pull requests. It
catches data-flow / taint issues (injection, path traversal, unsafe deserialization,
…) that line-level linters miss.

CodeQL ships as a large CLI bundle, not a pip/apt package, so it's NOT baked into the
gandalf-tools image. Resolution mirrors the `kics` gate:

1. host `codeql` binary on PATH → run it directly;
2. else Docker present → run the official-style bundle image (override with
   GANDALF_CODEQL_IMAGE, default `mcr.microsoft.com/cstsectools/codeql-container`);
3. else → 🟡 WARN (skipped).

Only the languages in scope are analyzed, mapped to CodeQL language ids:
python→python, node/ts→javascript (one DB covers JS+TS), go→go. Interpreted
languages need no build; Go is autobuilt (`go build`) — if that build can't run the
database create fails and that language degrades to WARN, the others still run.

Building a database + downloading query packs is slow and network-bound, so this
gate gets its own longer budget: GANDALF_CODEQL_TIMEOUT (seconds, default 600). If a
step exceeds it the language is skipped rather than hanging the run.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile

from gandalf.base import GateContext, GateOutcome, GateResult
from gandalf.plugins import run_tool, timeout_result
from gandalf.scope import _classify

_IMAGE = os.environ.get(
    "GANDALF_CODEQL_IMAGE", "mcr.microsoft.com/cstsectools/codeql-container:latest"
)
_TIMEOUT = int(os.environ.get("GANDALF_CODEQL_TIMEOUT", "600"))

# gandalf language tag → CodeQL language id. node and ts both map to "javascript"
# (a single DB covers JS + TS), so the set collapses duplicates for us.
_LANG_MAP = {
    "python": "python",
    "go": "go",
    "node": "javascript",
    "ts": "javascript",
}


class CodeqlGate:
    name = "codeql"
    blocking = False
    langs = frozenset(_LANG_MAP)

    async def run(self, ctx: GateContext) -> GateResult:
        have_host = shutil.which("codeql") is not None
        if not have_host and not shutil.which("docker"):
            return GateResult(
                self.name,
                GateOutcome.WARN,
                0.8,
                "codeql unavailable (no host binary and no docker) — skipped",
            )

        detected = _classify(ctx.changed_files) if ctx.changed_files else None
        # Whole-tree scope: _classify of changed_files is empty, so fall back to the
        # languages CodeQL can build here (all of them) — the per-language create
        # simply produces an empty DB for a language with no sources.
        cq_langs = sorted(
            {_LANG_MAP[t] for t in (detected or set(_LANG_MAP)) if t in _LANG_MAP}
        )
        if not cq_langs:
            return GateResult(
                self.name,
                GateOutcome.PASS,
                1.0,
                "codeql: no supported language in scope",
            )

        work = tempfile.mkdtemp(prefix="gandalf-codeql-")
        ran: list[str] = []  # languages that produced a SARIF we could read
        findings: list[dict] = []
        errors = warnings = 0
        try:
            for lang in cq_langs:
                sarif = os.path.join(work, f"{lang}.sarif")
                if not await self._analyze(ctx, work, lang, sarif, have_host):
                    continue
                try:
                    with open(sarif, errors="replace") as fh:
                        data = json.load(fh)
                except (OSError, json.JSONDecodeError):
                    continue
                ran.append(lang)
                e, w, f = _parse_sarif(data)
                errors += e
                warnings += w
                findings.extend(f)
        finally:
            shutil.rmtree(work, ignore_errors=True)

        if not ran:
            return GateResult(
                self.name,
                GateOutcome.WARN,
                0.8,
                "codeql: no database analyzed (build/query-pack unavailable) — skipped",
            )

        n = errors + warnings
        langs_txt = "+".join(ran)
        if n == 0:
            return GateResult(
                self.name, GateOutcome.PASS, 1.0, f"codeql ({langs_txt}): clean"
            )
        score = max(0.0, 1.0 - min(n, 10) / 10)
        outcome = GateOutcome.FAIL if errors > 0 or n > 5 else GateOutcome.WARN
        return GateResult(
            self.name,
            outcome,
            score,
            f"codeql ({langs_txt}): {errors} error, {warnings} warning finding(s)",
            findings[:100],
        )

    async def _analyze(
        self, ctx: GateContext, work: str, lang: str, sarif: str, have_host: bool
    ) -> bool:
        """Create a DB and run the `<lang>-queries` code-scanning pack, writing SARIF
        to `sarif`. Returns True iff both steps succeeded (SARIF should now exist)."""
        db = os.path.join(work, f"db-{lang}")
        pack = f"codeql/{lang}-queries"
        if have_host:
            create = [
                "codeql",
                "database",
                "create",
                db,
                "--language",
                lang,
                "--source-root",
                ctx.workdir,
                "--overwrite",
                "--quiet",
            ]
            analyze = [
                "codeql",
                "database",
                "analyze",
                db,
                pack,
                "--format",
                "sarif-latest",
                "--output",
                sarif,
                "--download",
                "--quiet",
            ]
        else:
            base = [
                "docker",
                "run",
                "--rm",
                # The cstsectools image ships a broken ENTRYPOINT (setup.py is
                # non-executable, so it exits 126 before codeql runs). codeql is on
                # PATH, so bypass the entrypoint and invoke it directly.
                "--entrypoint",
                "",
                "--network",
                "host",
                "-v",
                f"{os.path.abspath(ctx.workdir)}:/src",
                "-v",
                f"{os.path.abspath(work)}:/work",
                "-w",
                "/src",
                _IMAGE,
            ]
            create = [
                *base,
                "codeql",
                "database",
                "create",
                f"/work/db-{lang}",
                "--language",
                lang,
                "--source-root",
                "/src",
                "--overwrite",
                "--quiet",
            ]
            analyze = [
                *base,
                "codeql",
                "database",
                "analyze",
                f"/work/db-{lang}",
                pack,
                "--format",
                "sarif-latest",
                "--output",
                f"/work/{lang}.sarif",
                "--download",
                "--quiet",
            ]

        rc, _o, _e = await run_tool(create, ctx.workdir, _TIMEOUT)
        if rc != 0 or timeout_result(self.name, rc) is not None:
            return False
        rc, _o, _e = await run_tool(analyze, ctx.workdir, _TIMEOUT)
        if rc != 0 or timeout_result(self.name, rc) is not None:
            return False
        return os.path.exists(sarif)


def _parse_sarif(data: dict) -> tuple[int, int, list[dict]]:
    """Pull (error-count, warning-count, findings) out of a SARIF 2.x document.
    `note`-level results are informational and don't count toward the score."""
    errors = warnings = 0
    findings: list[dict] = []
    for run in data.get("runs", []) or []:
        for res in run.get("results", []) or []:
            level = res.get("level", "warning")
            if level == "error":
                errors += 1
            elif level == "note":
                pass
            else:
                warnings += 1
            loc = (res.get("locations") or [{}])[0]
            phys = loc.get("physicalLocation", {}) or {}
            findings.append(
                {
                    "file": phys.get("artifactLocation", {}).get("uri", ""),
                    "line": phys.get("region", {}).get("startLine", ""),
                    "rule": res.get("ruleId", ""),
                    "message": f"[{level}] {res.get('message', {}).get('text', '')}",
                }
            )
    return errors, warnings, findings
