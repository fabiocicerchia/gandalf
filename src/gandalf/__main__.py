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
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from . import cache as gcache
from . import config as gconfig
from . import debug
from . import llm, plugins, pr_comments, report, sarif, scope, severity, suppress
from . import trend as gtrend
from .base import GateContext, GateOutcome
from .plugins import discover_gates
from .progress import Progress


async def _run_gates(gates, ctx, on_done=None, limit=0, timeouts=None):
    """Run gates concurrently, but at most `limit` at once (<=0 = unbounded).
    Bounding matters because ~35 gates each may spawn a `docker run`, which can
    swamp a laptop/CI runner if all launch simultaneously. `timeouts` is the
    [gandalf.timeouts] table; each gate's tool calls honour its own budget."""
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
            except Exception as exc:  # a broken plugin must not sink the whole run
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
        return res

    return await asyncio.gather(*(one(g) for g in gates))


async def _run_fixers(gates, ctx):
    """Apply autofixes from gates that expose `async def fix(ctx)`. Sequential —
    fixers edit files (e.g. ruff --fix then ruff format on the same files), so
    order matters and concurrent writes would race. Returns [(name, changed, msg)]."""
    out = []
    for g in gates:
        fix = getattr(g, "fix", None)
        if fix is None:
            continue
        try:
            changed, msg = await fix(ctx)
        except Exception as exc:  # a broken fixer must not sink the run
            changed, msg = False, f"fix errored: {exc}"
        out.append((g.name, changed, msg))
    return out


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
) -> None:
    """Terminal scorecard + the language / fixes / config / policy footer lines."""
    print(report.render_terminal(sc.label, results, verdict, advice, meta_line))
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
        applied = [f"{n}: {m}" for n, changed, m in fixes if changed]
        print(
            "\nFixes applied:\n"
            + ("\n".join(f"  ✔ {a}" for a in applied) if applied else "  (none)")
        )
    if cfg.path:
        print(f"Config: {cfg.path}")
    if not passed and verdict.outcome != GateOutcome.FAIL:
        # RAG isn't red but policy fails the run — say so explicitly.
        print(f"Policy: run FAILED — {reason}")


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
        "gates": [
            {
                **dataclasses.asdict(r),
                "blocking": getattr(r, "_blocking", False),
                "duration": getattr(r, "_duration", None),
            }
            for r in results
        ],
    }


def _write_outputs(
    args, out_dir, stem, sc, results, verdict, advice, meta_line, payload
) -> None:
    """Write JSON (always) + optional HTML / SARIF / PR-comment artifacts."""
    # Always emit a JSON file for CI to parse.
    json_path = out_dir / f"{stem}.json"
    json_path.write_text(json.dumps(payload, indent=2, default=str))
    print(f"\nJSON report: {json_path}")

    if not args.no_html:
        html_path = out_dir / f"{stem}.html"
        html_path.write_text(
            report.render_html(sc.label, results, verdict, advice, meta_line)
        )
        print(f"HTML report: {html_path}")

    if args.sarif is not None:
        sarif_path = Path(args.sarif) if args.sarif else out_dir / f"{stem}.sarif"
        sarif_path.write_text(
            json.dumps(sarif.to_sarif(results, meta_line), indent=2, default=str)
        )
        print(f"SARIF report: {sarif_path}")

    if args.pr_comments is not None or args.pr is not None:
        pr_payload = pr_comments.review_payload(results, verdict, sc.changed_files)
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
        print(json.dumps(payload, indent=2, default=str))


def _build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="gandalf", description=__doc__)
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
        "--sarif",
        nargs="?",
        const="",
        metavar="PATH",
        help="also write a SARIF 2.1.0 report (default: reports/<stem>.sarif)",
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
    ap.add_argument("--no-llm", action="store_true", help="skip the LLM summary")
    ap.add_argument(
        "--debug",
        action="store_true",
        help="verbose stderr log: per-gate timing + every command run",
    )
    ap.add_argument(
        "--fix",
        action="store_true",
        help="apply gate autofixes (ruff, format, eslint) before scoring",
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
    args = _build_parser().parse_args(argv)

    if args.debug:
        debug.enable()

    cfg = gconfig.load(scope.repo_root(), args.config)
    debug.log(f"config: {cfg.path or '(defaults)'}")

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
            if not getattr(g, "langs", None) or (set(getattr(g, "langs")) & detected)
        ]
        skipped = [g.name for g in gates if g not in active]

        meta = {
            "diff": sc.diff,
            "target": args.target or "",
            "allow_remote": args.allow_remote,
            "languages": sorted(detected),
            "title": args.title or "",
            "body": args.body or "",
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
                sc.workdir, gcache.target_files(sc.workdir, sc.changed_files)
            )
            to_run = [
                g for g in active if gcache.get(cache_data, g.name, file_hash) is None
            ]

        limit = _resolve_concurrency(args.concurrency, cfg)
        debug.log(f"running {len(to_run)} gate(s), concurrency={limit or 'unbounded'}")
        prog.stage(f"Running {len(to_run)} gates")
        fresh = asyncio.run(
            _run_gates(
                to_run,
                ctx,
                on_done=prog.bar,
                limit=limit,
                timeouts=cfg.section("timeouts"),
            )
        )

        if cache_path is not None:
            for r in fresh:
                gcache.put(cache_data, r.name, file_hash, r)
            gcache.save(cache_path, cache_data)
            cached = [
                gcache.get(cache_data, g.name, file_hash)
                for g in active
                if g not in to_run
            ]
            by_name = {r.name: r for r in fresh + cached}
            results = [by_name[g.name] for g in active]
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
        # known issues don't fail the gate — only new findings can.
        default_bl = Path(scope.repo_root()) / suppress.DEFAULT_BASELINE
        baseline_path = args.baseline or (
            str(default_bl) if default_bl.is_file() else None
        )
        sup = suppress.build(cfg.section("suppress"), baseline_path)
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
        if commit_short:
            gtrend.record(trend_path, commit_short, verdict.score, generated_at)
        meta_line = {
            "generated_at": generated_at,
            "commit": sc.commit,
            "score_delta": score_delta,
        }
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
        )

        out_dir = Path(scope.repo_root()) / "reports"
        out_dir.mkdir(exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
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
        )
        _write_outputs(
            args, out_dir, stem, sc, results, verdict, advice, meta_line, payload
        )

    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
