"""Render gate results as JUnit XML — the format most CI systems (Jenkins,
GitLab, ...) render as a test-style report, as an alternative to SARIF.
Stdlib only.

Each gate becomes one <testcase>. FAIL becomes a <failure> (what fails the
build under gandalf's default policy); WARN stays a passing testcase with a
<system-out> note, since WARN doesn't fail the run unless --fail-on warn is
set.
"""

from __future__ import annotations

from xml.sax.saxutils import escape, quoteattr

from .base import GateOutcome, GateResult
from .report import fmt_finding


def to_junit(results: list[GateResult], meta: dict | None = None) -> str:
    meta = meta or {}
    failures = sum(1 for r in results if r.outcome == GateOutcome.FAIL)
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<testsuite name="gandalf" tests="{len(results)}" failures="{failures}" '
        f'errors="0" skipped="0">',
    ]
    for r in results:
        duration = getattr(r, "_duration", None)
        time_attr = (
            f' time="{duration:.3f}"' if isinstance(duration, (int, float)) else ""
        )
        lines.append(
            f"  <testcase classname=\"gandalf\" name={quoteattr(r.name)}{time_attr}>"
        )
        body_lines = [r.summary] if r.summary else []
        body_lines += [fmt_finding(f) for f in r.findings]
        body = escape("\n".join(body_lines))
        if r.outcome == GateOutcome.FAIL:
            lines.append(f"    <failure message={quoteattr(r.summary or r.name)}>{body}</failure>")
        elif r.outcome == GateOutcome.WARN and body:
            lines.append(f"    <system-out>{body}</system-out>")
        lines.append("  </testcase>")
    lines.append("</testsuite>")
    return "\n".join(lines)
