"""Draw the bench results as one self-contained SVG.

Same principle as gandalf's HTML report: no stylesheet, no script, no font to
fetch, so the file works from the docs site, a README, or a file:// URL. Stdlib
only — an SVG is text.

Two panels, not one chart with two axes: milliseconds and mebibytes are
different questions and a shared axis would make one of them a lie. Within a
panel the scale is linear, so an operation that costs almost nothing looks like
it costs almost nothing.
"""

from __future__ import annotations

from xml.sax.saxutils import escape

# Validated with the dataviz palette validator (six checks, both modes):
# slots 1 and 2 of the categorical theme, blue for the code as it ships and
# orange for the implementation it replaced.
LIGHT = {
    "surface": "#fcfcfb",
    "primary": "#0b0b0b",
    "secondary": "#52514e",
    "muted": "#8a8984",
    "grid": "#e6e5e1",
    "after": "#2a78d6",
    "before": "#eb6834",
}
DARK = {
    "surface": "#1a1a19",
    "primary": "#ffffff",
    "secondary": "#c3c2b7",
    "muted": "#8a8984",
    "grid": "#33322f",
    "after": "#3987e5",
    "before": "#d95926",
}

WIDTH = 900
GUTTER = 268  # Room for the longest label without truncating it.
RIGHT = 96  # Room for the value sitting past the end of the bar.
BAR = 15
PAIR_GAP = 2  # The surface gap the mark spec asks for between adjacent fills.
ROW_GAP = 13
PANEL_GAP = 34


def _nice_max(v: float) -> float:
    """A round number at or above `v`, so the gridlines land somewhere sane."""
    if v <= 0:
        return 1.0
    step = 10 ** (len(str(int(v))) - 1)
    # Fine enough that a 558 ms bar gets a 600 ms axis rather than a 1000 ms one
    # and half an empty panel. Every multiplier divides by 4 into round ticks.
    for mult in (1, 1.2, 1.6, 2, 2.4, 3, 4, 5, 6, 8, 10):
        if step * mult >= v:
            return step * mult
    return step * 10


def _fmt(v: float) -> str:
    if v >= 100:
        return f"{v:.0f}"
    if v >= 10:
        return f"{v:.1f}"
    return f"{v:.2f}".rstrip("0").rstrip(".")


def _row_height(row: dict) -> int:
    return BAR * 2 + PAIR_GAP if row.get("before") is not None else BAR


def _panel(rows: list[dict], unit: str, title: str, top: int) -> tuple[list[str], int]:
    """One panel: a titled group of bars sharing a single axis."""
    out: list[str] = []
    plot = WIDTH - GUTTER - RIGHT
    ceiling = _nice_max(max(max(r["after"], r.get("before") or 0) for r in rows))
    y = top

    out.append(
        f'<text x="0" y="{y}" class="panel-title">{escape(title)}'
        f'<tspan class="unit" dx="8">{escape(unit)}</tspan></text>'
    )
    y += 20

    axis_top = y
    body_rows: list[tuple[dict, int]] = []
    for row in rows:
        body_rows.append((row, y))
        y += _row_height(row) + ROW_GAP
    axis_bottom = y - ROW_GAP + 6

    # Grid first, so every mark sits on top of it.
    for i in range(5):
        gx = GUTTER + plot * i / 4
        out.append(
            f'<line x1="{gx:.1f}" y1="{axis_top - 4}" x2="{gx:.1f}" y2="{axis_bottom}" class="grid"/>'
        )
        out.append(
            f'<text x="{gx:.1f}" y="{axis_bottom + 14}" class="tick" text-anchor="middle">'
            f"{_fmt(ceiling * i / 4)}</text>"
        )

    for row, ry in body_rows:
        out.append(
            f'<text x="{GUTTER - 12}" y="{ry + _row_height(row) / 2 + 4:.1f}" '
            f'class="label" text-anchor="end">{escape(row["label"])}</text>'
        )
        bars = []
        if row.get("before") is not None:
            bars.append(("before", row["before"], ry))
            bars.append(("after", row["after"], ry + BAR + PAIR_GAP))
        else:
            bars.append(("after", row["after"], ry))
        for series, value, by in bars:
            # A 1px floor, so a genuinely negligible cost is visible as
            # negligible rather than absent.
            w = max(1.0, plot * value / ceiling)
            out.append(
                f'<rect x="{GUTTER}" y="{by}" width="{w:.1f}" height="{BAR}" '
                f'rx="4" class="bar {series}"><title>{escape(row["label"])} — '
                f"{series} {_fmt(value)} {escape(unit)}</title></rect>"
            )
            out.append(
                f'<text x="{GUTTER + w + 8:.1f}" y="{by + BAR - 3}" class="value">'
                f"{_fmt(value)}</text>"
            )
        if row.get("before") is not None and row["after"] > 0:
            factor = row["before"] / row["after"]
            if factor >= 1.15:
                out.append(
                    f'<text x="{WIDTH - 2}" y="{ry + _row_height(row) / 2 + 4:.1f}" '
                    f'class="delta" text-anchor="end">{factor:.1f}x</text>'
                )

    return out, axis_bottom + 24


