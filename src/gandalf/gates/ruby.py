"""Ruby gates: syntax, rubocop, bundler-audit, test.

Ruby compiles nothing, so the build slot is a parse pass (`ruby -c`) over the
files in scope — the same thing gandalf's Python `build` gate does, for the same
reason: a tree that does not parse must never go green, and that check costs
nothing and needs no project setup.

Everything else is the ecosystem's standard tooling on the host: rubocop for
lint, bundler-audit for advisories against Gemfile.lock, rspec or rake for tests.
Each self-skips when its tool is not installed.
"""

from __future__ import annotations

from pathlib import Path

from gandalf.base import GateContext, GateOutcome, GateResult
from gandalf.gates._toolchain import (
    ToolchainGate,
    counted,
    exit_code,
    merged,
    parsed,
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

# A bare `*.rb` is enough to justify a parse check and nothing more: Ruby is a
# popular configuration DSL (mdl styles, Vagrantfile, Brewfile), and one of those
# in a Python repo must not drag a linter and a test runner in behind it. The
# gates that need a *project* ask for a project marker.
_ANY_RUBY = ("Gemfile", "*.gemspec", "Rakefile", ".rubocop.yml", "*.rb")
_MARKERS = ("Gemfile", "*.gemspec", "Rakefile", ".rubocop.yml")
_LANGS = frozenset({"ruby"})


class RubySyntaxGate(ToolchainGate):
    """`ruby -c` over the Ruby in scope. Blocking — a parse error is never amber."""

    name = "ruby_syntax"
    blocking = True
    ecosystem = "ruby"
    langs = _LANGS
    markers = _ANY_RUBY
    binary = "ruby"

    async def check(self, ctx: GateContext, root: str) -> GateResult:
        return await per_file(self.name, ["ruby", "-c"], ctx, (".rb",), label="ruby -c")


def _rubocop_findings(data: dict) -> list[dict]:
    """rubocop's per-file offence lists, flattened."""
    return [
        {
            "file": f.get("path", ""),
            "line": (o.get("location") or {}).get("line", 0),
            "column": (o.get("location") or {}).get("column", 0),
            "rule": o.get("cop_name", ""),
            "message": o.get("message", ""),
            "severity": o.get("severity", ""),
        }
        for f in data.get("files") or []
        for o in f.get("offenses") or []
    ]


class RubocopGate(ToolchainGate):
    """rubocop — the de-facto Ruby linter/formatter."""

    name = "rubocop"
    ecosystem = "ruby"
    langs = _LANGS
    markers = _MARKERS
    binary = "rubocop"

    async def check(self, ctx: GateContext, root: str) -> GateResult:
        rc, out, err = await run_tool(
            ["rubocop", "--format", "json", "--no-color", "--force-exclusion"], root
        )
        if (to := timeout_result(self.name, rc)) is not None:
            return to
        data = parsed(out)
        if data is None:
            # rubocop exits 2 and prints nothing parseable when its config is
            # broken or a required gem is absent — a tool failure, not offences.
            return unavailable(
                self.name,
                f"rubocop: did not run — {tail(merged(out, err), 2)}",
            )
        findings = _rubocop_findings(data)
        n = (data.get("summary") or {}).get("offense_count", len(findings))
        return counted(self.name, n, "rubocop", findings[:50], noun="offence(s)")

    async def fix(self, ctx: GateContext) -> tuple[bool, str]:
        """`rubocop --autocorrect` — the safe corrections only. Under `--fix`."""
        root = project_dir(ctx, self.markers)
        if root is None or tool_missing("rubocop"):
            return (False, "rubocop unavailable — nothing fixed")
        await run_tool(["rubocop", "--autocorrect", "--no-color"], root)
        return (False, "rubocop --autocorrect applied")


class BundlerAuditGate(ToolchainGate):
    """bundler-audit — known advisories against the resolved Gemfile.lock.

    `--no-update` on purpose: a gate does not reach the network on its own
    initiative, and the advisory database is the operator's to refresh.
    """

    name = "bundler_audit"
    ecosystem = "ruby"
    langs = _LANGS
    markers = ("Gemfile.lock",)
    binary = "bundle-audit"

    async def check(self, ctx: GateContext, root: str) -> GateResult:
        rc, out, err = await run_tool(["bundle-audit", "check", "--no-update"], root)
        if (to := timeout_result(self.name, rc)) is not None:
            return to
        combined = (out or "") + (err or "")
        advisories = [ln for ln in combined.splitlines() if ln.startswith("Name: ")]
        if rc == 0:
            return GateResult(
                self.name, GateOutcome.PASS, 1.0, "bundler-audit: no known advisories"
            )
        if not advisories:
            return unavailable(
                self.name, f"bundler-audit: did not run — {tail(combined, 2)}"
            )
        n = len(advisories)
        score = max(0.0, 1.0 - min(n, 10) / 10)
        return GateResult(
            self.name,
            GateOutcome.FAIL,
            score,
            f"bundler-audit: {n} vulnerable gem(s)",
            [{"message": ln} for ln in combined.splitlines() if ln.strip()][:50],
        )


class RubyTestGate(ToolchainGate):
    """The project's suite: rspec when there is a `spec/`, else `rake test`."""

    name = "ruby_test"
    ecosystem = "ruby"
    langs = _LANGS
    markers = _MARKERS

    async def check(self, ctx: GateContext, root: str) -> GateResult:
        if (Path(root) / "spec").is_dir():
            if tool_missing("rspec"):
                return self.missing("rspec")
            return await exit_code(
                self.name,
                ["rspec", "--no-color"],
                root,
                ok="rspec: passed",
                bad="rspec: failed",
                fail_re=r"^\s*\d+\)\s",
            )
        if not (Path(root) / "Rakefile").is_file():
            return GateResult(
                self.name, GateOutcome.PASS, 1.0, "ruby: no spec/ and no Rakefile"
            )
        if tool_missing("rake"):
            return self.missing("rake")
        return await exit_code(
            self.name,
            ["rake", "test"],
            root,
            ok="rake test: passed",
            bad="rake test: failed",
        )
