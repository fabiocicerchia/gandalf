"""The terminal footer: scorecard, setup banner, languages, fixes, policy."""

from __future__ import annotations

import shutil

from . import plugins, render_text
from .base import GateOutcome


def _tools_line(tools: dict) -> str:
    """One-line provenance summary for the terminal footer."""
    resolved = tools.get("resolved") or {}
    if not resolved:
        return ""
    host = sum(1 for v in resolved.values() if v["source"] == "host")
    image = sum(1 for v in resolved.values() if v["source"] == "image")
    parts = []
    if host:
        parts.append(f"{host} from PATH")
    if image:
        img = tools.get("image") or {}
        ident = (img.get("id") or "")[:19] or img.get("name", "")
        parts.append(f"{image} from {img.get('name', 'image')} ({ident})")
    line = f"Tools: {', '.join(parts)}"
    versioned = {n: v["version"] for n, v in resolved.items() if v.get("version")}
    if versioned:
        line += "\n" + "\n".join(
            f"  {n} ({resolved[n]['source']}) {v}" for n, v in sorted(versioned.items())
        )
    return line


def print_summary(
    sc,
    results,
    verdict,
    advice,
    meta_line,
    detected,
    skipped,
    disabled,
    fixes,
    cfg,
    passed,
    reason,
    tools,
    explain,
) -> None:
    """Terminal scorecard + the language / fixes / config / policy footer lines."""
    print(render_text.render_terminal(sc.label, results, verdict, advice, meta_line))
    if explain:
        print(render_text.explain_score(results, verdict))
    # Before the per-run footer: on a host with no scanners this is the only line
    # that tells the user anything actionable, so it must not be the last thing
    # after a wall of gate rows.
    if banner := render_text.setup_banner(
        results,
        plugins._tools_image_available(),
        bool(shutil.which("docker")),
    ):
        print(banner)
    print(
        f"\nLanguages: {', '.join(sorted(detected)) or 'none detected'}"
        + (
            f"  ·  skipped {len(skipped)} irrelevant gate(s): {', '.join(sorted(skipped))}"
            if skipped
            else ""
        )
        + (
            f"  ·  disabled {len(disabled)} by config: {', '.join(disabled)}"
            if disabled
            else ""
        )
    )
    if fixes:
        # `removeprefix`: a fixer that names its own gate ("ruff: 2 autofixed")
        # would otherwise print it twice.
        applied = [
            f"{n}: {m.removeprefix(f'{n}: ')}" for n, changed, m in fixes if changed
        ]
        print(
            "\nFixes applied:\n"
            + ("\n".join(f"  ✔ {a}" for a in applied) if applied else "  (none)")
        )
    if tools_line := _tools_line(tools):
        print(tools_line)
    if cfg.path:
        print(f"Config: {cfg.path}")
    if not passed and verdict.outcome != GateOutcome.FAIL:
        # RAG isn't red but policy fails the run — say so explicitly.
        print(f"Policy: run FAILED — {reason}")
