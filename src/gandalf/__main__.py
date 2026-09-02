"""gandalf CLI — evaluate the codebase, run pluggable gates, show RAG traffic lights.

    python -m gandalf                 # whole working tree, as-is
    python -m gandalf --staged        # staged changes only
    python -m gandalf --commit <sha>  # a specific commit (in a throwaway worktree)
    python -m gandalf --path <dir>    # limit scanning to a folder

Exit code is non-zero when the overall verdict is red, so it's CI-usable.

The entry point and the run itself: resolve the scope, run the gates, apply the
policy. The flag table is in `cli`, the artifacts in `outputs`, the terminal
footer in `summary`.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from . import cache as gcache
from . import config as gconfig
from . import debug, llm, outputs, plugins, report, scope, severity, suppress
from . import summary as gsummary
from . import trend as gtrend
from .base import GateContext, GateOutcome
from .cli import build_parser
from .fixers import run_fixers
from .plugins import discover_gates
from .progress import Progress
from .stream import GateStream


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


def _apply_excludes(args, cfg) -> None:
    """Set the process-wide exclusions before any gate resolves its file list,
    so every gate sees the same scope.

    Always set, even when empty: this is process state, and a second run in the
    same process (the editor extension) must not inherit the first one's
    exclusions. Tool resolutions are process state for the same reason.
    """
    excludes = list(args.exclude or []) + [
        str(x) for x in (cfg.data.get("exclude") or [])
    ]
    plugins.set_extra_ignores(excludes)
    plugins.reset_tool_sources()
    if excludes:
        debug.log(f"excluding {len(excludes)} extra pattern(s): {', '.join(excludes)}")


def _select_gates(cfg) -> tuple[list, list, str]:
    """(gates to run, gates the config disabled, error message).

    A non-empty message means there is nothing to run. Config selection
    (only/skip) happens here, before the language filtering in `_active_gates`.
    """
    gates = discover_gates()
    if not gates:
        return [], [], "no gates discovered"
    gates, disabled = cfg.select(gates)
    if not gates:
        return [], [], "all gates disabled by config selection"
    return gates, disabled, ""


def _fix_mode(args) -> bool:
    """Whether --fix applies. It cannot under --commit: that runs in a throwaway
    worktree, so anything fixed there is discarded with it."""
    if args.fix and args.commit:
        print("--fix ignored for --commit (throwaway worktree)", file=sys.stderr)
        return False
    return bool(args.fix)


def _progress(no_llm: bool, do_fix: bool) -> Progress:
    """One stage per phase this run will actually go through."""
    return Progress((3 if no_llm else 4) + (1 if do_fix else 0))


def _active_gates(gates: list, detected: set) -> tuple[list, list[str]]:
    """(gates worth running here, names of the ones skipped).

    Only gates relevant to the languages in scope, plus the generic (untagged)
    ones — so a Go change doesn't trigger eslint/mypy, etc.
    """
    active = [
        g for g in gates if not getattr(g, "langs", None) or (set(g.langs) & detected)
    ]
    return active, [g.name for g in gates if g not in active]


def _gate_context(args, cfg, sc, detected: set, do_fix: bool) -> GateContext:
    """The context every gate is handed."""
    return GateContext(
        repo=sc.workdir,
        workdir=sc.workdir,
        changed_files=sc.changed_files,
        meta={
            "diff": sc.diff,
            "target": args.target or "",
            "allow_remote": args.allow_remote,
            "languages": sorted(detected),
            "title": args.title or "",
            "body": args.body or "",
            "fix": do_fix,  # a gate may run its tool differently under --fix
            "config": cfg,
        },
    )


def _cache_plan(args, sc) -> gcache.Plan:
    """The result cache for this run, or an inert plan.

    --target, --title and --body change what a gate reports without changing a
    file, and the content hash cannot see them — so they disable the cache.
    """
    if args.cache is None or args.target or args.title or args.body:
        return gcache.Plan()
    path = str(Path(scope.repo_root()) / args.cache)
    file_hash = gcache.content_hash(
        sc.workdir,
        gcache.target_files(sc.workdir, sc.changed_files),
        salt=gcache.toolchain_salt(),
    )
    return gcache.Plan(path, gcache.load(path), file_hash)


def _stream(args, cfg, n_gates: int, sc) -> GateStream | None:
    """The --stream reporter, or None.

    Its suppressor is built here and deliberately not reused for the report:
    that one runs after --write-baseline and must load what that just wrote.
    """
    if not args.stream:
        return None
    return GateStream(
        n_gates,
        sc.label,
        suppress.build(cfg.section("suppress"), _baseline_path(args.baseline)),
        sc.workdir,
    )


def _log_slowest(results) -> None:
    """The five slowest gates, under --debug."""
    if not debug.enabled():
        return
    slowest = sorted(results, key=lambda r: getattr(r, "_duration", 0.0), reverse=True)[
        :5
    ]
    debug.log(
        "slowest gates: "
        + ", ".join(f"{r.name} {getattr(r, '_duration', 0.0):.2f}s" for r in slowest)
    )


def _write_baseline(args, results) -> None:
    """--write-baseline: accept everything this run found, so only new findings
    can fail the next one."""
    if args.write_baseline is None:
        return
    bpath = str(Path(scope.repo_root()) / args.write_baseline)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    n = suppress.write_baseline(bpath, results, generated_at=stamp)
    print(f"Wrote baseline: {bpath} ({n} finding(s))")


@dataclass(frozen=True)
class Scored:
    """A run after the policy has had its say: the results as they will be
    reported, the composite they add up to, and the pass/fail call."""

    results: list
    verdict: report.Verdict
    policy: report.Policy
    passed: bool
    reason: str


def _score(args, cfg, results) -> Scored:
    """Suppress, reweight, aggregate, decide — in that order.

    Suppression comes first so a legacy repo's known issues don't fail the gate;
    only new findings can. Severity weighting comes after it, so muted findings
    don't count toward the weight.
    """
    sup = suppress.build(cfg.section("suppress"), _baseline_path(args.baseline))
    if sup.active:
        results = [sup.apply(r) for r in results]
    if args.severity_weight or cfg.section("severity").get("weight"):
        results = [severity.reweight(r) for r in results]
    verdict = report.aggregate(results)
    policy = report.Policy.from_config(
        cfg.section("verdict"), args.fail_on, args.min_score
    )
    passed, reason = report.decide(verdict, policy)
    return Scored(results, verdict, policy, passed, reason)


def _meta_line(args, sc, verdict, generated_at: str) -> dict:
    """The report header block — and, on the way, this run's trend entry."""
    trend_path = str(Path(scope.repo_root()) / gtrend.DEFAULT_TREND)
    commit_short = sc.commit.get("short", "")
    previous = gtrend.previous_score(trend_path, commit_short)
    if commit_short and not args.no_trend:
        gtrend.record(trend_path, commit_short, verdict.score, generated_at)
    return {
        "generated_at": generated_at,
        "commit": sc.commit,
        "score_delta": None if previous is None else verdict.score - previous,
        "workdir": sc.workdir,  # lets sarif.to_sarif rebase paths repo-relative
    }


