"""Turn gate findings into GitHub PR review comments anchored to file:line.

`review_payload()` builds the body for GitHub's "Create a review" API
(`POST /repos/{repo}/pulls/{n}/reviews`): an `event`, a summary `body`, and a
`comments` array of `{path, line, side, body}`. Findings on the same file:line
merge into one comment; findings without a usable line — or outside the PR's
changed set (GitHub rejects comments off the diff) — roll up into the summary
body so nothing is dropped.

`post()` submits the review over the REST API with stdlib urllib (no SDK). It
needs a token and repo; without them the caller just writes the JSON for a
later CI step to post.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from .base import GateOutcome, GateResult
from .report import fmt_finding
from .sarif import _finding_line
from .suppress import finding_path, finding_rule

_RAG_WORD = {
    GateOutcome.PASS: "🟢",
    GateOutcome.WARN: "🟡",
    GateOutcome.FAIL: "🔴",
}


def _brand() -> tuple[str, str]:
    """(icon, name) shown in the comment text. Override to rebrand without a code
    fork; the account that authors the comment is set by the token, not here."""
    return (
        os.environ.get("GANDALF_PR_ICON", "🧙"),
        os.environ.get("GANDALF_PR_TITLE", "gandalf"),
    )


def _comment_body(gate: str, f: dict) -> str:
    rule = finding_rule(f)
    tag = f"`{gate}`" + (f" · `{rule}`" if rule else "")
    return f"**{_brand()[1]}** {tag}\n\n{fmt_finding(f)}"


def build(
    results: list[GateResult], changed_files: list[str] | None = None
) -> tuple[list[dict], list[str]]:
    """→ (inline_comments, overflow_lines). Inline comments are anchored to a
    line in the changed set; overflow is human-readable text for the summary."""
    changed = set(changed_files or [])
    inline: dict[tuple[str, int], list[str]] = {}
    overflow: list[str] = []
    for r in results:
        if r.outcome == GateOutcome.PASS:
            continue
        for f in r.findings:
            if not isinstance(f, dict):
                continue
            path, line = finding_path(f), _finding_line(f)
            body = _comment_body(r.name, f)
            anchorable = path and line > 0 and (not changed or path in changed)
            if anchorable:
                inline.setdefault((path, line), []).append(body)
            else:
                where = f"{path}:{line}" if path and line else (path or r.name)
                overflow.append(
                    f"- {_RAG_WORD[r.outcome]} `{r.name}` {where} — {fmt_finding(f)}"
                )
    comments = [
        {"path": p, "line": ln, "side": "RIGHT", "body": "\n\n---\n\n".join(bodies)}
        for (p, ln), bodies in sorted(inline.items())
    ]
    return comments, overflow


def review_payload(
    results: list[GateResult],
    verdict,
    changed_files: list[str] | None = None,
    max_overflow: int = 30,
) -> dict:
    comments, overflow = build(results, changed_files)
    word = {
        GateOutcome.PASS: "GREEN",
        GateOutcome.WARN: "AMBER",
        GateOutcome.FAIL: "RED",
    }[verdict.outcome]
    icon, name = _brand()
    header = f"{icon} {name}".strip()
    lines = [f"## {header} — {word} · {verdict.score}/100", ""]
    if comments:
        lines.append(f"{len(comments)} inline comment(s) below.")
    if overflow:
        lines += [
            "",
            "### Other findings (not on changed lines)",
            *overflow[:max_overflow],
        ]
        if len(overflow) > max_overflow:
            lines.append(f"- …and {len(overflow) - max_overflow} more")
    if not comments and not overflow:
        lines.append("No findings. ✅")
    # COMMENT (not REQUEST_CHANGES): GitHub forbids requesting changes on your own PR.
    return {"event": "COMMENT", "body": "\n".join(lines), "comments": comments}


def post(
    repo: str, pr: int, payload: dict, token: str, timeout: int = 30
) -> tuple[bool, str]:
    """Submit the review. Returns (ok, message). Never raises — a failed post
    must not fail the gandalf run."""
    if not (repo and token):
        return (False, "no repo/token — skipped (wrote JSON instead)")
    url = f"https://api.github.com/repos/{repo}/pulls/{pr}/reviews"
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosec B310 — fixed https GitHub API URL
            return (200 <= resp.status < 300, f"posted review ({resp.status})")
    except urllib.error.HTTPError as exc:
        return (
            False,
            f"GitHub {exc.code}: {exc.read().decode(errors='replace')[:200]}",
        )
    except (urllib.error.URLError, OSError) as exc:
        return (False, f"post failed: {exc}")
