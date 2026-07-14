"""RAG traffic-light rendering: terminal (ANSI) + self-contained HTML report."""

from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass

from .base import GateOutcome, GateResult


# Finding dicts come from many tools, so the same field goes by different keys.
# First truthy value wins (order = preference), mirroring the old or-chains.
_LOC_KEYS = ("path", "filename", "file", "file_path")
_LINE_KEYS = ("line", "line_number", "Line")
_MSG_KEYS = (
    "message",
    "issue_text",
    "description",
    "Description",
    "check_name",
    "error",
    "issue",
    "finding",
    "typo",
    "missing",
    "judge_summary",
    "rule_id",
    "VulnerabilityID",
    "QueryName",
)


def _first(f: dict, keys: tuple[str, ...]):
    for k in keys:
        if f.get(k):
            return f[k]
    return ""


def fmt_finding(f) -> str:
    """One-line, human-readable rendering of a heterogeneous gate finding."""
    if not isinstance(f, dict):
        return str(f)[:500]
    loc = _first(f, _LOC_KEYS)
    line = _first(f, _LINE_KEYS)
    msg = _first(f, _MSG_KEYS)
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
    # Best-practices / compliance
    "compliance": "Best practices",
    # Skill-backed advisory gates (LLM judges built from embedded skills/)
    "grill_me": "Design readiness",
    "codebase_architecture": "Architecture",
    "well_architected": "Well-Architected",
}
_GROUP_ORDER = (
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


def _category_of(r: GateResult) -> str:
    return getattr(r, "_category", "") or _CATEGORY.get(r.name, "Other")


# outcome → (emoji, ansi, hex, label)
_RAG = {
    GateOutcome.PASS: ("🟢", "\033[32m", "#22c55e", "GREEN"),
    GateOutcome.WARN: ("🟡", "\033[33m", "#eab308", "AMBER"),
    GateOutcome.FAIL: ("🔴", "\033[31m", "#ef4444", "RED"),
}
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
# Shown in place of an empty LLM section so it reads as "skipped", not "missing".
_EMPTY_NOTE = (
    '<p class="empty-note">Not generated for this run '
    "(LLM was skipped or unavailable).</p>"
)
# The model's "everything passes" reply — matched loosely (markdown/punctuation
# tolerated) so the remediation section is omitted rather than showing a placeholder.
_NO_REMEDIATION = re.compile(r"^\W*no remediation needed\W*$", re.I)


@dataclass
class Verdict:
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
    ) -> "Policy":
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


def aggregate(results: list[GateResult]) -> Verdict:
    """Red if any FAIL (blocking or not); amber if any WARN; green if all pass.
    Composite score = mean of gate sub-scores ×100."""
    if not results:
        return Verdict(GateOutcome.WARN, 0)
    if any(r.outcome == GateOutcome.FAIL for r in results):
        overall = GateOutcome.FAIL
    elif any(r.outcome == GateOutcome.WARN for r in results):
        overall = GateOutcome.WARN
    else:
        overall = GateOutcome.PASS
    score = round(sum(r.score for r in results) / len(results) * 100)
    return Verdict(overall, score)


