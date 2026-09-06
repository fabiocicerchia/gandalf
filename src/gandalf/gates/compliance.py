"""Compliance gate: an LLM judge scoring how fully the change satisfies the
request. Ported from ai-harness; the ai-harness router is swapped for gandalf.llm.

Needs a request to judge against — pass --title / --body (or set ctx.meta). With
no request/diff it degrades to WARN. Passes at >= 85% compliance.
"""

from __future__ import annotations

import asyncio

from gandalf.base import GateContext, GateOutcome, GateResult
from gandalf.plugins import unavailable
from gandalf.skills import _parse_json as _parse_judge

COMPLIANCE_THRESHOLD = 0.85
_DIFF_LIMIT = 24_000
_BODY_LIMIT = 6_000

_PROMPT = """\
You are a senior staff engineer reviewing whether a proposed change delivers what was asked.
Judge adherence to the PROVIDED REQUIREMENTS.

### REQUIREMENTS ###
Title: {title}

{body}

### PROPOSED CHANGE (unified diff) ###
{diff}

### INSTRUCTIONS ###
1. Compare the diff against each requirement/acceptance criterion above.
2. Be objective: a partial implementation that lacks core functionality should be scored low.
3. Be fair: if a requirement is fully met, mark it as met.

Respond with ONLY a JSON object, no prose, no markdown fences:
{{
  "compliance": <integer 0-100 — how fully the diff satisfies the requirements>,
  "missing": [<short string per requirement/criterion not fully met or missing>],
  "summary": "<one clear, professional sentence summarizing the gap>"
}}
"""


def _prompt(ctx: GateContext) -> str | None:
    """The judge prompt for this change, or None when there is nothing to judge."""
    meta = ctx.meta or {}
    title = (meta.get("title") or "").strip()
    body = (meta.get("body") or "").strip()
    diff = (meta.get("diff") or "").strip()
    if not diff or not (title or body):
        return None
    diff_trunc = diff[:_DIFF_LIMIT] + ("\n…[diff truncated]" if len(diff) > _DIFF_LIMIT else "")
    body_trunc = body[:_BODY_LIMIT] + ("\n…[truncated]" if len(body) > _BODY_LIMIT else "")
    return _PROMPT.format(title=title, body=body_trunc, diff=diff_trunc)


def _verdict(gate: str, data: dict) -> GateResult:
    """The judge's JSON as a gate result. A score that will not parse is 0 —
    never a pass."""
    try:
        pct = max(0, min(100, round(float(data.get("compliance", 0)))))
    except (TypeError, ValueError):
        pct = 0
    score = pct / 100.0
    missing = [str(m).strip() for m in (data.get("missing") or []) if str(m).strip()]
    outcome = GateOutcome.PASS if score >= COMPLIANCE_THRESHOLD else GateOutcome.FAIL
    summary = f"{pct}% compliant" + (f" · {len(missing)} unmet point(s)" if missing else "")
    findings = [{"missing": m} for m in missing]
    if data.get("summary"):
        findings.append({"judge_summary": str(data["summary"])})
    return GateResult(gate, outcome, score, summary, findings)


class ComplianceGate:
    name = "compliance"
    blocking = False

    async def run(self, ctx: GateContext) -> GateResult:
        from gandalf import llm  # noqa: PLC0415 — local import: importing at module scope closes a cycle

        prompt = _prompt(ctx)
        if prompt is None:
            return unavailable(self.name, "compliance: no request/diff to judge (pass --title/--body)")
        try:
            # llm.chat is blocking (urllib) — run it off the event loop.
            text = await asyncio.to_thread(llm.chat, [{"role": "user", "content": prompt}], temperature=0.0)
            data = _parse_judge(text)
        except Exception as exc:
            return GateResult(
                self.name,
                GateOutcome.FAIL,
                0.0,
                f"compliance: judge unavailable ({str(exc)[:80]})",
            )
        return _verdict(self.name, data)
