"""Language-agnostic lint gates: shellcheck, actionlint, yamllint, codespell.
All available via the gandalf-tools image, so no host installs needed.
"""

from __future__ import annotations

import json
from pathlib import Path

from gandalf.base import GateContext, GateOutcome, GateResult
from gandalf.plugins import run_tool, timeout_result, missing_result

_SKIP = (".venv", "node_modules", "llama.cpp", ".git", "reports")


def _find(root: Path, *globs: str) -> list[str]:
    hits: list[str] = []
    for g in globs:
        for p in root.rglob(g):
            if not any(s in p.parts for s in _SKIP) and p.is_file():
                hits.append(str(p.relative_to(root)))
    return hits


class ShellcheckGate:
    name = "shellcheck"
    blocking = False
    langs = frozenset({"shell"})

    async def run(self, ctx: GateContext) -> GateResult:
        if (m := missing_result(self.name, "shellcheck")) is not None:
            return m
        scripts = _find(Path(ctx.workdir), "*.sh", "*.bash")
        if not scripts:
            return GateResult(
                self.name, GateOutcome.PASS, 1.0, "shellcheck: no shell scripts"
            )
        rc, out, _ = await run_tool(
            ["shellcheck", "--format=json", *scripts], ctx.workdir
        )
        if (to := timeout_result(self.name, rc)) is not None:
            return to
        try:
            findings = json.loads(out or "[]")
        except json.JSONDecodeError:
            findings = []
        n = len(findings)
        if n == 0:
            return GateResult(
                self.name,
                GateOutcome.PASS,
                1.0,
                f"shellcheck: {len(scripts)} script(s) clean",
            )
        errors = sum(1 for f in findings if f.get("level") == "error")
        score = max(0.0, 1.0 - min(n, 10) / 10)
        outcome = GateOutcome.FAIL if errors > 0 else GateOutcome.WARN
        return GateResult(
            self.name,
            outcome,
            score,
            f"shellcheck: {n} issue(s), {errors} error(s)",
            findings,
        )


class ActionlintGate:
    name = "actionlint"
    blocking = False

    async def run(self, ctx: GateContext) -> GateResult:
        wf = Path(ctx.workdir) / ".github" / "workflows"
        if not wf.is_dir() or not any(wf.glob("*.y*ml")):
            return GateResult(
                self.name, GateOutcome.PASS, 1.0, "actionlint: no workflows"
            )
        if (m := missing_result(self.name, "actionlint")) is not None:
            return m
        rc, out, _ = await run_tool(["actionlint", "-oneline"], ctx.workdir)
        if (to := timeout_result(self.name, rc)) is not None:
            return to
        issues = [ln for ln in (out or "").splitlines() if ln.strip()]
        n = len(issues)
        if n == 0:
            return GateResult(
                self.name, GateOutcome.PASS, 1.0, "actionlint: workflows clean"
            )
        score = max(0.0, 1.0 - min(n, 10) / 10)
        outcome = GateOutcome.FAIL if n > 3 else GateOutcome.WARN
        return GateResult(
            self.name,
            outcome,
            score,
            f"actionlint: {n} issue(s)",
            [{"issue": i} for i in issues],
        )


class YamllintGate:
    name = "yamllint"
    blocking = False
    langs = frozenset({"yaml"})

    async def run(self, ctx: GateContext) -> GateResult:
        if (m := missing_result(self.name, "yamllint")) is not None:
            return m
        yamls = _find(Path(ctx.workdir), "*.yml", "*.yaml")
        if not yamls:
            return GateResult(
                self.name, GateOutcome.PASS, 1.0, "yamllint: no YAML files"
            )
        # Honor a repo's own yamllint config if it ships one (auto-discovered from
        # the workdir); otherwise fall back to the built-in relaxed preset.
        has_cfg = any(
            (Path(ctx.workdir) / c).is_file()
            for c in (".yamllint", ".yamllint.yaml", ".yamllint.yml")
        )
        cfg = [] if has_cfg else ["-d", "relaxed"]
        rc, out, _ = await run_tool(
            ["yamllint", "-f", "parsable", *cfg, *yamls], ctx.workdir
        )
        if (to := timeout_result(self.name, rc)) is not None:
            return to
        lines = [ln for ln in (out or "").splitlines() if ln.strip()]
        errors = [ln for ln in lines if "[error]" in ln]
        n = len(lines)
        if n == 0:
            return GateResult(
                self.name,
                GateOutcome.PASS,
                1.0,
                f"yamllint: {len(yamls)} file(s) clean",
            )
        score = max(0.0, 1.0 - min(n, 10) / 10)
        outcome = GateOutcome.FAIL if errors else GateOutcome.WARN
        return GateResult(
            self.name,
            outcome,
            score,
            f"yamllint: {n} issue(s), {len(errors)} error(s)",
            [{"issue": ln} for ln in lines],
        )


class CodespellGate:
    name = "codespell"
    blocking = False

    async def run(self, ctx: GateContext) -> GateResult:
        if (m := missing_result(self.name, "codespell")) is not None:
            return m
        rc, out, _ = await run_tool(
            [
                "codespell",
                "--skip",
                "*.lock,*.min.js,.git,.venv,node_modules,llama.cpp,reports,*.svg",
                ".",
            ],
            ctx.workdir,
        )
        if (to := timeout_result(self.name, rc)) is not None:
            return to
        typos = [ln for ln in (out or "").splitlines() if "==>" in ln]
        n = len(typos)
        if n == 0:
            return GateResult(self.name, GateOutcome.PASS, 1.0, "codespell: no typos")
        score = max(0.0, 1.0 - min(n, 20) / 20)
        # Spelling is cosmetic — cap at WARN.
        return GateResult(
            self.name,
            GateOutcome.WARN,
            score,
            f"codespell: {n} typo(s)",
            [{"typo": t.strip()} for t in typos],
        )
