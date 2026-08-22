"""Turn gate findings into GitHub PR review comments anchored to file:line.

`review_payload()` builds a summary `body` plus a `comments` array of
`{path, line, side, body}`. Findings on the same file:line merge into one
comment; findings GitHub would reject — no usable line, or a line the PR diff
never adds — roll up into the summary body so nothing is dropped.

`post()` is idempotent across re-runs: the summary lives in one sticky issue
comment that gets edited (with a "last updated" stamp) instead of re-posted,
and inline comments are diffed against what's already on the PR — unchanged
ones are left alone, obsolete ones resolved, new ones added. Nothing is ever
deleted; a resolved thread keeps the record of what was flagged and whatever
was said back. Both are recognised by a hidden HTML marker in the body. Stdlib
urllib only, no SDK — though resolving a thread is GraphQL-only. Without a
token and repo the caller just writes the JSON for a later CI step to post.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone

from .base import GateOutcome, GateResult
from .report import fmt_finding
from . import findings

# Hidden in the rendered comment; how a re-run finds what it posted last time.
_MARKER = "<!-- gandalf-pr-review -->"

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
    rule = findings.rule(f)
    tag = f"`{gate}`" + (f" · `{rule}`" if rule else "")
    return f"{_MARKER}\n**{_brand()[1]}** {tag}\n\n{fmt_finding(f)}"


_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


def added_lines(diff: str) -> dict[str, set[int]]:
    """path → line numbers the diff *adds* on the right-hand side. GitHub only
    accepts a review comment on such a line, so this is the anchorable set. An
    empty result (e.g. a --stat-only diff) means "unknown", not "none"."""
    out: dict[str, set[int]] = {}
    path, line, left = "", 0, 0
    for raw in diff.splitlines():
        if left > 0:  # inside a hunk: count new-side lines, skip deletions
            if raw.startswith(("-", "\\")):
                continue
            if raw.startswith("+") and path:
                out.setdefault(path, set()).add(line)
            line += 1
            left -= 1
        elif hunk := _HUNK.match(raw):
            line, left = int(hunk[1]), int(hunk[2] or 1)
        elif raw.startswith("+++ "):
            new = raw[4:].strip()
            path = "" if new == "/dev/null" else new.removeprefix("b/")
    return out


# `src/x.py:12:` at a word boundary — the shape compilers and linters print.
_TEXT_LOC = re.compile(r"(?:^|\s)([\w./\\-]+\.\w+):(\d+)(?=[:\s]|$)")


def _text_location(f: dict) -> tuple[str, int]:
    """Gates that only carry the location inside their message (mypy, tsc,
    codeql, …) would otherwise never anchor. A bogus parse costs nothing: the
    finding just fails the added-line check and rolls up as before."""
    hit = _TEXT_LOC.search(fmt_finding(f))
    return (hit[1], int(hit[2])) if hit else ("", 0)


def build(
    results: list[GateResult],
    changed_files: list[str] | None = None,
    diff: str = "",
    workdir: str = "",
) -> tuple[list[dict], list[str]]:
    """→ (inline_comments, overflow_lines). Inline comments are anchored to a
    line the diff adds; overflow is human-readable text for the summary."""
    changed = set(changed_files or [])
    added = added_lines(diff)
    inline: dict[tuple[str, int], list[str]] = {}
    overflow: list[str] = []
    for r in results:
        if r.outcome == GateOutcome.PASS:
            continue
        for f in r.findings:
            if not isinstance(f, dict):
                continue
            # Scanners run in the container against /src; GitHub wants the path
            # repo-relative, same rebase the SARIF writer does.
            path, line = findings.relpath(findings.path(f), workdir), findings.line(f)
            if not path or not line:
                text_path, text_line = _text_location(f)
                if text_path and text_line:
                    path, line = findings.relpath(text_path, workdir), text_line
            body = _comment_body(r.name, f)
            if added:
                anchorable = line in added.get(path, ())
            else:
                anchorable = (
                    bool(path) and line > 0 and (not changed or path in changed)
                )
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
    diff: str = "",
    workdir: str = "",
) -> dict:
    comments, overflow = build(results, changed_files, diff, workdir)
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
        shown = overflow[:max_overflow]
        # <details> keeps a long finding list from burying the PR conversation.
        # The blank line after </summary> is what lets GitHub render the
        # markdown inside; without it the list comes out as one flat blob.
        lines += [
            "",
            "<details>",
            f"<summary>Other findings — {len(overflow)} not on changed lines</summary>",
            "",
            *shown,
        ]
        if len(overflow) > max_overflow:
            lines.append(f"- …and {len(overflow) - max_overflow} more")
        lines += ["", "</details>"]
    if not comments and not overflow:
        lines.append("No findings. ✅")
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines += ["", f"<sub>Last updated {stamp}</sub>", "", _MARKER]
    # COMMENT (not REQUEST_CHANGES): GitHub forbids requesting changes on your own PR.
    return {"event": "COMMENT", "body": "\n".join(lines), "comments": comments}


def _ours(body: str | None) -> bool:
    """Ours to edit/delete. The marker covers everything posted since it was
    added; the prefix match also adopts comments from before it existed."""
    body = body or ""
    return _MARKER in body or body.lstrip().startswith(f"**{_brand()[1]}**")


def _api(
    method: str, url: str, token: str, data: dict | None = None, timeout: int = 30
) -> tuple[int, str]:
    req = urllib.request.Request(
        url,
        data=None if data is None else json.dumps(data).encode(),
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosec B310 — fixed https GitHub API URL
        return resp.status, resp.read().decode(errors="replace")


def _list_all(url: str, token: str, timeout: int) -> list[dict]:
    # ponytail: stops at 1000 comments; paginate properly if a PR ever gets there.
    out: list[dict] = []
    for page in range(1, 11):
        _, raw = _api("GET", f"{url}?per_page=100&page={page}", token, timeout=timeout)
        batch = json.loads(raw)
        out += batch
        if len(batch) < 100:
            break
    return out


def _sticky_summary(api: str, pr: int, body: str, token: str, timeout: int) -> str:
    """Edit our one summary comment in place, or create it the first time."""
    existing = _list_all(f"{api}/issues/{pr}/comments", token, timeout)
    mine = next((c["id"] for c in existing if _ours(c.get("body"))), 0)
    if mine:
        _api("PATCH", f"{api}/issues/comments/{mine}", token, {"body": body}, timeout)
        return f"updated summary comment {mine}"
    _api("POST", f"{api}/issues/{pr}/comments", token, {"body": body}, timeout)
    return "created summary comment"


# Review threads carry the resolve state, and only GraphQL exposes them — the
# REST comment id is not the thread id `resolveReviewThread` wants.
_THREADS = """
query($owner:String!,$name:String!,$pr:Int!,$after:String){
  repository(owner:$owner,name:$name){
    pullRequest(number:$pr){
      reviewThreads(first:100,after:$after){
        pageInfo{hasNextPage endCursor}
        nodes{id isResolved comments(first:1){nodes{path line body}}}
      }
    }
  }
}
"""
_RESOLVE = "mutation($id:ID!){resolveReviewThread(input:{threadId:$id}){thread{id}}}"


def _graphql(query: str, variables: dict, token: str, timeout: int) -> dict:
    _, raw = _api(
        "POST",
        "https://api.github.com/graphql",
        token,
        {"query": query, "variables": variables},
        timeout,
    )
    body = json.loads(raw)
    if body.get("errors"):  # GraphQL reports failures in a 200
        raise RuntimeError(str(body["errors"])[:200])
    return body["data"]


def _our_threads(repo: str, pr: int, token: str, timeout: int) -> list[dict]:
    """Our review threads as {id, resolved, key} — key matching what build()
    produces, so a thread and a wanted comment compare directly."""
    owner, _, name = repo.partition("/")
    out: list[dict] = []
    after = None
    for _ in range(10):  # ponytail: 1000 threads is far past any real PR
        page = _graphql(
            _THREADS,
            {"owner": owner, "name": name, "pr": pr, "after": after},
            token,
            timeout,
        )["repository"]["pullRequest"]["reviewThreads"]
        for node in page["nodes"]:
            first = (node["comments"]["nodes"] or [None])[0]
            if first and _ours(first["body"]):
                out.append(
                    {
                        "id": node["id"],
                        "resolved": node["isResolved"],
                        "key": (first["path"], first["line"], first["body"]),
                    }
                )
        if not page["pageInfo"]["hasNextPage"]:
            break
        after = page["pageInfo"]["endCursor"]
    return out


def _reconcile(
    threads: list[dict], comments: list[dict]
) -> tuple[list[str], list[dict]]:
    """→ (thread ids to resolve, comments to post). An already-resolved thread
    counts as absent, so a finding that comes back gets a fresh comment rather
    than silently staying hidden."""
    live = {t["key"]: t["id"] for t in threads if not t["resolved"]}
    want = {(c["path"], c["line"], c["body"]): c for c in comments}
    return (
        [tid for key, tid in live.items() if key not in want],
        [c for key, c in want.items() if key not in live],
    )


def _sync_inline(
    repo: str, pr: int, comments: list[dict], token: str, timeout: int
) -> str:
    """Reconcile inline comments with the PR: identical ones stay put (no reply
    thread lost, no notification), obsolete ones are *resolved* — never deleted,
    so the trail of what was flagged and any human reply survive — and new ones
    are posted."""
    api = f"https://api.github.com/repos/{repo}"
    stale, new = _reconcile(_our_threads(repo, pr, token, timeout), comments)
    resolved, resolve_failed = 0, 0
    for thread_id in stale:
        try:
            _graphql(_RESOLVE, {"id": thread_id}, token, timeout)
            resolved += 1
        except (urllib.error.HTTPError, urllib.error.URLError, OSError, RuntimeError):
            # Cosmetic: a thread left open is noise, not a reason to fail a run.
            resolve_failed += 1
    stuck = f", {resolve_failed} could not be resolved" if resolve_failed else ""
    if not new:
        return f"{len(comments)} inline comment(s) already current, {resolved} resolved{stuck}"
    _, raw = _api("GET", f"{api}/pulls/{pr}", token, timeout=timeout)
    head = json.loads(raw)["head"]["sha"]
    posted, failed = 0, 0
    for c in new:
        # One call each rather than one review: a line GitHub rejects costs that
        # comment, not the whole batch (and the review body would duplicate the
        # sticky summary, which is the comment pile-up we're avoiding).
        try:
            _api(
                "POST",
                f"{api}/pulls/{pr}/comments",
                token,
                {**c, "commit_id": head},
                timeout,
            )
            posted += 1
        except (urllib.error.HTTPError, urllib.error.URLError, OSError):
            failed += 1
    tail = f", {failed} rejected by GitHub" if failed else ""
    return f"posted {posted} inline comment(s), {resolved} resolved{stuck}{tail}"


def post(
    repo: str, pr: int, payload: dict, token: str, timeout: int = 30
) -> tuple[bool, str]:
    """Publish the review, replacing what the last run posted. Returns
    (ok, message). Never raises — a failed post must not fail the gandalf run."""
    if not (repo and token):
        return (False, "no repo/token — skipped (wrote JSON instead)")
    api = f"https://api.github.com/repos/{repo}"
    try:
        note = _sticky_summary(api, pr, payload["body"], token, timeout)
        return (
            True,
            f"{note}; {_sync_inline(repo, pr, payload['comments'], token, timeout)}",
        )
    except urllib.error.HTTPError as exc:
        return (
            False,
            f"GitHub {exc.code}: {exc.read().decode(errors='replace')[:200]}",
        )
    except (urllib.error.URLError, OSError) as exc:
        return (False, f"post failed: {exc}")