def render_terminal(
    label: str,
    results: list[GateResult],
    verdict: Verdict,
    advice: dict,
    meta: dict | None = None,
) -> str:
    meta = meta or {}
    lines = [f"\n{_BOLD}🧙  GANDALF{_RESET} {_DIM}— {label}{_RESET}"]
    c = meta.get("commit") or {}
    if c.get("short"):
        lines.append(f"{_DIM}commit {c['short']} — {c.get('subject', '')}{_RESET}")
    if meta.get("generated_at"):
        lines.append(f"{_DIM}generated {meta['generated_at']}{_RESET}")
    word = _RAG[verdict.outcome][3]
    lines.append(
        f"\n{_BANNER[verdict.outcome]}  {word} · {verdict.score}/100  {_RESET}"
    )

    # Gates grouped by category, each header coloured by its aggregate RAG + score.
    width = max((len(r.name) for r in results), default=4)
    for group in _GROUP_ORDER:
        members = sorted(
            (r for r in results if _category_of(r) == group), key=lambda r: r.name
        )
        if not members:
            continue
        gc = (
            GateOutcome.FAIL
            if any(r.outcome == GateOutcome.FAIL for r in members)
            else GateOutcome.WARN
            if any(r.outcome == GateOutcome.WARN for r in members)
            else GateOutcome.PASS
        )
        pct = round(sum(r.score for r in members) / len(members) * 100)
        gcol = _RAG[gc][1]
        lines.append(f"\n{_BOLD}{gcol}{group}{_RESET} {_DIM}· {pct}%{_RESET}")
        for r in members:
            emoji, color, _, w = _RAG[r.outcome]
            block = (
                f" {_DIM}[blocking]{_RESET}" if getattr(r, "_blocking", False) else ""
            )
            lines.append(
                f"  {emoji} {color}{r.name.ljust(width)}{_RESET}  {r.summary}{block}"
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
        word = _RAG[outcome][3] if outcome else "WARN"
        blocks.append(f"{name} ({word}):\n{body}")
    return "\n\n".join(blocks)


def _md_to_html(text: str) -> str:
    """Tiny, dependency-free markdown → HTML for the LLM summary: headings, bold,
    italic, inline code, links, and un/ordered lists. Everything is HTML-escaped
    before our own tags go in."""

    def inline(s: str) -> str:
        s = html.escape(s)
        s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
        s = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r'<a href="\2">\1</a>', s)
        s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
        s = re.sub(r"(?<!\w)\*([^*]+)\*(?!\w)", r"<em>\1</em>", s)
        s = re.sub(r"(?<!\w)_([^_]+)_(?!\w)", r"<em>\1</em>", s)
        return s

    out: list[str] = []
    para: list[str] = []
    items: list[str] = []
    otype = ""

    def flush_para() -> None:
        if para:
            out.append("<p>" + inline(" ".join(para)) + "</p>")
            para.clear()

    def flush_list() -> None:
        nonlocal otype
        if items:
            out.append(
                f"<{otype}>"
                + "".join(f"<li>{inline(i)}</li>" for i in items)
                + f"</{otype}>"
            )
            items.clear()
            otype = ""

    for raw in text.splitlines():
        line = raw.rstrip()
        if not line.strip():
            flush_para()
            flush_list()
            continue
        h = re.match(r"(#{1,6})\s+(.*)", line)
        ul = re.match(r"\s*[-*+]\s+(.*)", line)
        ol = re.match(r"\s*\d+\.\s+(.*)", line)
        if h:
            flush_para()
            flush_list()
            lvl = min(len(h.group(1)), 6)
            out.append(f"<h{lvl}>{inline(h.group(2))}</h{lvl}>")
        elif ul:
            flush_para()
            if otype and otype != "ul":
                flush_list()
            otype = "ul"
            items.append(ul.group(1))
        elif ol:
            flush_para()
            if otype and otype != "ol":
                flush_list()
            otype = "ol"
            items.append(ol.group(1))
        else:
            flush_list()
            para.append(line.strip())
    flush_para()
    flush_list()
    return "\n".join(out) or "<p>(no summary)</p>"


