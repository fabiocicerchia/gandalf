"""The scorecard as one self-contained HTML file: the stylesheet, the script,
and the markdown-to-HTML the LLM sections are rendered through."""

from __future__ import annotations

import html
import re
from collections import defaultdict

from .base import GateOutcome, GateResult
from .html_assets import CSS, JS
from .plugins import did_not_run
from .report import (
    GROUP_ORDER,
    RAG,
    SKIP_EMOJI,
    Verdict,
    category_of,
    fmt_finding,
    format_delta,
    group_outcome_and_pct,
)

# Shown in place of an empty LLM section so it reads as "skipped", not "missing".
_EMPTY_NOTE = (
    '<p class="empty-note">Not generated for this run '
    "(LLM was skipped or unavailable).</p>"
)
# The model's "everything passes" reply — matched loosely (markdown/punctuation
# tolerated) so the remediation section is omitted rather than showing a placeholder.
_NO_REMEDIATION = re.compile(r"^\W*no remediation needed\W*$", re.IGNORECASE)


def _md_inline(s: str) -> str:
    """Inline markdown → HTML: code, links, bold, italic. Escaped first, so a
    finding that contains `<script>` stays text."""
    s = html.escape(s)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r'<a href="\2">\1</a>', s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"(?<!\w)\*([^*]+)\*(?!\w)", r"<em>\1</em>", s)
    s = re.sub(r"(?<!\w)_([^_]+)_(?!\w)", r"<em>\1</em>", s)
    return s


class _MdBlocks:
    """The block-level state `_md_to_html` carries between lines: the rendered
    output so far, the paragraph being collected, and the open list."""

    def __init__(self) -> None:
        self.out: list[str] = []
        self.para: list[str] = []
        self.items: list[str] = []
        self.otype = ""

    def flush_para(self) -> None:
        if self.para:
            self.out.append("<p>" + _md_inline(" ".join(self.para)) + "</p>")
            self.para.clear()

    def flush_list(self) -> None:
        if self.items:
            self.out.append(
                f"<{self.otype}>"
                + "".join(f"<li>{_md_inline(i)}</li>" for i in self.items)
                + f"</{self.otype}>"
            )
            self.items.clear()
            self.otype = ""

    def open_list(self, kind: str, item: str) -> None:
        if self.otype and self.otype != kind:
            self.flush_list()
        self.otype = kind
        self.items.append(item)


def _md_to_html(text: str) -> str:
    """Tiny, dependency-free markdown → HTML for the LLM summary: headings, bold,
    italic, inline code, links, and un/ordered lists. Everything is HTML-escaped
    before our own tags go in."""
    b = _MdBlocks()
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line.strip():
            b.flush_para()
            b.flush_list()
            continue
        h = re.match(r"(#{1,6})\s+(.*)", line)
        ul = re.match(r"\s*[-*+]\s+(.*)", line)
        ol = re.match(r"\s*\d+\.\s+(.*)", line)
        if h:
            b.flush_para()
            b.flush_list()
            lvl = min(len(h.group(1)), 6)
            b.out.append(f"<h{lvl}>{_md_inline(h.group(2))}</h{lvl}>")
        elif ul:
            b.flush_para()
            b.open_list("ul", ul.group(1))
        elif ol:
            b.flush_para()
            b.open_list("ol", ol.group(1))
        else:
            b.flush_list()
            b.para.append(line.strip())
    b.flush_para()
    b.flush_list()
    return "\n".join(b.out) or "<p>(no summary)</p>"


def _diff_html(diff: str, limit: int = 20000) -> str:
    """Collapsible, lightly-colored unified diff for the changeset section."""
    if not diff.strip():
        return ""
    text = diff[:limit]
    lines = []
    for raw in text.splitlines():
        esc = html.escape(raw)
        if raw.startswith("+") and not raw.startswith("+++"):
            lines.append(f'<span class="diff-add">{esc}</span>')
        elif raw.startswith("-") and not raw.startswith("---"):
            lines.append(f'<span class="diff-del">{esc}</span>')
        elif raw.startswith("@@"):
            lines.append(f'<span class="diff-hunk">{esc}</span>')
        else:
            lines.append(esc)
    body = "\n".join(lines)
    if len(diff) > limit:
        body += "\n… (truncated)"
    n = len(diff.splitlines())
    return (
        f'<details class="diff-view"><summary>View raw diff ({n} line{"s" if n != 1 else ""})'
        f'</summary><pre class="diff-pre">{body}</pre></details>'
    )


