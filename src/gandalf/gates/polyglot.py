"""Language-agnostic lint gates: shellcheck, actionlint, yamllint, codespell.
All available via the gandalf-tools image, so no host installs needed.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from gandalf.base import GateContext, GateOutcome, GateResult
from gandalf.gates._toolchain import named, nonblank, scored
from gandalf.plugins import missing_result, run_tool, timeout_result, tool_missing

# What codespell must not read. One list, so `--fix` corrects exactly the files
# the gate scored — a fixer with a wider reach would rewrite vendored trees.
_CODESPELL_SKIP = "*.lock,*.min.js,.git,.venv,node_modules,llama.cpp,reports,*.svg"


# More than a few findings fails the gate.
MAX_FINDINGS = 3


def _yamllint_config(workdir: str) -> list[str]:
    """Honor a repo's own yamllint config if it ships one (auto-discovered from
    the workdir); otherwise fall back to the built-in relaxed preset."""
    own = (".yamllint", ".yamllint.yaml", ".yamllint.yml")
    if any((Path(workdir) / c).is_file() for c in own):
        return []
    return ["-d", "relaxed"]


def _spellable(ctx: GateContext) -> list[str]:
    """The files codespell may read: tracked and not excluded, never `.`. Walking
    the directory would drag in whatever git ignores — build output, a docs site,
    a virtualenv — and `--fix` would then rewrite it."""
    return named(ctx, "*") or ["."]


class ShellcheckGate:
    name = "shellcheck"
    blocking = False
    langs = frozenset({"shell"})

    async def run(self, ctx: GateContext) -> GateResult:
        if (m := missing_result(self.name, "shellcheck")) is not None:
            return m
        scripts = named(ctx, "*.sh", "*.bash")
        if not scripts:
            return GateResult(self.name, GateOutcome.PASS, 1.0, "shellcheck: no shell scripts")
        rc, out, _ = await run_tool(["shellcheck", "--format=json", *scripts], ctx.workdir)
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

    async def fix(self, ctx: GateContext) -> tuple[bool, str]:
        """Apply shellcheck's own fixes. Called only under `--fix`.

        shellcheck cannot rewrite a file itself — `--format=diff` is how it
        offers the change, and `git apply` is what puts it on disk. Only the
        replacements shellcheck considers safe reach that formatter, so this
        stays a conservative rewrite; the whole patch is applied or none of it
        is, which is what keeps a half-applied quoting fix off the disk.
        """
        if tool_missing("shellcheck"):
            return (False, "shellcheck unavailable — nothing fixed")
        scripts = named(ctx, "*.sh", "*.bash")
        if not scripts:
            return (False, "shellcheck: no shell scripts")
        _rc, out, _err = await run_tool(["shellcheck", "--format=diff", *scripts], ctx.workdir)
        if "@@" not in (out or ""):
            return (False, "shellcheck: nothing it can fix automatically")
        with tempfile.NamedTemporaryFile("w", suffix=".patch", delete=False, encoding="utf-8") as fh:
            fh.write(out if out.endswith("\n") else out + "\n")
            patch = fh.name
        try:
            rc, _o, err = await run_tool(["git", "apply", patch], ctx.workdir)
        finally:
            Path(patch).unlink()  # noqa: ASYNC240 — one stat, straight after a subprocess that took seconds — not worth a thread hop
        if rc != 0:
            return (False, f"shellcheck: patch rejected — {(err or '').strip()[:120]}")
        return (True, "shellcheck: applied its suggested fixes")


class ActionlintGate:
    name = "actionlint"
    blocking = False

    async def run(self, ctx: GateContext) -> GateResult:
        wf = Path(ctx.workdir) / ".github" / "workflows"
        if not wf.is_dir() or not any(wf.glob("*.y*ml")):
            return GateResult(self.name, GateOutcome.PASS, 1.0, "actionlint: no workflows")
        if (m := missing_result(self.name, "actionlint")) is not None:
            return m
        rc, out, _ = await run_tool(["actionlint", "-oneline"], ctx.workdir)
        if (to := timeout_result(self.name, rc)) is not None:
            return to
        issues = nonblank(out)
        n = len(issues)
        if n == 0:
            return GateResult(self.name, GateOutcome.PASS, 1.0, "actionlint: workflows clean")
        return scored(
            self.name,
            n,
            f"actionlint: {n} issue(s)",
            [{"issue": i} for i in issues],
            fail=n > MAX_FINDINGS,
        )


class YamllintGate:
    name = "yamllint"
    blocking = False
    langs = frozenset({"yaml"})

    async def run(self, ctx: GateContext) -> GateResult:
        if (m := missing_result(self.name, "yamllint")) is not None:
            return m
        yamls = named(ctx, "*.yml", "*.yaml")
        if not yamls:
            return GateResult(self.name, GateOutcome.PASS, 1.0, "yamllint: no YAML files")
        rc, out, _ = await run_tool(
            ["yamllint", "-f", "parsable", *_yamllint_config(ctx.workdir), *yamls],
            ctx.workdir,
        )
        if (to := timeout_result(self.name, rc)) is not None:
            return to
        issues = nonblank(out)
        errors = [ln for ln in issues if "[error]" in ln]
        n = len(issues)
        if n == 0:
            return GateResult(
                self.name,
                GateOutcome.PASS,
                1.0,
                f"yamllint: {len(yamls)} file(s) clean",
            )
        return scored(
            self.name,
            n,
            f"yamllint: {n} issue(s), {len(errors)} error(s)",
            [{"issue": ln} for ln in issues],
            fail=bool(errors),
        )


class CodespellGate:
    name = "codespell"
    blocking = False

    async def run(self, ctx: GateContext) -> GateResult:
        if (m := missing_result(self.name, "codespell")) is not None:
            return m
        rc, out, _ = await run_tool(["codespell", "--skip", _CODESPELL_SKIP, *_spellable(ctx)], ctx.workdir)
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

    async def fix(self, ctx: GateContext) -> tuple[bool, str]:
        """Correct the typos in place (`codespell -w`). Called only under `--fix`.

        A typo with more than one plausible correction is left alone by the tool
        itself, so this only ever writes the corrections codespell is sure of."""
        if tool_missing("codespell"):
            return (False, "codespell unavailable — nothing fixed")
        rc, out, err = await run_tool(
            [
                "codespell",
                "--write-changes",
                "--skip",
                _CODESPELL_SKIP,
                *_spellable(ctx),
            ],
            ctx.workdir,
        )
        if rc < 0:
            return (False, "codespell: did not run")
        # Deduped: codespell reports each correction on both streams, and
        # run_tool captures them separately, so a plain count doubles.
        fixed = {ln.strip() for ln in ((out or "") + (err or "")).splitlines() if "==>" in ln}
        return (bool(fixed), f"codespell: {len(fixed)} typo(s) corrected")
