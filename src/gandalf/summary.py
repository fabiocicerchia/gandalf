"""The terminal footer: scorecard, setup banner, languages, fixes, policy."""

from __future__ import annotations

import shutil
from typing import TYPE_CHECKING

from . import console, plugins, render_text
from .base import GateOutcome

if TYPE_CHECKING:  # import-time cycle: these are only needed for annotations
    from .config import Config
    from .report import Run


def _image_part(tools: dict, image: int) -> str:
    """`N from <image> (<id>)` — the image is named by content id where it has
    one, since the tag is a moving target."""
    img = tools.get("image") or {}
    ident = (img.get("id") or "")[:19] or img.get("name", "")
    return f"{image} from {img.get('name', 'image')} ({ident})"


def _sources_line(tools: dict, resolved: dict) -> str:
    """`Tools: N from PATH, M from <image>` — where this run's scanners came from."""
    host = sum(1 for v in resolved.values() if v["source"] == "host")
    image = sum(1 for v in resolved.values() if v["source"] == "image")
    parts = []
    if host:
        parts.append(f"{host} from PATH")
    if image:
        parts.append(_image_part(tools, image))
    return f"Tools: {', '.join(parts)}"


def _versions_block(resolved: dict) -> str:
    """One indented line per scanner that reported a version, or ''."""
    versioned = {n: v["version"] for n, v in resolved.items() if v.get("version")}
    if not versioned:
        return ""
    return "\n" + "\n".join(f"  {n} ({resolved[n]['source']}) {v}" for n, v in sorted(versioned.items()))


def _tools_line(tools: dict) -> str:
    """One-line provenance summary for the terminal footer."""
    resolved = tools.get("resolved") or {}
    if not resolved:
        return ""
    return _sources_line(tools, resolved) + _versions_block(resolved)


def print_summary(run: Run, meta_line: dict, cfg: Config, *, explain: bool) -> None:
    """Terminal scorecard + the language / fixes / config / policy footer lines."""
    console.out(render_text.render_terminal(run.scope.label, run.results, run.verdict, run.advice, meta_line))
    if explain:
        console.out(render_text.explain_score(run.results, run.verdict))
    # Before the per-run footer: on a host with no scanners this is the only line
    # that tells the user anything actionable, so it must not be the last thing
    # after a wall of gate rows.
    if banner := render_text.setup_banner(
        run.results,
        plugins._tools_image_available(),
        bool(shutil.which("docker")),
    ):
        console.out(banner)
    console.out(
        f"\nLanguages: {', '.join(sorted(run.detected)) or 'none detected'}"
        + (
            f"  ·  skipped {len(run.skipped)} irrelevant gate(s): {', '.join(sorted(run.skipped))}"
            if run.skipped
            else ""
        )
        + (f"  ·  disabled {len(run.disabled)} by config: {', '.join(run.disabled)}" if run.disabled else "")
    )
    if run.fixes:
        # `removeprefix`: a fixer that names its own gate ("ruff: 2 autofixed")
        # would otherwise print it twice.
        applied = [f"{n}: {m.removeprefix(f'{n}: ')}" for n, changed, m in run.fixes if changed]
        console.out("\nFixes applied:\n" + ("\n".join(f"  ✔ {a}" for a in applied) if applied else "  (none)"))
    if tools_line := _tools_line(run.tools):
        console.out(tools_line)
    if cfg.path:
        console.out(f"Config: {cfg.path}")
    if not run.passed and run.verdict.outcome != GateOutcome.FAIL:
        # RAG isn't red but policy fails the run — say so explicitly.
        console.out(f"Policy: run FAILED — {run.reason}")
