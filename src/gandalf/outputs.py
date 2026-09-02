"""What a run leaves behind: the JSON run record and the optional HTML, SARIF,
JUnit, badge and PR-comment artifacts, plus the scanner-provenance block."""

from __future__ import annotations

import asyncio
import dataclasses
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import badge, junit, plugins, pr_comments, render_html, report, sarif, scope
from . import findings as gfindings


def destination(args, sc) -> tuple[Path, str]:
    """Where this run's artifacts go: the directory (created) and the file stem
    every one of them shares."""
    out_dir = (
        Path(args.out_dir) if args.out_dir else Path(scope.repo_root()) / "reports"
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(tz=timezone.utc).strftime("%Y%m%d-%H%M%S")
    return out_dir, f"gandalf-{sc.label.replace('/', '_')}-{ts}"


def tool_report(workdir: str, probe_versions: bool) -> dict:
    """Which scanner ran from where, and optionally at what version.

    Recorded because the same gate resolves differently on two machines — host
    binary here, container there, different versions of both — and until now the
    report gave no way to tell, so "it passes for me" had no answer. Provenance is
    free (the resolution already happened); versions cost a subprocess each and
    are opt-in behind --tool-versions.
    """
    sources = plugins.tool_sources()
    if not sources:
        return {}
    versions = asyncio.run(plugins.tool_versions(workdir)) if probe_versions else {}
    report_block: dict = {
        "resolved": {
            name: {
                "source": src,
                **({"version": versions[name]} if name in versions else {}),
            }
            for name, src in sorted(sources.items())
        }
    }
    if any(src == "image" for src in sources.values()):
        report_block["image"] = {
            "name": plugins.TOOLS_IMAGE,
            "id": plugins.tools_image_id(),
        }
    return report_block


def build_payload(
    sc,
    generated_at,
    detected,
    verdict,
    passed,
    policy,
    reason,
    advice,
    skipped,
    disabled,
    fixes,
    results,
    tools,
) -> dict:
    """The machine-readable run record written to reports/<stem>.json."""
    return {
        "scope": sc.label,
        "generated_at": generated_at,
        "commit": sc.commit,
        "languages": sorted(detected),
        "verdict": verdict.outcome.value,  # pass | warn | fail (RAG)
        "passed": passed,  # policy decision (drives exit code)
        "policy": {
            "fail_on": policy.fail_on.value,
            "min_score": policy.min_score,
            "reason": reason,
        },
        "score": verdict.score,
        "summary": advice["summary"],
        "changeset": advice.get("changeset", ""),
        "remediation": advice["remediation"],
        "improvement": advice["improvement"],
        "skipped_gates": sorted(skipped),
        "disabled_gates": disabled,
        "fixes": [{"gate": n, "changed": c, "message": m} for n, c, m in fixes],
        # Where each scanner actually came from this run (and, with
        # --tool-versions, at what version) — see _tool_report.
        "tools": tools,
        "gates": [
            {
                **dataclasses.asdict(r),
                # Each finding keeps its tool's own keys and gains a `_gandalf`
                # block with the reconciled path/line/rule/message/severity, so
                # a consumer never has to know that ruff says `location.row` and
                # trivy says `Target`. See gandalf/findings.py.
                "findings": gfindings.annotate_all(r.findings, sc.workdir),
                "category": report.category_of(r),
                "blocking": getattr(r, "_blocking", False),
                # True when the gate produced no signal about the code (tool not
                # installed, timed out, judge unreachable, nothing in scope). Such
                # gates are left out of `score` — see report.aggregate.
                "unavailable": plugins.did_not_run(r),
                "duration": getattr(r, "_duration", None),
            }
            for r in results
        ],
    }


def write_outputs(
    args, out_dir, stem, sc, results, verdict, advice, meta_line, payload
) -> None:
    """Write JSON (always) + optional HTML / SARIF / PR-comment artifacts."""
    # Always emit a JSON file for CI to parse. Dumped straight to the file
    # rather than through a string: the payload carries every finding, and
    # `write_text(dumps(...))` holds the whole rendered document in memory
    # alongside the object it was rendered from.
    json_path = out_dir / f"{stem}.json"
    with json_path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, default=str)
    print(f"\nJSON report: {json_path}")

    if not args.no_html:
        html_path = out_dir / f"{stem}.html"
        html_path.write_text(
            render_html.render_html(
                sc.label, results, verdict, advice, meta_line, sc.diff
            )
        )
        print(f"HTML report: {html_path}")

    if args.sarif is not None:
        sarif_path = Path(args.sarif) if args.sarif else out_dir / f"{stem}.sarif"
        with sarif_path.open("w", encoding="utf-8") as fh:
            json.dump(sarif.to_sarif(results, meta_line), fh, indent=2, default=str)
        print(f"SARIF report: {sarif_path}")

    if args.junit is not None:
        junit_path = Path(args.junit) if args.junit else out_dir / f"{stem}.junit.xml"
        junit_path.write_text(junit.to_junit(results, meta_line))
        print(f"JUnit report: {junit_path}")

    if args.badge is not None:
        badge_path = Path(args.badge) if args.badge else out_dir / f"{stem}-badge.json"
        badge_path.write_text(json.dumps(badge.to_badge(verdict), indent=2))
        print(f"Badge: {badge_path}")

    if args.pr_comments is not None or args.pr is not None:
        pr_payload = pr_comments.review_payload(
            results, verdict, sc.changed_files, diff=sc.diff, workdir=sc.workdir
        )
        pr_path = (
            Path(args.pr_comments)
            if args.pr_comments
            else out_dir / f"{stem}-pr-comments.json"
        )
        pr_path.write_text(json.dumps(pr_payload, indent=2, default=str))
        print(
            f"PR comments: {pr_path} ({len(pr_payload['comments'])} inline comment(s))"
        )
        if args.pr is not None:
            repo = args.pr_repo or os.environ.get("GITHUB_REPOSITORY", "")
            token = os.environ.get("GITHUB_TOKEN", "")
            _ok, msg = pr_comments.post(repo, args.pr, pr_payload, token)
            print(f"PR #{args.pr}: {msg}")

    if args.json:
        json.dump(payload, sys.stdout, indent=2, default=str)
        print()
