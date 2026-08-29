"""Run an embedded project skill as a gandalf gate.

A *skill gate* hands a change to the LLM together with the verbatim text of a
project skill (``skills/<slug>/SKILL.md``) wrapped in a scoring contract, then
maps the model's score to a Red/Amber/Green outcome. The skill file is the
rubric and the single source of truth: edit the skill and every gate built on it
follows, exactly the way a human agent invoking ``/<skill>`` would. This is how
gandalf turns prose skills — grill-me, improve-codebase-architecture,
well-architected — into automated quality gates.

These gates are ADVISORY: they emit only PASS or WARN, never FAIL. LLM judgement
is subjective, so a skill gate surfaces friction (amber) without hard-blocking a
build — the deterministic tool gates (bandit, semgrep, kics, …) own the red
line. A WARN is also the honest degrade when the model is unreachable, the skill
file is missing, or there is nothing in scope to judge: never a false pass.
"""

from __future__ import annotations

import asyncio
from functools import cache
from pathlib import Path

from gandalf.base import GateContext, GateOutcome, GateResult
from gandalf.plugins import unavailable

# One tolerant JSON parser for every LLM-judge gate; it hardens json.loads so
# over-nested replies surface as JSONDecodeError instead of leaking RecursionError.
from gandalf.skills import _parse_json as parse_json

# skills/ sits at the repo root, above the src/gandalf/ package; resolve relative
# to this package so a gate reads the same file a human would `/`-invoke, wherever
# gandalf runs from (working tree, staged, or a throwaway --commit worktree).
SKILLS_DIR = Path(__file__).resolve().parent.parent.parent / "skills"

_DIFF_LIMIT = 20_000
_FILE_LIMIT = 8_000  # per changed file
_FILES_BUDGET = 24_000  # total across all changed-file contents
_SKILL_LIMIT = 16_000  # per skill, so a huge reference doc can't blow the prompt
_MAX_FINDINGS = 20


@cache
def load_skill(slug: str) -> str:
    """The verbatim ``SKILL.md`` for ``slug`` (bounded). Returns "" when the skill
    isn't embedded, so the gate degrades to WARN rather than scoring blind."""
    main = SKILLS_DIR / slug / "SKILL.md"
    if not main.is_file():
        return ""
    return main.read_text(errors="replace")[:_SKILL_LIMIT]


def _rubric(slugs: tuple[str, ...]) -> str:
    """Concatenate the named skills into one rubric block. The first slug is the
    gate's skill; the rest are its embedded dependencies (e.g. grill-me → grilling,
    improve-codebase-architecture → codebase-design)."""
    parts = []
    for slug in slugs:
        text = load_skill(slug)
        if text:
            parts.append(f"===== SKILL: {slug} =====\n{text}")
    return "\n\n".join(parts)


def _changed_file_contents(ctx: GateContext) -> str:
    """Full text of the changed files (bounded), so a gate can reason about the
    actual code and not just the diff hunks. Empty when nothing is scoped (the
    default working-tree run) — the gate then leans on the diff/request alone."""
    root = Path(ctx.workdir)
    out: list[str] = []
    budget = _FILES_BUDGET
    for rel in ctx.changed_files or []:
        p = root / rel
        if not p.is_file() or budget <= 0:
            continue
        try:
            body = p.read_text(errors="replace")
        except OSError:
            continue
        body = body[: min(_FILE_LIMIT, budget)]
        budget -= len(body)
        out.append(f"--- {rel} ---\n{body}")
    return "\n\n".join(out)


def _normalize_findings(raw) -> list[dict]:
    """Coerce the model's findings into dicts whose keys report.fmt_finding
    already understands (``file`` / ``finding`` / ``description``)."""
    findings: list[dict] = []
    for item in (raw or [])[:_MAX_FINDINGS]:
        if isinstance(item, str):
            findings.append({"finding": item.strip()})
            continue
        if not isinstance(item, dict):
            continue
        sev = str(item.get("severity") or item.get("risk") or "").strip().lower()
        findings.append(
            {
                "severity": sev,
                "finding": str(
                    item.get("title") or item.get("finding") or item.get("issue") or ""
                ).strip(),
                "description": str(
                    item.get("detail")
                    or item.get("description")
                    or item.get("recommendation")
                    or ""
                ).strip(),
                "file": str(
                    item.get("location") or item.get("file") or item.get("module") or ""
                ).strip(),
            }
        )
    return [f for f in findings if f.get("finding") or f.get("description")]