_CSS = """
:root{ --bg:#fff; --fg:#1b1d22; --muted:#6b7280; --border:#e4e6eb; --card:#f7f8fa;
  --tint:0.15; --pass:#22c55e; --warn:#eab308; --fail:#ef4444; --warn-text:#a16207; }
@media (prefers-color-scheme:dark){ :root:not([data-theme=light]){
  --bg:#0f1115; --fg:#e6e8eb; --muted:#9aa0a6; --border:#272b33; --card:#171a20;
  --tint:0.24; --warn-text:#fbbf24; } }
:root[data-theme=dark]{ --bg:#0f1115; --fg:#e6e8eb; --muted:#9aa0a6; --border:#272b33;
  --card:#171a20; --tint:0.24; --warn-text:#fbbf24; }
*{box-sizing:border-box}
body{ margin:0; background:var(--bg); color:var(--fg); line-height:1.6;
  font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif; }
.wrap{ width:75%; margin:2.5rem auto; }
@media (max-width:820px){ .wrap{ width:92%; } }
header{ display:flex; align-items:center; justify-content:space-between; gap:1rem; }
h1{ font-size:1.5rem; margin:0; font-weight:700; }
h1 small{ color:var(--muted); font-weight:400; }
.metabar{ margin-top:.6rem; color:var(--muted); font-size:.85rem; }
.metabar code{ background:rgba(127,127,127,.18); padding:.1em .4em; border-radius:5px; }
#themeBtn{ cursor:pointer; border:1px solid var(--border); background:var(--card);
  color:var(--fg); border-radius:9px; padding:.5rem .75rem; font-size:1rem; line-height:1; }
.verdict{ margin:1.25rem 0; padding:1.05rem 1.5rem; border-radius:12px; color:#fff;
  font-size:1.4rem; font-weight:700; letter-spacing:.3px; }
.verdict.pass{ background:var(--pass); } .verdict.warn{ background:var(--warn); }
.verdict.fail{ background:var(--fail); }
.cat-grid{ display:flex; flex-wrap:wrap; gap:.6rem; margin:.2rem 0 .3rem; }
.cat{ flex:1 1 190px; padding:.6rem .85rem; border-radius:10px; color:#fff; }
.cat.pass{ background:var(--pass); } .cat.fail{ background:var(--fail); }
.cat.warn{ background:var(--warn); color:#3a2d00; }
.cat-name{ font-size:.72rem; text-transform:uppercase; letter-spacing:.04em; font-weight:600; opacity:.9; }
.cat-score{ font-size:1.5rem; font-weight:700; line-height:1.1; }
.eyebrow{ text-transform:uppercase; letter-spacing:.08em; font-size:.72rem;
  color:var(--muted); font-weight:600; margin:1.4rem 0 .45rem; }
.summary{ background:var(--card); border:1px solid var(--border); border-radius:12px;
  padding:1.1rem 1.4rem; }
.summary>:first-child{ margin-top:0; } .summary>:last-child{ margin-bottom:0; }
.summary.accent-changeset{ border-left:4px solid #06b6d4; }
.summary.accent-remediation{ border-left:4px solid var(--warn); }
.summary.accent-improvement{ border-left:4px solid #3b82f6; }
.summary h1,.summary h2,.summary h3{ font-size:1.05rem; margin:1rem 0 .4rem; }
.summary code{ background:rgba(127,127,127,.18); padding:.1em .35em; border-radius:5px; font-size:.9em; }
.summary a{ color:#3b82f6; }
.empty-note{ color:var(--muted); font-style:italic; margin:0; }
/* Scroll the table sideways on narrow screens instead of the whole page. */
.table-scroll{ margin-top:1.5rem; overflow-x:auto; -webkit-overflow-scrolling:touch; }
table{ width:100%; min-width:552px; table-layout:fixed; border-collapse:separate;
  border-spacing:0; border:1px solid var(--border); border-radius:12px; overflow:hidden; }
/* Fixed columns so expanding a Detail cell never shifts the others. */
th:nth-child(1),td:nth-child(1){ width:44px; }
th:nth-child(2),td:nth-child(2){ width:270px; }
th:nth-child(3),td:nth-child(3){ width:150px; }
th:nth-child(4),td:nth-child(4){ width:88px; }
th,td{ padding:13px 18px; text-align:left; border-bottom:1px solid var(--border);
  vertical-align:top; word-break:break-word; }
thead th{ background:var(--card); font-size:.78rem; text-transform:uppercase;
  letter-spacing:.05em; color:var(--muted); }
th.sortable{ cursor:pointer; user-select:none; }
th.sortable:hover{ color:var(--fg); }
td.cat-cell{ color:var(--muted); font-size:.85rem; }
tbody tr:last-child td{ border-bottom:none; }
tr.pass td{ background:rgba(34,197,94,var(--tint)); }
tr.warn td{ background:rgba(234,179,8,var(--tint)); }
tr.fail td{ background:rgba(239,68,68,var(--tint)); }
.emoji{ font-size:1.3rem; white-space:nowrap; }
.rag{ font-weight:700; white-space:nowrap; }
.rag.pass{ color:var(--pass); } .rag.warn{ color:var(--warn-text); } .rag.fail{ color:var(--fail); }
.pill{ margin-left:.5rem; font-size:.62rem; text-transform:uppercase; letter-spacing:.05em;
  background:rgba(127,127,127,.2); color:var(--muted); padding:.18em .55em; border-radius:999px;
  vertical-align:middle; font-weight:700; white-space:nowrap; }
.cell-detail small{ display:block; margin-top:.3rem; color:var(--muted); font-size:.8rem;
  word-break:break-word; }
.cell-detail details{ margin-top:.4rem; }
.cell-detail summary{ cursor:pointer; color:var(--muted); font-size:.8rem; user-select:none; }
.cell-detail summary:hover{ color:var(--fg); }
ul.findings{ margin:.45rem 0 0; padding-left:1.1rem; }
ul.findings li{ font-size:.8rem; color:var(--muted); word-break:break-word; margin:.2rem 0;
  font-family:ui-monospace,Menlo,Consolas,monospace; }
/* Remediation: one block; each gate labelled "name (RAG-badge)", failures first. */
.rem-pre{ color:var(--muted); margin:0 0 .7rem; }
.rem-gate{ font-weight:700; margin:1.1rem 0 .35rem; display:flex; align-items:center; gap:.5rem; }
.rem-gate:first-child{ margin-top:0; }
.rem-body{ margin-left:.1rem; }
.rem-body>:first-child{ margin-top:0; } .rem-body>:last-child{ margin-bottom:0; }
.badge{ display:inline-block; font-size:.66rem; font-weight:700; text-transform:uppercase;
  letter-spacing:.04em; padding:.2em .55em; border-radius:6px; color:#fff; }
.badge.fail{ background:var(--fail); } .badge.pass{ background:var(--pass); }
.badge.warn{ background:var(--warn); color:#3a2d00; }
"""