def main(argv: list[str] | None = None) -> int:
    """Run gandalf and return the process exit status.

    Returns rather than exits, so the same entry point serves the console
    script, `python -m gandalf` and the tests.
    """
    args = build_parser().parse_args(argv)

    if args.debug:
        debug.enable()

    cfg = gconfig.load(scope.repo_root(), args.config)
    debug.log(f"config: {cfg.path or '(defaults)'}")
    _apply_excludes(args, cfg)

    gates, disabled, problem = _select_gates(cfg)
    if problem:
        print(problem, file=sys.stderr)
        return 2

    do_fix = _fix_mode(args)
    prog = _progress(args.no_llm, do_fix)
    prog.stage("Resolving scope")
    with scope.resolve(args.commit, args.staged, args.path) as sc:
        detected = scope.languages(sc.workdir, sc.changed_files)
        active, skipped = _active_gates(gates, detected)
        ctx = _gate_context(args, cfg, sc, detected, do_fix)

        fixes = []
        if do_fix:
            prog.stage("Applying fixes")
            fixes = asyncio.run(run_fixers(active, ctx))

        plan = _cache_plan(args, sc)
        to_run = plan.pending(active)
        limit = _resolve_concurrency(args.concurrency, cfg)
        debug.log(f"running {len(to_run)} gate(s), concurrency={limit or 'unbounded'}")
        prog.stage(f"Running {len(to_run)} gates")
        stream = _stream(args, cfg, len(active), sc)
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
        results, cached = plan.merge(fresh, active, to_run)
        if stream:  # cache hits never ran, so nothing has reported them yet
            for r in cached:
                stream.gate(r)

        _log_slowest(results)
        _write_baseline(args, results)
        scored = _score(args, cfg, results)
        results, verdict, passed = scored.results, scored.verdict, scored.passed

        advice = _build_advice(args, sc, results, verdict, prog)

        prog.stage("Writing reports")
        prog.finish()  # end the single progress line before the scorecard prints
        generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        meta_line = _meta_line(args, sc, verdict, generated_at)
        tools = outputs.tool_report(sc.workdir, args.tool_versions)
        gsummary.print_summary(
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
            scored.reason,
            tools,
            args.explain_score,
        )

        out_dir, stem = outputs.destination(args, sc)
        payload = outputs.build_payload(
            sc,
            generated_at,
            detected,
            verdict,
            passed,
            scored.policy,
            scored.reason,
            advice,
            skipped,
            disabled,
            fixes,
            results,
            tools,
        )
        outputs.write_outputs(
            args, out_dir, stem, sc, results, verdict, advice, meta_line, payload
        )

    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
