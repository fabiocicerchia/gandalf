"""The CLI surface: every flag gandalf accepts, in one place.

Kept apart from the run so the flag table can be read — and tested — without
running anything.
"""

from __future__ import annotations

import argparse

from . import cache as gcache
from . import suppress

# argparse prints this as the CLI description; it is the module docstring of
# `python -m gandalf`, kept here because the parser is what shows it.
_DESCRIPTION = """gandalf CLI — evaluate the codebase, run pluggable gates, show RAG traffic lights.

    python -m gandalf                 # whole working tree, as-is
    python -m gandalf --staged        # staged changes only
    python -m gandalf --commit <sha>  # a specific commit (in a throwaway worktree)
    python -m gandalf --path <dir>    # limit scanning to a folder

Exit code is non-zero when the overall verdict is red, so it's CI-usable.
"""


def build_parser() -> argparse.ArgumentParser:
    """The CLI surface, in one place.

    Kept separate from main() so the flag table can be read — and tested —
    without running anything.
    """
    # RawDescriptionHelpFormatter, like the sibling CLIs: the module docstring
    # is a worked list of invocations, and reflowing it runs four commands
    # together into one paragraph.
    ap = argparse.ArgumentParser(
        prog="gandalf",
        description=_DESCRIPTION,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    grp = ap.add_mutually_exclusive_group()
    grp.add_argument("--commit", metavar="SHA", help="evaluate a specific commit")
    grp.add_argument("--staged", action="store_true", help="evaluate staged changes only")
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
        help="don't append this run to .gandalf-trend.jsonl (the score delta is still read from it)",
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
    ap.add_argument("--json", action="store_true", help="also print machine-readable JSON")
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
    ap.add_argument("--body", help="request body / acceptance criteria for the compliance gate")
    ap.add_argument("--config", metavar="PATH", help="path to a .gandalf.toml (default: repo root)")
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
        "--explain-score",
        action="store_true",
        help="show how the composite score was arrived at: every gate that counted, its score, and what it contributed",
    )
    ap.add_argument(
        "--tool-versions",
        action="store_true",
        help="probe the version of every scanner that ran and record it in the report (one extra subprocess per tool)",
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
