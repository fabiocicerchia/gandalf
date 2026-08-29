"""gandalf CLI — evaluate the codebase, run pluggable gates, show RAG traffic lights.

    python -m gandalf                 # whole working tree, as-is
    python -m gandalf --staged        # staged changes only
    python -m gandalf --commit <sha>  # a specific commit (in a throwaway worktree)
    python -m gandalf --path <dir>    # limit scanning to a folder

Exit code is non-zero when the overall verdict is red, so it's CI-usable.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import dataclasses
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from . import (
    badge,
    debug,
    findings as gfindings,
    junit,
    llm,
    plugins,
    pr_comments,
    report,
    sarif,
    scope,
    severity,
    suppress,
)
from . import cache as gcache
from . import config as gconfig
from . import trend as gtrend
from .base import GateContext, GateOutcome
from .plugins import discover_gates
from .progress import Progress


async def _run_gates(gates, ctx, on_done=None, limit=0, timeouts=None, on_result=None):
    """Run gates concurrently, but at most `limit` at once (<=0 = unbounded).
    Bounding matters because ~35 gates each may spawn a `docker run`, which can
    swamp a laptop/CI runner if all launch simultaneously. `timeouts` is the
    [gandalf.timeouts] table; each gate's tool calls honour its own budget.
    `on_result(res)` fires as each gate finishes, for --stream."""
    total = len(gates)
    done = 0
    sem = asyncio.Semaphore(limit) if limit and limit > 0 else None

    async def one(g):
        nonlocal done
        plugins.GATE_TIMEOUT.set(_gate_timeout(g.name, timeouts))
        cm = sem if sem is not None else contextlib.nullcontext()
        debug.log(f"gate {g.name}: start")
        t0 = time.monotonic()
        async with cm:
            try:
                res = await g.run(ctx)
            except Exception as exc:  # noqa: BLE001 — a broken plugin must not sink the whole run
                from .base import GateResult

                res = GateResult(g.name, GateOutcome.WARN, 0.5, f"gate errored: {exc}")
        res._duration = round(time.monotonic() - t0, 3)
        res._blocking = getattr(g, "blocking", False)
        res._category = getattr(
            g, "category", ""
        )  # optional gate override for grouping
        done += 1  # asyncio is single-threaded → no lock needed
        debug.log(f"gate {g.name}: {res.outcome.value} in {res._duration:.2f}s")
        if on_done:
            on_done(done, total, g.name)
        if on_result:
            on_result(res)
        return res

    return await asyncio.gather(*(one(g) for g in gates))


def _tree_state(workdir: str) -> dict[str, str]:
    """path → a hash of that file's uncommitted content, for every file git
    currently sees as modified.

    A fixer reports what it did in whatever words its tool prints, and the tools
    disagree wildly: ruff counts what it fixed, `eslint --fix` says nothing at
    all and exits non-zero whenever anything unfixable is left over. Diffing the
    worktree either side of a fixer answers the question none of them answer —
    which files it actually rewrote — and answers it the same way for a plugin's
    fixer as for a built-in one. Empty, and so silent, outside a git worktree.
    """
    try:
        out = subprocess.run(  # nosec B603 B607 - fixed git argv, no shell
            ["git", "diff", "--no-color", "--no-ext-diff"],
            cwd=workdir,
            capture_output=True,
            text=True,
            check=False,
        ).stdout
    except OSError:
        return {}
    chunks: dict[str, list[str]] = {}
    body: list[str] | None = None
    for line in out.splitlines():
        if line.startswith("diff --git "):
            body = chunks.setdefault(line.split(" b/", 1)[-1], [])
        elif body is not None:
            body.append(line)
    return {
        path: hashlib.sha256("\n".join(lines).encode()).hexdigest()
        for path, lines in chunks.items()
    }


def _touched(before: dict[str, str], after: dict[str, str]) -> list[str]:
    """Files whose content differs between two worktree states."""
    return sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))


def _files_note(paths: list[str], limit: int = 5) -> str:
    """The rewritten files, named — and counted instead once there are too many
    of them to read in a terminal line."""
    shown = ", ".join(paths[:limit])
    return f"{shown}, …+{len(paths) - limit} more" if len(paths) > limit else shown


async def _run_fixers(gates, ctx):
    """Apply autofixes from gates that expose `async def fix(ctx)`. Sequential —
    fixers edit files (e.g. ruff --fix then ruff format on the same files), so
    order matters and concurrent writes would race. Returns [(name, changed, msg)].

    What each fixer changed is measured from the worktree rather than taken from
    its own word — see _tree_state."""
    out = []
    before = _tree_state(ctx.workdir)
    for g in gates:
        fix = getattr(g, "fix", None)
        if fix is None:
            continue
        try:
            changed, msg = await fix(ctx)
        except Exception as exc:  # noqa: BLE001 — a broken fixer must not sink the run
            changed, msg = False, f"fix errored: {exc}"
        after = _tree_state(ctx.workdir)
        if touched := _touched(before, after):
            changed, msg = True, f"{msg} — {_files_note(touched)}"
            debug.log(f"fix {g.name}: rewrote {len(touched)} file(s)")
        before = after
        out.append((g.name, changed, msg))
    return out


class _GateStream:
    """One NDJSON line per gate on stdout, as it completes.

    Without this a consumer learns nothing until the final report is written, so
    an editor pane sits empty for the whole run. Lines are emitted in completion
    order and the aggregate (verdict, composite score) still comes only from the
    final report — a gate result on its own can't produce one.

    Findings are passed through the suppressor first so a baselined finding
    doesn't flash up and then vanish when the report lands. Severity weighting is
    not applied, so a streamed `score` is preliminary; the report is the record.
    """

    def __init__(self, total: int, scope: str, sup, workdir: str = ""):
        self.total = total
        self.n = 0
        self.sup = sup
        self.workdir = workdir
        self._write({"event": "start", "scope": scope, "gates": total})

    def gate(self, r) -> None:
        self.n += 1
        shown = self.sup.apply(r) if self.sup.active else r
        self._write(
            {
                "event": "gate",
                "index": self.n,
                "total": self.total,
                **dataclasses.asdict(shown),
                "findings": gfindings.annotate_all(shown.findings, self.workdir),
                "category": report.category_of(r),
                "duration": getattr(r, "_duration", None),
                "blocking": getattr(r, "_blocking", False),
                "unavailable": plugins.did_not_run(r),
            }
        )

    @staticmethod
    def _write(obj: dict) -> None:
        # flush: the point is to be read while the process is still running.
        print(json.dumps(obj, default=str), flush=True)


def _baseline_path(explicit: str | None) -> str | None:
    """The baseline file to suppress from: an explicit --baseline, else the repo
    default when it exists. Shared so --stream suppresses exactly what the final
    report will."""
    if explicit:
        return explicit
    default = Path(scope.repo_root()) / suppress.DEFAULT_BASELINE
    return str(default) if default.is_file() else None


def _gate_timeout(name: str, timeouts: dict | None) -> int | None:
    """Per-gate subprocess budget from [gandalf.timeouts]: a gate-name key wins,
    else `default`, else None (fall back to the global GANDALF_GATE_TIMEOUT)."""
    if not timeouts:
        return None
    v = timeouts.get(name, timeouts.get("default"))
    try:
        return int(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _resolve_concurrency(cli: int | None, cfg) -> int:
    """Max gates in flight. Precedence: --concurrency → GANDALF_CONCURRENCY →
    [gandalf] concurrency → cpu count. <=0 anywhere means unbounded."""
    for src in (cli, os.environ.get("GANDALF_CONCURRENCY"), cfg.concurrency):
        if src is not None and str(src) != "":
            try:
                return int(src)
            except (TypeError, ValueError):
                continue
    return os.cpu_count() or 4


def _build_advice(args, sc, results, verdict, prog) -> dict:
    """LLM analysis section, or a skipped-stub when --no-llm."""
    if args.no_llm:
        return {
            "summary": "(LLM summary skipped)",
            "changeset": "",
            "remediation": "",
            "improvement": "",
        }
    prog.stage("LLM analysis")
    # Feed the actual findings (not just the summary) so remediation can be
    # specific — cite the file/line/package/rule instead of "fix the vulns".
    lines = []
    for r in sorted(results, key=lambda r: r.name):
        lines.append(f"- {r.name}: {r.outcome.value.upper()} — {r.summary}")
        if r.outcome != GateOutcome.PASS and r.findings:
            for f in r.findings[:15]:
                lines.append(f"    - {report.fmt_finding(f)}")
    return llm.analyze(
        sc.workdir,
        sc.label,
        sc.diff,
        f"{verdict.outcome.value.upper()} ({verdict.score}/100)",
        "\n".join(lines),
    )


def _print_summary(
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
) -> None:
    """Terminal scorecard + the language / fixes / config / policy footer lines."""
    print(report.render_terminal(sc.label, results, verdict, advice, meta_line))
    # Before the per-run footer: on a host with no scanners this is the only line
    # that tells the user anything actionable, so it must not be the last thing
    # after a wall of gate rows.
    if banner := report.setup_banner(
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


def _tool_report(workdir: str, probe_versions: bool) -> dict:
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


def _build_payload(
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


def _write_outputs(
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
            report.render_html(sc.label, results, verdict, advice, meta_line, sc.diff)
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


def _build_parser() -> argparse.ArgumentParser:
    """The CLI surface, in one place.

    Kept separate from main() so the flag table can be read — and tested —
    without running anything.
    """
    # RawDescriptionHelpFormatter, like the sibling CLIs: the module docstring
    # is a worked list of invocations, and reflowing it runs four commands
    # together into one paragraph.
    ap = argparse.ArgumentParser(
        prog="gandalf",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    grp = ap.add_mutually_exclusive_group()
    grp.add_argument("--commit", metavar="SHA", help="evaluate a specific commit")
    grp.add_argument(
        "--staged", action="store_true", help="evaluate staged changes only"
    )
    ap.add_argument(
        "--path",
        metavar="DIR",
        help="limit scanning to a folder (git-tracked files under it); "
        "combines with --staged/--commit to narrow the changed set",
    )
    ap.add_argument("--no-html", action="store_true", help="skip the HTML report")
    ap.add_argument(
        "--out-dir",
        metavar="DIR",
        help="write reports here instead of <repo>/reports (created if missing); "
        "lets an editor/CI keep its artifacts out of the working tree",
    )
    ap.add_argument(
        "--no-trend",
        action="store_true",
        help="don't append this run to .gandalf-trend.jsonl (the score delta is "
        "still read from it)",
    )
    ap.add_argument(
        "--sarif",
        nargs="?",
        const="",
        metavar="PATH",
        help="also write a SARIF 2.1.0 report (default: reports/<stem>.sarif)",
    )
    ap.add_argument(
        "--junit",
        nargs="?",
        const="",
        metavar="PATH",
        help="also write a JUnit XML report (default: reports/<stem>.junit.xml)",
    )
    ap.add_argument(
        "--badge",
        nargs="?",
        const="",
        metavar="PATH",
        help="also write a shields.io endpoint badge JSON (default: reports/<stem>-badge.json); "
        "point a README at https://img.shields.io/endpoint?url=<raw-URL-to-that-file>",
    )
    ap.add_argument(
        "--pr-comments",
        nargs="?",
        const="",
        metavar="PATH",
        help="write GitHub PR review comments (per-finding, file:line) as JSON "
        "(default: reports/<stem>-pr-comments.json)",
    )
    ap.add_argument(
        "--pr",
        type=int,
        metavar="N",
        help="post the PR comments to this PR number (needs GITHUB_TOKEN + repo)",
    )
    ap.add_argument(
        "--pr-repo",
        metavar="OWNER/REPO",
        help="repo for --pr (default: $GITHUB_REPOSITORY)",
    )
    ap.add_argument(
        "--json", action="store_true", help="also print machine-readable JSON"
    )
    ap.add_argument(
        "--stream",
        action="store_true",
        help="emit one NDJSON line per gate to stdout as it finishes (before the "
        "scorecard), so a consumer can show results during the run instead of "
        "waiting for the final report",
    )
    ap.add_argument("--no-llm", action="store_true", help="skip the LLM summary")
    ap.add_argument(
        "--debug",
        action="store_true",
        help="verbose stderr log: per-gate timing + every command run",
    )
    ap.add_argument(
        "--fix",
        action="store_true",
        help="let every gate whose tool can fix its own findings do so, in place, "
        "before scoring (ruff, ruff format, eslint, golangci-lint, clippy, "
        "sqlfluff, shellcheck, codespell). Ignored for --commit",
    )
    ap.add_argument("--target", help="live URL for dynamic gates (nikto/sqlmap/dalfox)")
    ap.add_argument(
        "--allow-remote",
        action="store_true",
        help="permit dynamic scans against a non-localhost --target",
    )
    ap.add_argument("--title", help="request title for the compliance gate")
    ap.add_argument(
        "--body", help="request body / acceptance criteria for the compliance gate"
    )
    ap.add_argument(
        "--config", metavar="PATH", help="path to a .gandalf.toml (default: repo root)"
    )
    ap.add_argument(
        "--exclude",
        action="append",
        metavar="GLOB",
        help="skip paths matching GLOB, for every gate. Repeatable. Same matching "
        "as .gandalfignore: a bare name skips that directory anywhere "
        "(node_modules), a path anchors at the repo root (src/generated), and "
        "globs work (*.min.js). Adds to .gandalfignore rather than replacing it",
    )
    ap.add_argument(
        "--fail-on",
        choices=("fail", "warn"),
        help="lowest outcome that fails the run (default: fail)",
    )
    ap.add_argument(
        "--min-score",
        type=int,
        metavar="N",
        help="fail the run if the composite score is below N (0-100)",
    )
    ap.add_argument(
        "--concurrency",
        type=int,
        metavar="N",
        help="max gates running at once (<=0 = unbounded; default: CPU count)",
    )
    ap.add_argument(
        "--severity-weight",
        action="store_true",
        help="weight each gate's score by its findings' severity",
    )
    ap.add_argument(
        "--baseline",
        metavar="PATH",
        help="baseline file of accepted findings to suppress (default: .gandalf-baseline.json)",
    )
    ap.add_argument(
        "--write-baseline",
        nargs="?",
        const=suppress.DEFAULT_BASELINE,
        metavar="PATH",
        help="write current findings to a baseline file (default path if none given)",
    )
    ap.add_argument(
        "--tool-versions",
        action="store_true",
        help="probe the version of every scanner that ran and record it in the "
        "report (one extra subprocess per tool)",
    )
    ap.add_argument(
        "--cache",
        nargs="?",
        const=gcache.DEFAULT_CACHE,
        metavar="PATH",
        help="reuse a gate's prior result when the scanned files are unchanged "
        "(default path if none given); ignored with --target/--title/--body, "
        "since those affect gates without changing any file",
    )
    return ap


def main(argv: list[str] | None = None) -> int:
    """Run gandalf and return the process exit status.

    Returns rather than exits, so the same entry point serves the console
    script, `python -m gandalf` and the tests.
    """
    args = _build_parser().parse_args(argv)

    if args.debug:
        debug.enable()

    cfg = gconfig.load(scope.repo_root(), args.config)
    debug.log(f"config: {cfg.path or '(defaults)'}")

    # Before any gate resolves its file list, so every gate sees the same scope.
    excludes = list(args.exclude or []) + [
        str(x) for x in (cfg.data.get("exclude") or [])
    ]
    # Always set, even when empty: this is process state, and a second run in
    # the same process must not inherit the first one's exclusions.
    plugins.set_extra_ignores(excludes)
    # Same reason: tool resolutions are process state, and a second run in one
    # process (the editor extension) must not report the first run's tools.
    plugins.reset_tool_sources()
    if excludes:
        debug.log(f"excluding {len(excludes)} extra pattern(s): {', '.join(excludes)}")

    gates = discover_gates()
    if not gates:
        print("no gates discovered", file=sys.stderr)
        return 2
    # Config gate selection (only/skip) happens before language filtering below.
    gates, disabled = cfg.select(gates)
    if not gates:
        print("all gates disabled by config selection", file=sys.stderr)
        return 2

    do_fix = args.fix and not args.commit
    if args.fix and args.commit:
        print("--fix ignored for --commit (throwaway worktree)", file=sys.stderr)
    prog = Progress((3 if args.no_llm else 4) + (1 if do_fix else 0))
    prog.stage("Resolving scope")
    with scope.resolve(args.commit, args.staged, args.path) as sc:
        # Only run gates relevant to the languages in scope, plus the generic
        # (untagged) ones. So a Go change doesn't trigger eslint/mypy, etc.
        detected = scope.languages(sc.workdir, sc.changed_files)
        active = [
            g
            for g in gates
            if not getattr(g, "langs", None) or (set(g.langs) & detected)
        ]
        skipped = [g.name for g in gates if g not in active]

        meta = {
            "diff": sc.diff,
            "target": args.target or "",
            "allow_remote": args.allow_remote,
            "languages": sorted(detected),
            "title": args.title or "",
            "body": args.body or "",
            "fix": do_fix,  # a gate may run its tool differently under --fix
            "config": cfg,
        }
        ctx = GateContext(
            repo=sc.workdir,
            workdir=sc.workdir,
            changed_files=sc.changed_files,
            meta=meta,
        )
        fixes = []
        if do_fix:
            prog.stage("Applying fixes")
            fixes = asyncio.run(_run_fixers(active, ctx))

        cache_path = None
        cache_data: dict = {}
        file_hash = ""
        to_run = active
        if args.cache is not None and not (args.target or args.title or args.body):
            cache_path = str(Path(scope.repo_root()) / args.cache)
            cache_data = gcache.load(cache_path)
            file_hash = gcache.content_hash(
                sc.workdir,
                gcache.target_files(sc.workdir, sc.changed_files),
                salt=gcache.toolchain_salt(),
            )
            to_run = [
                g
                for g in active
                if gcache.get(cache_data, g.name, file_hash, gcache.max_age(g)) is None
            ]

        limit = _resolve_concurrency(args.concurrency, cfg)
        debug.log(f"running {len(to_run)} gate(s), concurrency={limit or 'unbounded'}")
        prog.stage(f"Running {len(to_run)} gates")
        # A stream-only suppressor, read now so streamed findings match what the
        # report will show. Built separately from the one below on purpose: that
        # one runs after --write-baseline, and must keep loading what it wrote.
        stream = (
            _GateStream(
                len(active),
                sc.label,
                suppress.build(cfg.section("suppress"), _baseline_path(args.baseline)),
                sc.workdir,
            )
            if args.stream
            else None
        )
        fresh = asyncio.run(
            _run_gates(
                to_run,
                ctx,
                on_done=prog.bar,
                limit=limit,
                timeouts=cfg.section("timeouts"),
                on_result=stream.gate if stream else None,
            )
        )

        if cache_path is not None:
            for r in fresh:
                gcache.put(cache_data, r.name, file_hash, r)
            gcache.save(cache_path, cache_data)
            cached = [
                gcache.get(cache_data, g.name, file_hash, gcache.max_age(g))
                for g in active
                if g not in to_run
            ]
            by_name = {r.name: r for r in fresh + cached}
            results = [by_name[g.name] for g in active]
            if stream:  # cache hits never ran, so nothing has reported them yet
                for r in cached:
                    stream.gate(r)
        else:
            results = fresh

        if debug.enabled():
            slowest = sorted(
                results, key=lambda r: getattr(r, "_duration", 0.0), reverse=True
            )[:5]
            debug.log(
                "slowest gates: "
                + ", ".join(
                    f"{r.name} {getattr(r, '_duration', 0.0):.2f}s" for r in slowest
                )
            )

        if args.write_baseline is not None:
            bpath = str(Path(scope.repo_root()) / args.write_baseline)
            stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
            n = suppress.write_baseline(bpath, results, generated_at=stamp)
            print(f"Wrote baseline: {bpath} ({n} finding(s))")

        # Suppress accepted/baselined findings before scoring, so a legacy repo's
        # known issues don't fail the gate — only new findings can. Resolved again
        # here rather than reused from the --stream suppressor above: this runs
        # after --write-baseline, and must load what that just wrote.
        sup = suppress.build(cfg.section("suppress"), _baseline_path(args.baseline))
        if sup.active:
            results = [sup.apply(r) for r in results]

        # Severity-weight scores (after suppression, so muted findings don't count).
        if args.severity_weight or cfg.section("severity").get("weight"):
            results = [severity.reweight(r) for r in results]

        verdict = report.aggregate(results)

        policy = report.Policy.from_config(
            cfg.section("verdict"), args.fail_on, args.min_score
        )
        passed, reason = report.decide(verdict, policy)

        advice = _build_advice(args, sc, results, verdict, prog)

        prog.stage("Writing reports")
        prog.finish()  # end the single progress line before the scorecard prints
        generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        trend_path = str(Path(scope.repo_root()) / gtrend.DEFAULT_TREND)
        commit_short = sc.commit.get("short", "")
        score_delta = gtrend.previous_score(trend_path, commit_short)
        if score_delta is not None:
            score_delta = verdict.score - score_delta
        if commit_short and not args.no_trend:
            gtrend.record(trend_path, commit_short, verdict.score, generated_at)
        meta_line = {
            "generated_at": generated_at,
            "commit": sc.commit,
            "score_delta": score_delta,
            "workdir": sc.workdir,  # lets sarif.to_sarif rebase paths repo-relative
        }
        tools = _tool_report(sc.workdir, args.tool_versions)
        _print_summary(
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
        )

        out_dir = (
            Path(args.out_dir) if args.out_dir else Path(scope.repo_root()) / "reports"
        )
        out_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(tz=timezone.utc).strftime("%Y%m%d-%H%M%S")
        stem = f"gandalf-{sc.label.replace('/', '_')}-{ts}"
        payload = _build_payload(
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
        )
        _write_outputs(
            args, out_dir, stem, sc, results, verdict, advice, meta_line, payload
        )

    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