_JS = """
(function(){
  var root=document.documentElement, btn=document.getElementById('themeBtn');
  var saved=localStorage.getItem('gandalf-theme'); if(saved) root.dataset.theme=saved;
  function cur(){ return root.dataset.theme ||
    (matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light'); }
  function paint(){ btn.textContent = cur()==='dark' ? '\\u2600\\uFE0F' : '\\uD83C\\uDF19'; }
  btn.onclick=function(){ var n=cur()==='dark'?'light':'dark';
    root.dataset.theme=n; localStorage.setItem('gandalf-theme',n); paint(); };
  paint();

  // Click-to-sort the Gate / Category / Status columns.
  var tbody=document.querySelector('tbody'), dir={};
  document.querySelectorAll('th.sortable').forEach(function(th){
    th.onclick=function(){
      var key=th.dataset.key;
      var d=dir[key]=dir[key]?-dir[key]:(key==='rag'?-1:1);
      function cmp(a,b){
        if(key==='rag') return d*(+a.dataset.rag - +b.dataset.rag);
        var av=key==='cat'?a.dataset.cat:a.dataset.gate;
        var bv=key==='cat'?b.dataset.cat:b.dataset.gate;
        return d*av.localeCompare(bv) || a.dataset.gate.localeCompare(b.dataset.gate);
      }
      var rows=[].slice.call(tbody.rows);
      rows.sort(cmp);
      rows.forEach(function(r){ tbody.appendChild(r); });
      document.querySelectorAll('th.sortable').forEach(function(x){ x.textContent=x.dataset.label; });
      th.textContent=th.dataset.label+(d===1?' \\u25B2':' \\u25BC');
    };
  });
})();
"""


