"""Generic codebase summary via the headroom OpenAI-compatible endpoint.
Stdlib urllib only — no SDK dependency. Degrades to a one-line note if the
endpoint is unreachable so gates still run.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

from . import debug

LLM_URL = os.environ.get("GANDALF_LLM_URL", "http://127.0.0.1:8787/v1")
MODEL = os.environ.get("GANDALF_MODEL", "gpt-oss-120b")
MAX_TOKENS = int(os.environ.get("GANDALF_MAX_TOKENS", "8000"))
API_KEY = os.environ.get("GANDALF_API_KEY", "sk-no-key-required")

# Transient-failure retry: a flaky network shouldn't silently degrade the summary.
RETRIES = int(
    os.environ.get("GANDALF_LLM_RETRIES", "3")
)  # 3 retries before a judge skips (4 attempts)
BACKOFF = float(os.environ.get("GANDALF_LLM_BACKOFF", "1.0"))  # base seconds
# Retry only on transient HTTP statuses; 4xx (bad request/auth) won't fix on retry.
_RETRY_STATUS = frozenset({429, 500, 502, 503, 504})


def _retryable(exc: Exception) -> bool:
    """Whether a request failure is worth retrying.

    Transport failures and the transient status codes only. A 4xx that is not
    in that set is a bad request, and retrying it just spends the same tokens
    on the same rejection.
    """
    if isinstance(exc, urllib.error.HTTPError):  # subclass of URLError — check first
        return exc.code in _RETRY_STATUS
    return isinstance(exc, (urllib.error.URLError, TimeoutError, OSError))


def _request_with_retry(req: urllib.request.Request, timeout: int) -> dict:
    """POST with exponential backoff on transient failures. Raises the last
    exception once retries are exhausted (or immediately for non-retryable ones)."""
    for attempt in range(RETRIES + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosec B310 — operator-configured endpoint
                return json.load(resp)
        except Exception as exc:
            if attempt >= RETRIES or not _retryable(exc):
                raise
            delay = BACKOFF * (2**attempt)
            debug.log(
                f"LLM request failed ({exc}); retry {attempt + 1}/{RETRIES} in {delay:.1f}s"
            )
            time.sleep(delay)
    raise RuntimeError("unreachable")  # loop either returns or raises


def _context(workdir: str, label: str, diff: str) -> str:
    """Build the repo context sent alongside the findings.

    Truncated hard: the summary is worth what the model can attend to, and a
    whole README plus a whole diff is mostly tokens spent on neither.
    """
    root = Path(workdir)
    readme = ""
    for name in ("README.md", "README", "readme.md"):
        p = root / name
        if p.is_file():
            readme = p.read_text(errors="replace")[:2000]
            break
    try:
        tree = subprocess.run(  # nosec B603 B607 - fixed git argv, no shell
            ["git", "ls-files"],
            cwd=workdir,
            capture_output=True,
            text=True,
            check=False,
        ).stdout
        tree = "\n".join(tree.splitlines()[:200])
    except OSError:
        tree = ""
    try:
        log = subprocess.run(  # nosec B603 B607 - fixed git argv, no shell
            ["git", "log", "-5", "--oneline"],
            cwd=workdir,
            capture_output=True,
            text=True,
            check=False,
        ).stdout
    except OSError:
        log = ""
    parts = [
        f"# Scope: {label}",
        "## README (head)",
        readme,
        "## File tree",
        tree,
        "## Recent commits",
        log,
    ]
    if diff.strip():
        parts += ["## Changes under review", diff[:6000]]
    return "\n\n".join(parts)


def chat(messages: list[dict], *, temperature: float = 0.2, timeout: int = 120) -> str:
    """Low-level completion. Raises on transport/parse failure — callers decide
    how to degrade (summarize swallows it; the compliance gate reports FAIL)."""
    body = json.dumps(
        {
            "model": MODEL,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": MAX_TOKENS,
        }
    ).encode()
    req = urllib.request.Request(
        f"{LLM_URL.rstrip('/')}/chat/completions",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {API_KEY}",
        },
    )
    data = _request_with_retry(req, timeout)
    msg = data["choices"][0]["message"]
    # Reasoning models (e.g. gpt-oss) may return content=null and put text under a
    # reasoning field, or emit nothing usable if they exhaust tokens while thinking.
    content = msg.get("content") or msg.get("reasoning_content") or msg.get("reasoning")
    if not content:
        raise ValueError(
            f"empty completion (finish_reason={data['choices'][0].get('finish_reason')})"
        )
    return content.strip()


_SECTIONS = ("summary", "changeset", "remediation", "improvement")


def _split_sections(text: str) -> dict:
    """Split the model reply on @@MARKER@@ lines into the sections. If the model
    ignored the format, the whole reply becomes the summary."""
    out = {k: "" for k in _SECTIONS}
    key: str | None = None
    buf: list[str] = []
    for line in text.splitlines():
        # Tolerate the model wrapping the marker in markdown (**, ##, etc.).
        m = re.match(
            r"[\s#*_>-]*@@(SUMMARY|CHANGESET|REMEDIATION|IMPROVEMENT)@@[\s*_]*$",
            line,
            re.IGNORECASE,
        )
        if m:
            if key:
                out[key] = "\n".join(buf).strip()
            key, buf = m.group(1).lower(), []
        elif key:
            buf.append(line)
    if key:
        out[key] = "\n".join(buf).strip()
    if not any(out.values()):
        out["summary"] = text.strip()
    return out


def analyze(workdir: str, label: str, diff: str, verdict: str, scorecard: str) -> dict:
    """One LLM call → {summary, changeset, remediation, improvement} as markdown.
    Changeset/remediation/improvement are grounded in the gate results (scorecard)."""
    prompt = (
        "You are reviewing a codebase and its automated quality-gate results. "
        "Respond with EXACTLY these four sections, each introduced by its marker "
        "line alone (no other use of @@). Use markdown inside each section.\n"
        "@@SUMMARY@@\n"
        "A concise 2-3 sentence generic summary of the WHOLE project: what it is, "
        "its structure, notable strengths, obvious concerns.\n"
        "@@CHANGESET@@\n"
        "In 2-3 short sentences of PLAIN prose, describe the EFFECT of this staged "
        "change / commit for a non-technical reader — what now works or behaves "
        "differently, not how the code does it. Do NOT name any files, variables, "
        "URLs, settings, functions, or ports; no code, diffs, backticks or bullet "
        "lists. Example of the right style: 'This change fixes the connection between "
        "two internal services so they can reach each other again.' If there is no "
        "diff in scope, write 'No changeset in scope.'\n"
        "@@REMEDIATION@@\n"
        "Concrete, actionable fixes for the gates that are FAIL or WARN to raise the "
        "score to green. For EACH such gate output a block that starts with a marker "
        "line of its own: '@@GATE <gate_id>@@' (use the exact gate id, e.g. gitleaks, "
        "mypy, kics), then markdown bullet fixes for that gate. Be SPECIFIC: cite the "
        "exact file:line, package name + version, CVE/rule id, or symbol from the "
        "findings below — never vague advice like 'address the vulnerabilities'. One "
        "bullet per distinct issue. If several gates flag the SAME underlying issue "
        "(e.g. checkov + trivy + kics all flag one Dockerfile line), put the fix in "
        "ONE gate block and name the other gate ids in that bullet — do NOT emit "
        "separate blocks that just say 'already covered' or 'duplicate'. If every "
        "gate passes, write 'No remediation needed.' with no gate blocks.\n"
        "@@IMPROVEMENT@@\n"
        "Ways to raise the bar BEYOND merely passing — stricter configs, missing "
        "tests/coverage, docs, architecture — things not already flagged above.\n\n"
        f"## Verdict\n{verdict}\n\n## Gate results\n{scorecard}\n\n"
        + _context(workdir, label, diff)
    )
    try:
        adv = _split_sections(chat([{"role": "user", "content": prompt}]))
    except Exception as exc:  # noqa: BLE001 — LLM issues must never crash the run; degrade instead
        adv = {
            "summary": f"LLM unavailable ({LLM_URL}, model {MODEL}): {exc}",
            "changeset": "",
            "remediation": "",
            "improvement": "",
        }
    adv["remediation_pre"], adv["remediation_groups"] = _split_gates(adv["remediation"])
    return adv


def _split_gates(md: str) -> tuple[str, list[tuple[str, str]]]:
    """Split remediation markdown on '@@GATE <name>@@' markers into per-gate
    (name, body) blocks, plus any preamble before the first marker."""
    preamble: list[str] = []
    groups: list[tuple[str, str]] = []
    name: str | None = None
    buf: list[str] = []
    for line in md.splitlines():
        m = re.match(r"\s*@@GATE\s+([\w\-./]+)\s*@@\s*$", line, re.IGNORECASE)
        if m:
            if name is not None:
                groups.append((name, "\n".join(buf).strip()))
            name, buf = m.group(1), []
        elif name is None:
            preamble.append(line)
        else:
            buf.append(line)
    if name is not None:
        groups.append((name, "\n".join(buf).strip()))
    # Drop empty / "already covered elsewhere" stub blocks (several gates flag the
    # same issue, so the model sometimes emits a placeholder rather than repeating).
    groups = [(n, b) for n, b in groups if _has_fix(b)]
    return "\n".join(preamble).strip(), groups


_STUB = re.compile(
    r"(?i)\b(already covered|already addressed|duplicate|covered above|"
    r"addressed above|see above|omitted)\b"
)


def _has_fix(body: str) -> bool:
    """Whether a generated suggestion actually says anything.

    A short body matching the stub patterns is the model declining politely.
    Posting that on a pull request is worse than posting nothing, so it is
    filtered here rather than left to the reader.
    """
    b = body.strip()
    return bool(b) and not (len(b) < 160 and _STUB.search(b))
