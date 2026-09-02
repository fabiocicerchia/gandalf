"""The scorecard as a terminal draws it: ANSI colours, grouped gate rows,
the score breakdown, and the first-run setup banner."""

from __future__ import annotations

from . import plugins
from .base import GateOutcome, GateResult
from .plugins import did_not_run
from .report import (
    GROUP_ORDER,
    RAG,
    SKIP_EMOJI,
    Verdict,
    category_of,
    format_delta,
    group_outcome_and_pct,
)

_RESET = "\033[0m"
_BOLD = "\033[1m"
_DIM = "\033[2m"
_CYAN = "\033[36m"
# outcome → ANSI "banner" (bg + fg), mirroring the webpage's coloured blocks.
_BANNER = {
    GateOutcome.PASS: "\033[1;30;42m",
    GateOutcome.WARN: "\033[1;30;43m",
    GateOutcome.FAIL: "\033[1;97;41m",
}


def render_terminal(
    label: str,
    results: list[GateResult],
    verdict: Verdict,
    advice: dict,
    meta: dict | None = None,
) -> str:
    """Render the scorecard for a terminal.

    The primary surface: the answer has to be readable in the pane it is run
    in, before anyone opens the HTML report or the JSON.
    """
    meta = meta or {}
    lines = [f"\n{_BOLD}🧙  GANDALF{_RESET} {_DIM}— {label}{_RESET}"]
    c = meta.get("commit") or {}
    if c.get("short"):
        lines.append(f"{_DIM}commit {c['short']} — {c.get('subject', '')}{_RESET}")
    if meta.get("generated_at"):
        lines.append(f"{_DIM}generated {meta['generated_at']}{_RESET}")
    if results and all(did_not_run(r) for r in results):
        # A score computed from gates that all declined to run is not a score.
        # Saying "AMBER · 0/100" here reads as "your code scored zero".
        lines.append(
            f"\n{_BANNER[GateOutcome.WARN]}  NOT RUN · no gate produced "
            f"a result  {_RESET}"
        )
    else:
        word = RAG[verdict.outcome][3]
        lines.append(
            f"\n{_BANNER[verdict.outcome]}  {word} · {verdict.score}/100"
            f"{format_delta(meta.get('score_delta'))}  {_RESET}"
        )

    # Gates grouped by category, each header coloured by its aggregate RAG + score.
    width = max((len(r.name) for r in results), default=4)
    for group in GROUP_ORDER:
        members = sorted(
            (r for r in results if category_of(r) == group), key=lambda r: r.name
        )
        if not members:
            continue
        gc, pct = group_outcome_and_pct(members)
        gcol = RAG[gc][1]
        shown = "not run" if pct is None else f"{pct}%"
        lines.append(f"\n{_BOLD}{gcol}{group}{_RESET} {_DIM}· {shown}{_RESET}")
        for r in members:
            emoji, color, _, _w = RAG[r.outcome]
            if did_not_run(r):
                # Deliberately not a traffic light: this gate reported nothing
                # about the code, and an amber dot claims it did.
                emoji, color = SKIP_EMOJI, _DIM
            block = (
                f" {_DIM}[blocking]{_RESET}" if getattr(r, "_blocking", False) else ""
            )
            lines.append(
                f"  {emoji} {color}{r.name.ljust(width)}{_RESET}  {r.summary}{block}"
            )
    if n_skipped := sum(1 for r in results if did_not_run(r)):
        lines.append(
            f"\n{_DIM}{n_skipped} of {len(results)} gate(s) could not run "
            f"— not counted in the score{_RESET}"
        )
    outcome_of = {r.name: r.outcome for r in results}
    sev_order = {GateOutcome.FAIL: 0, GateOutcome.WARN: 1, GateOutcome.PASS: 2}
    for header in ("summary", "changeset", "remediation", "improvement"):
        if header == "remediation":
            body = _remediation_text(advice, outcome_of, sev_order)
        else:
            body = (advice.get(header) or "").strip()
        if body:
            lines.append(f"\n{header.upper()}")
            lines.append(body)
    return "\n".join(lines)


def _score_table(counted: list[GateResult], verdict: Verdict) -> list[str]:
    """The per-gate addends of the composite, and the mean they add up to."""
    width = max(len(r.name) for r in counted)
    lines = [f"  {_DIM}{'gate'.ljust(width)}   score   contributes{_RESET}"]
    for r in sorted(counted, key=lambda r: (r.score, r.name)):
        note = ""
        raw = getattr(r, "_raw_score", None)
        if raw is not None and round(raw, 3) != round(r.score, 3):
            note = f"  {_DIM}(gate scored {raw:.2f}, severity-weighted){_RESET}"
        emoji = RAG[r.outcome][0]
        lines.append(
            f"  {r.name.ljust(width)}  {r.score:5.2f}   "
            f"{r.score / len(counted) * 100:9.1f}  {emoji}{note}"
        )
    lines.append(
        f"  {_DIM}{'─' * (width + 24)}{_RESET}\n"
        f"  {len(counted)} gate(s) counted · mean "
        f"{sum(r.score for r in counted) / len(counted):.3f} → {verdict.score}/100"
    )
    return lines