_HTML_SEV = {GateOutcome.PASS: 0, GateOutcome.WARN: 1, GateOutcome.FAIL: 2}


def _gate_row(r: GateResult) -> str:
    """One `<tr>` of the gate table, carrying the data- attributes the page's
    sort and filter controls read."""
    emoji, _, _, word = RAG[r.outcome]
    cls = r.outcome.name.lower()
    if did_not_run(r):
        emoji, word = SKIP_EMOJI, "NOT RUN"
    detail = html.escape(r.summary)
    if r.findings:
        items = "".join(f"<li>{html.escape(fmt_finding(f))}</li>" for f in r.findings)
        detail += (
            f"<details><summary>{len(r.findings)} finding"
            f"{'s' if len(r.findings) != 1 else ''}</summary>"
            f'<ul class="findings">{items}</ul></details>'
        )
    pill = (
        '<span class="pill">blocking</span>' if getattr(r, "_blocking", False) else ""
    )
    category = html.escape(category_of(r))
    return (
        f'<tr class="{cls}" data-gate="{html.escape(r.name)}" '
        f'data-rag="{_HTML_SEV[r.outcome]}" data-cat="{category}">'
        f'<td class="emoji">{emoji}</td>'
        f"<td><strong>{html.escape(r.name)}</strong>{pill}</td>"
        f'<td class="cat-cell">{category}</td>'
        f'<td class="rag {cls}">{word}</td>'
        f'<td class="cell-detail">{detail}</td></tr>'
    )


def _advice_section(advice: dict, key: str, title: str, accent: str) -> str:
    """One titled LLM section, or the placeholder note when the model said
    nothing for it."""
    body = (advice.get(key) or "").strip()
    inner = _md_to_html(body) if body else _EMPTY_NOTE
    return (
        f'<div class="eyebrow">{title}</div>'
        f'<section class="summary {accent}">{inner}</section>'
    )


def _plain_remediation(eyebrow: str, raw: str) -> str:
    """The section when the LLM gave no per-gate structure: plain markdown, or
    nothing at all — every gate green means omitting the section entirely
    rather than printing a "No remediation needed." placeholder."""
    if _NO_REMEDIATION.match(raw):
        return ""
    inner = _md_to_html(raw) if raw else _EMPTY_NOTE
    return f'{eyebrow}<section class="summary accent-remediation">{inner}</section>'


def _rem_gate_html(name: str, body: str, outcome) -> str:
    """One gate's remediation block, labelled "name (RAG)"."""
    cls = outcome.name.lower() if outcome else "warn"
    word = RAG[outcome][3] if outcome else "WARN"
    return (
        f'<div class="rem-gate">{html.escape(name)} '
        f'<span class="badge {cls}">{word}</span></div>'
        f'<div class="rem-body">{_md_to_html(body)}</div>'
    )


def _remediation_html(advice: dict, outcome_of: dict, sev_order: dict) -> str:
    """The remediation section: gate blocks labelled "name (RAG)", failures
    first, or "" when there is nothing to fix."""
    eyebrow = '<div class="eyebrow">Remediation — fixes to raise the score</div>'
    groups = advice.get("remediation_groups") or []
    if not groups:
        return _plain_remediation(eyebrow, (advice.get("remediation") or "").strip())
    # One block, gates labelled "name (RAG)"; failures first, then warnings.
    ordered = sorted(
        groups,
        key=lambda g: sev_order.get(outcome_of.get(g[0]) or GateOutcome.PASS, 3),
    )
    pre = (advice.get("remediation_pre") or "").strip()
    parts = [f'<div class="rem-pre">{_md_to_html(pre)}</div>'] if pre else []
    parts += [
        _rem_gate_html(name, body, outcome_of.get(name)) for name, body in ordered
    ]
    return f'{eyebrow}<section class="summary accent-remediation">{"".join(parts)}</section>'