def render(rows: list[dict]) -> str:
    """The whole figure. `rows` is what bench.py measured."""
    by_unit: dict[str, list[dict]] = {}
    for r in rows:
        by_unit.setdefault(r["unit"], []).append(r)
    for group in by_unit.values():
        group.sort(key=lambda r: r["after"], reverse=True)

    titles = {
        "ms": ("Time", "milliseconds, fastest of N runs — lower is better"),
        "MiB peak": ("Peak memory", "mebibytes held at once — lower is better"),
    }

    body: list[str] = []
    y = 86
    for unit in ("ms", "MiB peak"):
        if unit not in by_unit:
            continue
        title, caption = titles[unit]
        panel, y = _panel(by_unit[unit], caption, title, y)
        body.extend(panel)
        y += PANEL_GAP

    height = y + 8
    css_vars = "\n".join(f"    --{k}: {v};" for k, v in LIGHT.items())
    dark_vars = "\n".join(f"      --{k}: {v};" for k, v in DARK.items())

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{height}" \
viewBox="0 0 {WIDTH} {height}" font-family="ui-sans-serif, -apple-system, 'Segoe UI', Roboto, \
Helvetica, Arial, sans-serif" role="img" aria-label="Gandalf in-process hot paths, before and after">
  <style>
    svg {{
{css_vars}
      background: var(--surface);
    }}
    @media (prefers-color-scheme: dark) {{
      svg {{
{dark_vars}
      }}
    }}
    .chart-title {{ font-size: 15px; font-weight: 600; fill: var(--primary); }}
    .chart-sub   {{ font-size: 11.5px; fill: var(--secondary); }}
    .panel-title {{ font-size: 12px; font-weight: 600; fill: var(--primary); }}
    .unit        {{ font-weight: 400; fill: var(--muted); }}
    .label       {{ font-size: 11.5px; fill: var(--secondary); }}
    .value       {{ font-size: 11px; fill: var(--secondary); font-variant-numeric: tabular-nums; }}
    .delta       {{ font-size: 11px; font-weight: 600; fill: var(--primary); }}
    .tick        {{ font-size: 10px; fill: var(--muted); font-variant-numeric: tabular-nums; }}
    .grid        {{ stroke: var(--grid); stroke-width: 1; }}
    .bar.after   {{ fill: var(--after); }}
    .bar.before  {{ fill: var(--before); }}
    .legend      {{ font-size: 11.5px; fill: var(--secondary); }}
  </style>
  <rect width="{WIDTH}" height="{height}" fill="var(--surface)"/>
  <text x="0" y="18" class="chart-title">Where a scan's in-process time and memory go</text>
  <text x="0" y="36" class="chart-sub">20k findings across 40 gates — the work gandalf and the \
extension do themselves, excluding the gate subprocesses that dominate a real scan.</text>
  <rect x="0" y="50" width="11" height="11" rx="3" class="bar before"/>
  <text x="17" y="60" class="legend">previous implementation</text>
  <rect x="176" y="50" width="11" height="11" rx="3" class="bar after"/>
  <text x="193" y="60" class="legend">as it ships now</text>
{chr(10).join("  " + line for line in body)}
</svg>
"""
