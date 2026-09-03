"""The RAG vocabulary and the scoring: category, verdict, policy.

Rendering lives next door — `render_text` for the terminal, `render_html`
for the self-contained report — so a change to how a scorecard looks never
touches how it is computed.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from . import findings
from .base import GateOutcome, GateResult
from .plugins import did_not_run


def fmt_finding(f) -> str:
    """One-line, human-readable rendering of a heterogeneous gate finding."""
    if not isinstance(f, dict):
        return str(f)[:500]
    loc = findings.path(f)
    line = findings.line(f)
    msg = findings.message(f)
    head = f"{loc}:{line}" if (loc and line) else str(loc)
    text = f"{head} — {msg}" if (head and msg) else (str(msg) or head)
    return (text or json.dumps(f, default=str))[:600]


# Gate → category, so the scorecard groups by concern rather than by language.
# A gate may override by setting a `category` class attribute (plugin-friendly).
_CATEGORY = {
    # Security — SAST, secrets, DAST, fuzz
    "semgrep": "Security",
    "bandit": "Security",
    "gitleaks": "Security",
    "atheris": "Security",
    "nikto": "Security",
    "sqlmap": "Security",
    "dalfox": "Security",
    # Dependencies — known-vuln scanning of deps / lockfiles
    "osv": "Dependencies",
    "osv_scanner": "Dependencies",
    "govulncheck": "Dependencies",
    "trivy": "Dependencies",
    "bundler_audit": "Dependencies",
    "composer_audit": "Dependencies",
    "dotnet_audit": "Dependencies",
    # Licensing — dependency license obligations
    "licenses": "Licensing",
    # Infrastructure — IaC, containers, CI config
    "checkov": "Infrastructure",
    "kics": "Infrastructure",
    "hadolint": "Infrastructure",
    "actionlint": "Infrastructure",
    # Database — SQL lint + migration safety
    "sqlfluff": "Database",
    "squawk": "Database",
    # Code quality — lint, format, types, dead code, style
    "ruff": "Code quality",
    "format": "Code quality",
    "mypy": "Code quality",
    "vulture": "Code quality",
    "golangci_lint": "Code quality",
    "eslint": "Code quality",
    "tsc": "Code quality",
    "shellcheck": "Code quality",
    "yamllint": "Code quality",
    "checkstyle": "Code quality",
    "ktlint": "Code quality",
    "rubocop": "Code quality",
    "phpcs": "Code quality",
    "cppcheck": "Code quality",
    "dotnet_format": "Code quality",
    # Complexity — maintainability / cyclomatic complexity
    "lizard": "Complexity",
    # Documentation — docstrings, markdown, spelling
    "interrogate": "Documentation",
    "mdl": "Documentation",
    "codespell": "Documentation",
    # Build & tests — compile, test suites, CI runner
    "build": "Build & tests",
    "go_build": "Build & tests",
    "tests": "Build & tests",
    "go_test": "Build & tests",
    "node_test": "Build & tests",
    "ci_act": "Build & tests",
    "java_build": "Build & tests",
    "java_test": "Build & tests",
    "ruby_syntax": "Build & tests",
    "ruby_test": "Build & tests",
    "php_syntax": "Build & tests",
    "php_test": "Build & tests",
    "cpp_build": "Build & tests",
    "cpp_test": "Build & tests",
    "dotnet_build": "Build & tests",
    "dotnet_test": "Build & tests",
    # Best-practices / compliance
    "compliance": "Best practices",
    # Skill-backed advisory gates (LLM judges built from embedded skills/)
    "grill_me": "Design readiness",
    "codebase_architecture": "Architecture",
    "well_architected": "Well-Architected",
}
GROUP_ORDER = (
    "Security",
    "Dependencies",
    "Licensing",
    "Infrastructure",
    "Database",
    "Code quality",
    "Complexity",
    "Documentation",
    "Build & tests",
    "Best practices",
    "Architecture",
    "Design readiness",
    "Well-Architected",
    "Other",
)


def category_of(r: GateResult) -> str:
    """The concern a gate reports on — the report's grouping, and part of the
    JSON payload so downstream consumers (editors, dashboards) group the same
    way without re-deriving the table."""
    return getattr(r, "_category", "") or _CATEGORY.get(r.name, "Other")


# outcome → (emoji, ansi, hex, label)
RAG = {
    GateOutcome.PASS: ("🟢", "\033[32m", "#22c55e", "GREEN"),
    GateOutcome.WARN: ("🟡", "\033[33m", "#eab308", "AMBER"),
    GateOutcome.FAIL: ("🔴", "\033[31m", "#ef4444", "RED"),
}
# A gate that could not run gets its own glyph — it is not a traffic light.
SKIP_EMOJI = "⚪"


@dataclass
class Verdict:
    """The run's single answer: one traffic light and one number out of 100."""

    outcome: GateOutcome  # overall RAG
    score: int  # 0..100 composite