def render_html(
    label: str,
    results: list[GateResult],
    verdict: Verdict,
    advice: dict,
    meta: dict | None = None,
) -> str:
    vcls = verdict.outcome.name.lower()  # pass | warn | fail
    vword = _RAG[verdict.outcome][3]
    sev = {GateOutcome.PASS: 0, GateOutcome.WARN: 1, GateOutcome.FAIL: 2}

    def row(r: GateResult) -> str:
        emoji, _, _, word = _RAG[r.outcome]
        cls = r.outcome.name.lower()
        detail = html.escape(r.summary)
        if r.findings:
            items = "".join(
                f"<li>{html.escape(fmt_finding(f))}</li>" for f in r.findings
            )
            detail += (
                f"<details><summary>{len(r.findings)} finding"
                f"{'s' if len(r.findings) != 1 else ''}</summary>"
                f'<ul class="findings">{items}</ul></details>'
            )
        pill = (
            '<span class="pill">blocking</span>'
            if getattr(r, "_blocking", False)
            else ""
        )
        category = html.escape(_category_of(r))
        return (
            f'<tr class="{cls}" data-gate="{html.escape(r.name)}" '
            f'data-rag="{sev[r.outcome]}" data-cat="{category}">'
            f'<td class="emoji">{emoji}</td>'
            f"<td><strong>{html.escape(r.name)}</strong>{pill}</td>"
            f'<td class="cat-cell">{category}</td>'
            f'<td class="rag {cls}">{word}</td>'
            f'<td class="cell-detail">{detail}</td></tr>'
        )

    # Group by category (Security, Dependencies, …), in a fixed order — used for
    # both the per-category score cards and the table's grouped rows.
    cards = []

    # Group results by category
    categorized_results: dict[str, list[GateResult]] = {}
    for r in results:
        category = _category_of(r)
        categorized_results.setdefault(category, []).append(r)

    # Generate score cards
    for group in _GROUP_ORDER:
        if group in categorized_results:
            members = categorized_results[group]
            if any(r.outcome == GateOutcome.FAIL for r in members):
                gcls = "fail"
            elif any(r.outcome == GateOutcome.WARN for r in members):
                gcls = "warn"
            else:
                gcls = "pass"
            pct = round(sum(r.score for r in members) / len(members) * 100)
            cards.append(
                f'<div class="cat {gcls}"><div class="cat-name">{group}</div>'
                f'<div class="cat-score">{pct}%</div></div>'
            )

    cat_grid = f'<div class="cat-grid">{"".join(cards)}</div>' if cards else ""

    header_row = (
        "<tr><th></th>"
        '<th class="sortable" data-key="gate" data-label="Gate">Gate</th>'
        '<th class="sortable" data-key="cat" data-label="Category">Category</th>'
        '<th class="sortable" data-key="rag" data-label="Status">Status</th>'
        "<th>Detail</th></tr>"
    )
    # Default order: by category (in _GROUP_ORDER), then name — sortable columns override.
    cat_index = {g: i for i, g in enumerate(_GROUP_ORDER)}
    data_rows = [
        row(r)
        for r in sorted(
            results, key=lambda r: (cat_index.get(_category_of(r), 99), r.name)
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

    def section(key: str, title: str, accent: str) -> str:
        body = (advice.get(key) or "").strip()
        inner = _md_to_html(body) if body else _EMPTY_NOTE
        return (
            f'<div class="eyebrow">{title}</div>'
            f'<section class="summary {accent}">{inner}</section>'
        )

    outcome_of = {r.name: r.outcome for r in results}
    sev_order = {GateOutcome.FAIL: 0, GateOutcome.WARN: 1, GateOutcome.PASS: 2}

    def remediation_html() -> str:
        eyebrow = '<div class="eyebrow">Remediation — fixes to raise the score</div>'
        groups = advice.get("remediation_groups") or []
        raw = (advice.get("remediation") or "").strip()
        if not groups:  # LLM gave no per-gate structure → plain markdown or a note
            # Nothing to fix (every gate green) → omit the section entirely rather
            # than printing a "No remediation needed." placeholder.
            if _NO_REMEDIATION.match(raw):
                return ""
            inner = _md_to_html(raw) if raw else _EMPTY_NOTE
            return f'{eyebrow}<section class="summary accent-remediation">{inner}</section>'
        # One block, gates labelled "name (RAG)"; failures first, then warnings.
        ordered = sorted(
            groups,
            key=lambda g: sev_order.get(outcome_of.get(g[0]) or GateOutcome.PASS, 3),
        )
        pre = (advice.get("remediation_pre") or "").strip()
        parts = [f'<div class="rem-pre">{_md_to_html(pre)}</div>'] if pre else []
        for name, body in ordered:
            outcome = outcome_of.get(name)
            cls = outcome.name.lower() if outcome else "warn"
            word = _RAG[outcome][3] if outcome else "WARN"
            parts.append(
                f'<div class="rem-gate">{html.escape(name)} '
                f'<span class="badge {cls}">{word}</span></div>'
                f'<div class="rem-body">{_md_to_html(body)}</div>'
            )
        return f'{eyebrow}<section class="summary accent-remediation">{"".join(parts)}</section>'

    return (
        '<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>Gandalf — {esc}</title><style>{_CSS}</style></head>"
        '<body><div class="wrap">'
        f"<header><h1>🧙 Gandalf <small>— {esc}</small></h1>"
        '<button id="themeBtn" aria-label="Toggle light/dark theme">🌙</button></header>'
        f"{metabar}"
        f'<div class="verdict {vcls}">{vword} &nbsp;·&nbsp; {verdict.score}/100</div>'
        '<div class="eyebrow">Summary</div>'
        f'<section class="summary">{_md_to_html(advice.get("summary") or "")}</section>'
        + section(
            "changeset",
            "Changeset — what this stage / commit changes",
            "accent-changeset",
        )
        + '<div class="eyebrow">Scores by category</div>'
        + cat_grid
        + '<div class="table-scroll"><table><thead>'
        + header_row
        + "</thead>"
        f"<tbody>{''.join(data_rows)}</tbody></table></div>"
        + remediation_html()
        + section(
            "improvement", "Improvement — raise the bar further", "accent-improvement"
        )
        + f"</div><script>{_JS}</script></body></html>"
    )