def explain_score(results: list[GateResult], verdict: Verdict) -> str:
    """Show how the composite was arrived at: every gate that counted, its score,
    and what it contributed.

    The composite is an unweighted mean, which is simple enough that nobody
    documents it and therefore nobody can reproduce it — "why is this 81 and not
    74?" has no answer short of reading report.py. Printing the addends answers it,
    and makes the two things that silently move the number visible: gates left out
    because they could not run, and scores replaced by severity weighting.
    """
    counted = [r for r in results if not did_not_run(r)]
    skipped = [r for r in results if did_not_run(r)]
    lines = [f"\n{_BOLD}SCORE{_RESET}  {verdict.score}/100"]
    if not counted:
        lines.append(
            f"  {_DIM}no gate produced a result — there is nothing to average{_RESET}"
        )
        return "\n".join(lines)
    lines += _score_table(counted, verdict)
    if skipped:
        names = ", ".join(sorted(r.name for r in skipped))
        lines.append(
            f"  {_DIM}{len(skipped)} not counted (could not run): {names}{_RESET}"
        )
    return "\n".join(lines)


def setup_banner(results: list[GateResult], image_built: bool, has_docker: bool) -> str:
    """A setup banner for a host where most gates found no tool to run, else "".

    The first-run problem this solves: gandalf resolves ~60 third-party scanners,
    and on a machine with none of them every gate degrades. The scorecard that
    comes out is technically accurate and completely unhelpful — page after page
    of amber about tools, not a word about the code — and it reads as "this is
    broken" rather than "this needs one setup step". So when almost nothing could
    run, say that plainly and say what to do about it.

    Deliberately printed after the scorecard: in a terminal the footer is what is
    still on screen when the run ends.
    """
    total = len(results)
    n = sum(1 for r in results if did_not_run(r))
    # Two thirds is the point where the scorecard is mostly about tooling rather
    # than about the repo. Below it the run still said something useful.
    if not total or n * 3 < total * 2:
        return ""
    nothing_ran = n == total
    head = (
        "No scanners available — gandalf checked nothing."
        if nothing_ran
        else f"Most scanners are unavailable — {n} of {total} gates could not run."
    )
    if image_built:
        # The image exists, so what is missing is host-only tooling: language
        # toolchains and project-local tools the image deliberately does not carry.
        fix = [
            f"The {plugins.TOOLS_IMAGE} image is built, so these are the host-only",
            "tools — language toolchains (go, npx/npm, cargo, mvn) and project",
            "environments. Install the ones for the languages you care about.",
        ]
    elif has_docker:
        fix = [
            "Build the scanner image once — no host installs:",
            "    make tools",
            "...or install individual scanners on PATH. Both work, mixed freely.",
        ]
    else:
        fix = [
            "Install the scanners on PATH, or install Docker and run:",
            "    make tools",
            "(the image is only ever checked for, never pulled)",
        ]
    body = [head, ""] + fix
    if nothing_ran:
        body += ["", "Nothing was verified, so the score is not a quality signal."]
    rule = "─" * 66
    lines = [f"\n{_BOLD}{_CYAN}{rule}{_RESET}"]
    lines += [f"{_CYAN}│{_RESET} {line}" for line in body]
    lines.append(f"{_BOLD}{_CYAN}{rule}{_RESET}")
    return "\n".join(lines)


def _remediation_text(advice: dict, outcome_of: dict, sev_order: dict) -> str:
    """Plain-text remediation: gate blocks as 'name (RAG):', failures first. Falls
    back to the raw markdown when the model gave no per-gate structure."""
    groups = advice.get("remediation_groups") or []
    if not groups:
        return (advice.get("remediation") or "").strip()
    ordered = sorted(groups, key=lambda g: sev_order.get(outcome_of.get(g[0]), 3))
    blocks = []
    if pre := (advice.get("remediation_pre") or "").strip():
        blocks.append(pre)
    for name, body in ordered:
        outcome = outcome_of.get(name)
        word = RAG[outcome][3] if outcome else "WARN"
        blocks.append(f"{name} ({word}):\n{body}")
    return "\n\n".join(blocks)