class SkillGate:
    """Base for LLM-backed skill gates. A subclass sets ``name``, ``category``,
    ``skills`` (the embedded slugs to load as the rubric), ``task`` (how to apply
    the skill as a non-interactive gate + the shape of the JSON to return), and
    ``pass_threshold`` (0..1). Optionally ``needs_request`` when the skill has
    nothing to judge without a --title/--body plan, and ``langs`` to scope it.

    Never emits FAIL: at/above threshold → PASS, otherwise → WARN.
    """

    name: str = ""  # set by each subclass
    blocking = False
    skills: tuple[str, ...] = ()
    task = ""
    pass_threshold = 0.75
    needs_request = False
    unit = "issue"  # what a finding is called in the summary line

    async def run(self, ctx: GateContext) -> GateResult:
        from gandalf import llm

        rubric = _rubric(self.skills)
        if not rubric:
            return unavailable(
                self.name,
                f"{self.name}: skill not embedded ({', '.join(self.skills)}) — skipped",
            )

        meta = ctx.meta or {}
        title = (meta.get("title") or "").strip()
        body = (meta.get("body") or "").strip()
        diff = (meta.get("diff") or "").strip()
        files = _changed_file_contents(ctx)

        if self.needs_request and not (title or body):
            return unavailable(
                self.name,
                f"{self.name}: no plan to judge — pass --title/--body describing the intent",
            )
        if not (diff or files or title or body):
            return unavailable(
                self.name, f"{self.name}: nothing in scope to judge — skipped"
            )

        prompt = self._prompt(rubric, title, body, diff, files, ctx)
        try:
            text = await asyncio.to_thread(
                llm.chat, [{"role": "user", "content": prompt}], temperature=0.0
            )
            data = parse_json(text)
        except Exception as exc:  # noqa: BLE001 — never crash or false-pass the run
            return unavailable(
                self.name, f"{self.name}: judge unavailable ({str(exc)[:70]}) — skipped"
            )

        try:
            pct = max(0, min(100, round(float(data.get("score", 0)))))
        except (TypeError, ValueError):
            pct = 0
        score = pct / 100.0
        findings = _normalize_findings(data.get("findings"))
        judge_summary = str(data.get("summary") or "").strip()

        outcome = GateOutcome.PASS if score >= self.pass_threshold else GateOutcome.WARN
        n = len(findings)
        summary = f"{pct}/100" + (
            f" · {n} {self.unit}{'s' if n != 1 else ''}" if n else " · clean"
        )
        if judge_summary:
            findings = [*findings, {"judge_summary": judge_summary}]
        return GateResult(self.name, outcome, score, summary, findings)

    def _prompt(
        self,
        rubric: str,
        title: str,
        body: str,
        diff: str,
        files: str,
        ctx: GateContext,
    ) -> str:
        diff_trunc = diff[:_DIFF_LIMIT] + (
            "\n…[diff truncated]" if len(diff) > _DIFF_LIMIT else ""
        )
        langs = ", ".join((ctx.meta or {}).get("languages") or []) or "unknown"
        request = (
            f"Title: {title}\n\n{body}".strip()
            if (title or body)
            else "(no explicit request supplied — infer intent from the change)"
        )
        return (
            f"{rubric}\n\n"
            "===== YOU ARE RUNNING THE SKILL(S) ABOVE AS AN AUTOMATED QUALITY GATE =====\n"
            "You are executing inside a CI pipeline, not an interactive session. You "
            "CANNOT ask the user questions, open a browser, write files, or run tools. "
            "Apply the judgement and vocabulary of the skill(s) above to the change "
            "below and return a single JSON verdict.\n\n"
            f"{self.task}\n\n"
            f"## Scope\nLanguages in scope: {langs}\n\n"
            f"## Request / intent\n{request}\n\n"
            f"## Diff\n{diff_trunc or '(no diff in scope)'}\n\n"
            f"## Changed file contents\n{files or '(none in scope)'}\n\n"
            "Respond with ONLY a JSON object — no prose, no markdown fences:\n"
            "{\n"
            '  "score": <integer 0-100>,\n'
            '  "summary": "<one professional sentence>",\n'
            '  "findings": [\n'
            '    {"severity": "high|medium|low", "title": "<short>", '
            '"detail": "<specific, actionable>", "location": "<file:line or module>"}\n'
            "  ]\n"
            "}\n"
            "Return an empty findings list only when the change genuinely clears the "
            "skill's bar. Be specific: cite the file, module, or line — never vague advice."
        )
