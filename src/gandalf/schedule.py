"""Gate run order: the expensive ones first.

Gates run concurrently but bounded — `--concurrency` caps how many are in
flight, because ~35 gates each spawning a `docker run` will swamp a laptop. Once
there is a queue, the order gates are submitted in decides when the run ends: a
five-minute trivy that starts last adds five minutes to a scan that had
otherwise finished. Discovery order is alphabetical by module filename, which is
no order at all — it puts `bandit` first and `trivy` near the back.

Longest-processing-time-first is the standard answer to that, and it is cheap:
start the heavy gates immediately and let the quick ones fill in behind them.
The estimate is, in order of preference:

1. what the gate actually cost last time, recorded in the result cache
   (`--cache`) — the only number that knows this repository;
2. a `cost` class attribute the gate declares for itself — the same
   plugin-friendly escape hatch `category` and `cache_ttl` already give;
3. the rough prior below, which only has to get the *tiers* right.

The prior is deliberately coarse and deliberately short. It is a tie-breaker for
the first run on a machine with no history, not a performance model — a wrong
guess costs some scheduling slack, never a wrong answer.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

    from .base import Gate

from . import debug

# A gate nobody has timed and nobody has labelled: assume it is a linter.
DEFAULT_COST = 10.0

# gate name → rough seconds, for gates whose tier is knowable in advance.
# Only the outliers are listed; everything unlisted gets DEFAULT_COST, which is
# where most linters genuinely land.
_PRIOR = {
    # Minutes: a whole CI run, a fuzzer, a live target, a database build.
    "codeql": 600.0,
    "ci_act": 300.0,
    "atheris": 300.0,
    "nikto": 240.0,
    "sqlmap": 240.0,
    "dalfox": 180.0,
    # A container image doing a full-tree scan.
    "kics": 180.0,
    "semgrep": 150.0,
    "trivy": 120.0,
    "checkov": 90.0,
    "scorecard": 90.0,
    # Compiling, or running someone's whole test suite.
    "java_build": 180.0,
    "java_test": 180.0,
    "cargo_build": 180.0,
    "cargo_test": 180.0,
    "cpp_build": 120.0,
    "cpp_test": 120.0,
    "dotnet_build": 120.0,
    "dotnet_test": 120.0,
    "build": 90.0,
    "tests": 90.0,
    "go_build": 90.0,
    "go_test": 90.0,
    "node_test": 90.0,
    "php_test": 90.0,
    "ruby_test": 90.0,
    "clippy": 120.0,
    "golangci_lint": 90.0,
    "tsc": 60.0,
    "checkstyle": 60.0,
    # Resolving a dependency tree, then asking an advisory database about it.
    "govulncheck": 60.0,
    "osv_scanner": 60.0,
    "dotnet_audit": 60.0,
    "licenses": 45.0,
    "osv": 45.0,
    "mypy": 45.0,
    "eslint": 45.0,
    # One LLM round trip each. Skipped outright under --no-llm.
    "grill_me": 60.0,
    "codebase_architecture": 60.0,
    "well_architected": 60.0,
    "security_assessment": 60.0,
    "ruthless_refactor": 60.0,
    "quality_gate_review": 60.0,
    "pr_code_summary": 60.0,
    "compliance": 60.0,
    # Fast enough that they are what you want filling the gaps.
    "ruff": 3.0,
    "format": 3.0,
    "hadolint": 3.0,
    "yamllint": 4.0,
    "actionlint": 4.0,
    "shellcheck": 5.0,
    "php_syntax": 5.0,
    "ruby_syntax": 5.0,
    "squawk": 5.0,
}


def cost(gate: Gate, recorded: dict[str, float] | None = None) -> float:
    """Seconds this gate is expected to take: measured, declared, or assumed.

    A measurement always wins — it is the only estimate that has seen this
    repository, this machine and this toolchain.
    """
    name = getattr(gate, "name", "")
    measured = (recorded or {}).get(name)
    if measured is not None:
        return float(measured)
    declared = getattr(gate, "cost", None)
    if declared is not None:
        try:
            return float(declared)
        except (TypeError, ValueError):
            pass  # A gate with a nonsense `cost` is scheduled, not rejected.
    return _PRIOR.get(name, DEFAULT_COST)


def order(gates: Sequence[Gate], recorded: dict[str, float] | None = None) -> list[Gate]:
    """`gates`, most expensive first. Ties break by name, so a run's order is
    reproducible and a diff of two `--debug` logs is readable."""
    ranked = sorted(gates, key=lambda g: (-cost(g, recorded), getattr(g, "name", "")))
    if ranked and debug.enabled():
        head = ", ".join(f"{g.name} ~{cost(g, recorded):.0f}s" for g in ranked[:5])
        source = "measured + priors" if recorded else "priors only (no cache history)"
        debug.log(f"gate order ({source}), heaviest first: {head}")
    return ranked
