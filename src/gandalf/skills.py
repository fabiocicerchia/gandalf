"""Skill-driven gates: turn a `skills/<name>/SKILL.md` playbook into an
LLM-judged gandalf gate.

The four review skills embedded under the repo's top-level `skills/` directory
(pr-code-summarizer, quality-gate-review, ruthless-refactor, security-assessment)
are prose playbooks written for a human/agent reviewer. `judge()` feeds one of
them to the same headroom endpoint the compliance gate uses, asks for a strict
JSON verdict, and maps it onto a GateResult — so each skill becomes a gate with
no per-skill parsing logic.

Skills are read from gandalf's OWN source tree (next to this package), not from
the worktree under review: the playbook is part of the tool, the code being
judged is the input. This also means `--commit`/`--staged` runs against a
throwaway worktree still find the skills.

Like every LLM gate, it degrades to WARN (never crashes the run) when the
endpoint is unreachable, so static-only runs aren't blocked by a missing model.
"""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

from gandalf import llm
from gandalf.base import GateContext, GateOutcome, GateResult
from gandalf.plugins import unavailable

# skills/ lives at the repo root, above the src/gandalf/ package.
_SKILLS_DIR = Path(__file__).resolve().parent.parent.parent / "skills"

_DIFF_LIMIT = 12_000
_FINDINGS_CAP = 12
_FRONTMATTER = re.compile(r"^---\n.*?\n---\n", re.DOTALL)


# RAG bands for a skill score.
GREEN_SCORE = 0.8
AMBER_SCORE = 0.6


class SkillNotFoundError(Exception):
    """The named skill has no SKILL.md under skills/ — a packaging error, not a
    runtime condition, so it's raised rather than degraded to WARN."""


def load_skill(name: str) -> str:
    """Return a skill's SKILL.md body with its YAML frontmatter stripped."""
    path = _SKILLS_DIR / name / "SKILL.md"
    if not path.is_file():
        raise SkillNotFoundError(f"no skill playbook at {path}")
    return _FRONTMATTER.sub("", path.read_text(errors="replace")).strip()


def _loads(s: str) -> dict:
    """json.loads, but input nested too deep for the C decoder surfaces as an
    ordinary parse error instead of leaking RecursionError to callers that only
    guard against JSONDecodeError."""
    try:
        return json.loads(s)
    except RecursionError as exc:
        raise json.JSONDecodeError("input too deeply nested", s, 0) from exc


def _parse_json(text: str) -> dict:
    """Tolerant JSON extraction: strip markdown fences, else grab the first
    brace-delimited object. Raises json.JSONDecodeError on anything unparsable
    (including over-nested input). The compliance gate delegates here."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```", 2)[1]
        cleaned = cleaned.removeprefix("json")
    cleaned = cleaned.strip()
    try:
        return _loads(cleaned)
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\}", cleaned)
        if not m:
            raise
        return _loads(m.group(0))


_OUTCOMES = {
    "pass": GateOutcome.PASS,
    "warn": GateOutcome.WARN,
    "fail": GateOutcome.FAIL,
    # Verdict vocabularies some skills use in prose.
    "go": GateOutcome.PASS,
    "review": GateOutcome.WARN,
    "no-go": GateOutcome.FAIL,
    "no_go": GateOutcome.FAIL,
    "nogo": GateOutcome.FAIL,
}


def _coerce_outcome(raw: str, score: float) -> GateOutcome:
    """Map the model's outcome word to a GateOutcome, falling back to score
    banding (>=0.8 pass, >=0.6 warn, else fail) if it returned something odd."""
    hit = _OUTCOMES.get(str(raw).strip().lower())
    if hit is not None:
        return hit
    if score >= GREEN_SCORE:
        return GateOutcome.PASS
    if score >= AMBER_SCORE:
        return GateOutcome.WARN
    return GateOutcome.FAIL


_INSTRUCTION = """\
You are applying the reviewing skill above as an automated QUALITY GATE over the \
codebase/change described below. Follow the skill's method, then collapse your \
judgement into a single machine-readable verdict.

{task}

Respond with ONLY a JSON object, no prose and no markdown fences:
{{
  "outcome": "pass" | "warn" | "fail",
  "score": <integer 0-100, higher is better>,
  "summary": "<one professional sentence — the verdict and why>",
  "findings": [<up to {cap} short strings: the concrete blockers/risks/gaps, \
each citing a file, symbol, or section where possible>]
}}
"""


async def judge(
    ctx: GateContext,
    *,
    skill: str,
    gate_name: str,
    task: str,
) -> GateResult:
    """Run one skill as a gate: playbook + repo context + change → JSON verdict.

    `task` is the per-gate steer appended to the shared rubric (how this skill
    decides pass/warn/fail). All LLM/transport failures degrade to WARN."""
    playbook = load_skill(skill)
    meta = ctx.meta or {}
    diff = (meta.get("diff") or "").strip()
    label = meta.get("title") or Path(ctx.workdir).name or "working tree"

    prompt = (
        f"{playbook}\n\n---\n\n"
        + _INSTRUCTION.format(task=task, cap=_FINDINGS_CAP)
        + "\n"
        + llm._context(ctx.workdir, label, diff[:_DIFF_LIMIT])
    )

    try:
        # llm.chat is blocking urllib — keep it off the event loop.
        text = await asyncio.to_thread(llm.chat, [{"role": "user", "content": prompt}], temperature=0.0)
        data = _parse_json(text)
    except Exception as exc:
        return unavailable(
            gate_name,
            f"{gate_name}: skill judge unavailable ({str(exc)[:80]}) — skipped",
        )

    try:
        pct = max(0, min(100, round(float(data.get("score", 0)))))
    except (TypeError, ValueError):
        pct = 0
    score = pct / 100.0
    outcome = _coerce_outcome(data.get("outcome", ""), score)
    findings = [{"finding": str(f).strip()} for f in (data.get("findings") or []) if str(f).strip()][:_FINDINGS_CAP]
    summary = str(data.get("summary") or f"{pct}/100").strip()
    return GateResult(gate_name, outcome, score, summary, findings)