@dataclass
class Policy:
    """How the RAG verdict maps to pass/fail (exit code). Defaults reproduce the
    original behaviour: only a red verdict fails the run."""

    fail_on: GateOutcome = GateOutcome.FAIL  # WARN → warnings fail the run too
    min_score: int = 0  # composite score below this fails the run

    @classmethod
    def from_config(
        cls,
        section: dict,
        cli_fail_on: str | None = None,
        cli_min_score: int | None = None,
    ) -> Policy:
        raw = (cli_fail_on or section.get("fail_on") or "fail").lower()
        fail_on = GateOutcome.WARN if raw == "warn" else GateOutcome.FAIL
        score = (
            cli_min_score if cli_min_score is not None else section.get("min_score", 0)
        )
        try:
            score = max(0, min(100, int(score)))
        except (TypeError, ValueError):
            score = 0
        return cls(fail_on, score)


def decide(verdict: Verdict, policy: Policy) -> tuple[bool, str]:
    """Apply the policy to a verdict → (passed, reason). `passed` drives the exit
    code; the displayed RAG is left untouched."""
    if verdict.outcome == GateOutcome.FAIL:
        return False, "a gate failed"
    if policy.fail_on == GateOutcome.WARN and verdict.outcome == GateOutcome.WARN:
        return False, "a gate warned (fail-on=warn)"
    if verdict.score < policy.min_score:
        return False, f"score {verdict.score} below min-score {policy.min_score}"
    return True, "policy satisfied"


def format_delta(delta: int | None) -> str:
    """' (+5 vs prev)' / ' (-3 vs prev)' / '' when there's no prior commit score."""
    if delta is None:
        return ""
    sign = "+" if delta >= 0 else ""
    return f" ({sign}{delta} vs prev)"


def aggregate(results: list[GateResult]) -> Verdict:
    """Red if any FAIL (blocking or not); amber if any WARN; green if all pass.
    Composite score = mean of gate sub-scores ×100.

    Gates that could not run are left out of both. A missing scanner is not a
    quality signal, and counting one as amber-at-0.8 is wrong in both directions:
    it drags a clean repo down and props a bad one up, and on a host with nothing
    installed it produces a scorecard that says nothing about the code. They are
    counted and shown separately instead — see `render_terminal`."""
    if not results:
        return Verdict(GateOutcome.WARN, 0)
    ran = [r for r in results if not did_not_run(r)]
    if not ran:
        # Every gate was unavailable: there is no score to report, and claiming
        # one would be inventing it. The CLI prints a setup banner for this case.
        return Verdict(GateOutcome.WARN, 0)
    if any(r.outcome == GateOutcome.FAIL for r in ran):
        overall = GateOutcome.FAIL
    elif any(r.outcome == GateOutcome.WARN for r in ran):
        overall = GateOutcome.WARN
    else:
        overall = GateOutcome.PASS
    score = round(sum(r.score for r in ran) / len(ran) * 100)
    return Verdict(overall, score)


def group_outcome_and_pct(members: list[GateResult]) -> tuple[GateOutcome, int | None]:
    """Worst outcome and mean score% across a category's gate results, counting
    only the gates that ran. `None` percent means none of them did — rendered as
    "not run" rather than as a 0% the category did not earn."""
    ran = [r for r in members if not did_not_run(r)]
    if not ran:
        return GateOutcome.WARN, None
    if any(r.outcome == GateOutcome.FAIL for r in ran):
        outcome = GateOutcome.FAIL
    elif any(r.outcome == GateOutcome.WARN for r in ran):
        outcome = GateOutcome.WARN
    else:
        outcome = GateOutcome.PASS
    pct = round(sum(r.score for r in ran) / len(ran) * 100)
    return outcome, pct