def render_html(
    label: str,
    results: list[GateResult],
    verdict: Verdict,
    advice: dict,
    meta: dict | None = None,
    diff: str = "",
) -> str:
    """Render the scorecard as one self-contained HTML file.

    Self-contained on purpose: no stylesheet, no script, no font to fetch, so
    the report opens from a CI artifact, an email attachment or a file:// URL
    and looks the same in all three.
    """
    vcls = verdict.outcome.name.lower()  # pass | warn | fail
    vword = RAG[verdict.outcome][3]

    # Group by category (Security, Dependencies, …), in a fixed order — used for
    # both the per-category score cards and the table's grouped rows.
    cards = []

    # Group results by category
    categorized_results: dict[str, list[GateResult]] = defaultdict(list)
    for r in results:
        categorized_results[category_of(r)].append(r)

    # Generate score cards
    for group in GROUP_ORDER:
        if group in categorized_results:
            gc, pct = group_outcome_and_pct(categorized_results[group])
            shown = "not run" if pct is None else f"{pct}%"
            cards.append(
                f'<div class="cat {gc.name.lower()}"><div class="cat-name">{group}</div>'
                f'<div class="cat-score">{shown}</div></div>'
            )

    cat_grid = f'<div class="cat-grid">{"".join(cards)}</div>' if cards else ""

    header_row = (
        "<tr><th></th>"
        '<th class="sortable" data-key="gate" data-label="Gate">Gate</th>'
        '<th class="sortable" data-key="cat" data-label="Category">Category</th>'
        '<th class="sortable" data-key="rag" data-label="Status">Status</th>'
        "<th>Detail</th></tr>"
    )
    # Default order: by category (in GROUP_ORDER), then name — sortable columns override.
    cat_index = {g: i for i, g in enumerate(GROUP_ORDER)}
    data_rows = [
        _gate_row(r)
        for r in sorted(
            results, key=lambda r: (cat_index.get(category_of(r), 99), r.name)
        )
    ]
    esc = html.escape(label)
    meta = meta or {}
    c = meta.get("commit") or {}
    bits = []
    if c.get("short"):
        bits.append(
            f"commit <code>{html.escape(c['short'])}</code> {html.escape(c.get('subject', ''))}"
        )
    if meta.get("generated_at"):
        bits.append(f"generated {html.escape(meta['generated_at'])}")
    metabar = (
        f'<div class="metabar">{" &nbsp;·&nbsp; ".join(bits)}</div>' if bits else ""
    )

    outcome_of = {r.name: r.outcome for r in results}
    sev_order = {GateOutcome.FAIL: 0, GateOutcome.WARN: 1, GateOutcome.PASS: 2}

    return (
        '<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>Gandalf — {esc}</title><style>{CSS}</style></head>"
        '<body><div class="wrap">'
        f"<header><h1>🧙 Gandalf <small>— {esc}</small></h1>"
        '<button id="themeBtn" aria-label="Toggle light/dark theme">🌙</button></header>'
        f"{metabar}"
        f'<div class="verdict {vcls}">{vword} &nbsp;·&nbsp; {verdict.score}/100'
        f"{html.escape(format_delta(meta.get('score_delta')))}</div>"
        '<div class="eyebrow">Summary</div>'
        f'<section class="summary">{_md_to_html(advice.get("summary") or "")}</section>'
        + _advice_section(
            advice,
            "changeset",
            "Changeset — what this stage / commit changes",
            "accent-changeset",
        )
        + _diff_html(diff)
        + '<div class="eyebrow">Scores by category</div>'
        + cat_grid
        + '<div class="filters">'
        + '<button class="filter-btn active" data-filter="all">All</button>'
        + '<button class="filter-btn" data-filter="fail">Fail</button>'
        + '<button class="filter-btn" data-filter="warn">Warn</button>'
        + '<button class="filter-btn" data-filter="pass">Pass</button>'
        + "</div>"
        + '<div class="table-scroll"><table><thead>'
        + header_row
        + "</thead>"
        f"<tbody>{''.join(data_rows)}</tbody></table></div>"
        + _remediation_html(advice, outcome_of, sev_order)
        + _advice_section(
            advice,
            "improvement",
            "Improvement — raise the bar further",
            "accent-improvement",
        )
        + '<footer><a href="https://github.com/fabiocicerchia/gandalf">'
        + "github.com/fabiocicerchia/gandalf</a> &middot; &copy; 2026 Fabio Cicerchia</footer>"
        + f"</div><script>{JS}</script></body></html>"
    )
