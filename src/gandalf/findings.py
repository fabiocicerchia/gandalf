"""One owner for reading a heterogeneous gate finding.

Gates hand their tool's findings through untouched, so the same field goes by a
different name in every one of them: ruff says ``filename`` and
``location.row``, semgrep ``path`` and ``start.line``, trivy ``Target`` and
``VulnerabilityID``, bandit ``filename`` and ``test_id``, and several gates hand
back a bare line of text with the location inside it. Every surface that
renders, anchors, suppresses or scores a finding has to answer the same six
questions about it — which file, which line, which column, which rule, what does
it say, how bad is it — and each of them used to answer with its own key list.

There were three copies of most of those lists (``report.py``, ``suppress.py``,
``sarif.py``, ``severity.py``) and a fourth in the VS Code extension's
``parse.ts``. They had drifted, and not harmlessly: ``test_id`` was missing from
the extension's rule list, so ``code`` won and every bandit finding there was
identified by the offending *source snippet* rather than by ``B105`` — the exact
failure the comment in ``suppress.finding_rule`` was written to prevent.

So: one module answers those questions, and every surface asks it. A key list
that lives in one place can still be wrong, but it can no longer be wrong in one
surface and right in another.

``fingerprint_keys()`` is the deliberate exception — see the comment on it.
"""

from __future__ import annotations

import os
import re

# Preference order, first truthy wins. Supersets of what the individual call
# sites used to carry, so a finding any surface could place is now placeable by
# all of them.
PATH_KEYS: tuple[str, ...] = (
    "path",
    "filename",
    "file",
    "file_path",
    "filepath",
    "File",
    "FilePath",
    "Path",
    "Target",  # trivy names the scanned artifact, not a source file
)

LINE_KEYS: tuple[str, ...] = (
    "line",
    "line_number",
    "line_no",
    "Line",
    "startLine",
    "start_line",
    "StartLine",
)

COLUMN_KEYS: tuple[str, ...] = ("column", "col", "startColumn", "start_column")

# `test_id` MUST stay ahead of `code`: bandit's `code` is the offending source
# snippet, not an identifier, so `code` winning gives every bandit finding a
# multi-line rule id. This ordering is the whole reason the list is shared.
RULE_KEYS: tuple[str, ...] = (
    "rule_id",
    "check_id",
    "RuleID",
    "test_id",
    "code",
    "check_name",
    "check",
    "QueryName",
    "VulnerabilityID",
    "id",
    "rule",
)

MESSAGE_KEYS: tuple[str, ...] = (
    "message",
    "issue_text",
    "description",
    "Description",
    "check_name",
    "error",
    "issue",
    "finding",
    "typo",
    "missing",
    "judge_summary",
    "reason",
    "rule_id",
    "VulnerabilityID",
    "QueryName",
)

# Rule documentation, where the tool ships one. Not used by any gandalf output
# today; it is here because every editor integration wants it and would
# otherwise grow a seventh key list of its own.
URL_KEYS: tuple[str, ...] = ("url", "URL", "PrimaryURL", "help_uri")

SEVERITY_KEYS: tuple[str, ...] = (
    "severity",
    "Severity",
    "issue_severity",
    "level",
    "Level",
)

# Objects a tool may nest a position inside, and the keys to try within them.
_POSITION_PARENTS: tuple[str, ...] = (
    "location",
    "start",
    "Location",
    "Start",
    "position",
)
_NESTED_LINE_KEYS: tuple[str, ...] = ("row", *LINE_KEYS)
_NESTED_COLUMN_KEYS: tuple[str, ...] = ("col", *COLUMN_KEYS)

# Raw tool words → the normalized ladder. The union of what severity.py and
# sarif.py each knew; `unknown` is a word tools actually publish, and means
# "the tool declined to rate this", which is not the same as carrying no
# severity field at all (that returns "").
_NORMAL: dict[str, str] = {
    "critical": "critical",
    "crit": "critical",
    "high": "high",
    "error": "high",
    "medium": "medium",
    "moderate": "medium",
    "warning": "medium",
    "warn": "medium",
    "low": "low",
    "minor": "low",
    "note": "low",
    "info": "info",
    "informational": "info",
    "unknown": "unknown",
}

LEVELS: tuple[str, ...] = ("critical", "high", "medium", "low", "info", "unknown")

# `src/a.py:12:` or `src/a.py:12:5:` inside a message — the gates that hand back
# a raw tool line (mypy, tsc, codeql) carry their location nowhere else.
_TEXT_LOCATION = re.compile(
    r"(?:^|[\s(\[\"'])([\w.@+-]+(?:[/\\][\w.@+-]+)*\.\w{1,12}):(\d+)(?::(\d+))?"
)
# A bare path with no line — the format gate's "Would reformat: src/x.py". Needs
# a separator to match, so an ordinary word with a dot in it is not a candidate.
_TEXT_PATH = re.compile(r"[\w.@+-]+(?:[/\\][\w.@+-]+)+\.\w{1,12}")


# A leading `[HIGH]` — how the kics and licenses gates report severity, folding
# it into the message rather than into a key. Only a bracket whose content is a
# known severity word counts, so bandit's `[B603]` and mypy's trailing
# `[attr-defined]` are left alone.
_MESSAGE_LEVEL = re.compile(r"^\[([A-Za-z]+)\]\s*")


def _is_mapping(f: object) -> bool:
    return isinstance(f, dict)


def first_str(f: object, keys: tuple[str, ...]) -> str:
    """First key holding a non-empty string (or a number), as a string."""
    if not _is_mapping(f):
        return ""
    for k in keys:
        v = f.get(k)  # type: ignore[union-attr]
        if isinstance(v, str) and v.strip():
            return v.strip()
        if isinstance(v, bool):
            continue  # a bool is not a value any of these fields means
        if isinstance(v, (int, float)):
            return str(v)
    return ""


def first_int(f: object, keys: tuple[str, ...]) -> int:
    """First key holding a positive integer, or 0. Digit strings count."""
    if not _is_mapping(f):
        return 0
    for k in keys:
        v = f.get(k)  # type: ignore[union-attr]
        if isinstance(v, bool):
            continue
        if isinstance(v, int) and v > 0:
            return v
        if isinstance(v, str) and v.isdigit() and int(v) > 0:
            return int(v)
    return 0


def _nested(f: object, key: str) -> dict | None:
    if not _is_mapping(f):
        return None
    v = f.get(key)  # type: ignore[union-attr]
    return v if isinstance(v, dict) else None


def _nested_position(f: object) -> tuple[int, int]:
    for parent in _POSITION_PARENTS:
        obj = _nested(f, parent)
        if obj is None:
            continue
        ln = first_int(obj, _NESTED_LINE_KEYS)
        if ln:
            return ln, first_int(obj, _NESTED_COLUMN_KEYS)
    return 0, 0


def path(f: object) -> str:
    """The file the finding names, exactly as the tool spelled it."""
    return first_str(f, PATH_KEYS)


def line(f: object) -> int:
    """1-based line, flat keys first then a nested position object. 0 if none."""
    return first_int(f, LINE_KEYS) or _nested_position(f)[0]


def column(f: object) -> int:
    """1-based column, or 0."""
    return first_int(f, COLUMN_KEYS) or _nested_position(f)[1]


def rule(f: object) -> str:
    """The rule / check / code id, however the tool spells it."""
    return first_str(f, RULE_KEYS)


def message(f: object) -> str:
    """What the tool said. Empty when the finding carries no prose at all —
    callers decide what to show instead, since a table row and a SARIF result
    want different fallbacks."""
    return first_str(f, MESSAGE_KEYS)


def severity_raw(f: object) -> str:
    """The severity word as the tool published it, or ''. Uppercased, because
    every consumer compares it case-insensitively anyway."""
    raw = first_str(f, SEVERITY_KEYS)
    if not raw:
        extra = _nested(f, "extra")  # semgrep nests it here
        if extra is not None:
            raw = first_str(extra, ("severity", *SEVERITY_KEYS))
    return raw.upper()


def severity(f: object) -> str:
    """Normalized severity — one of LEVELS — or '' when the finding carries
    none. '' and 'unknown' are different answers: the first means the tool said
    nothing, the second means it said so explicitly."""
    raw = severity_raw(f)
    return _NORMAL.get(raw.strip().lower(), "") if raw else ""


def message_level(text: str) -> tuple[str, str]:
    """Split a leading `[HIGH]` off a message → `(severity, rest)`.

    `('', text)` when the prefix is absent or is not a severity word.
    """
    hit = _MESSAGE_LEVEL.match(text or "")
    if not hit:
        return "", text
    word = _NORMAL.get(hit[1].lower(), "")
    return (word, text[hit.end() :]) if word else ("", text)


def url(f: object) -> str:
    """Rule documentation, when the tool ships one."""
    return first_str(f, URL_KEYS)


def text_location(text: str) -> tuple[str, int, int]:
    """`(path, line, column)` scraped from a message, for the gates that carry
    their location only in prose. `('', 0, 0)` when there is nothing to scrape.
    A bogus parse costs the caller nothing — it checks the path exists."""
    hit = _TEXT_LOCATION.search(text or "")
    if not hit:
        return "", 0, 0
    return hit[1], int(hit[2]), int(hit[3]) if hit[3] else 0


def _on_disk(candidate: str, root: str) -> bool:
    """Whether a scraped path names a file that is actually there.

    Prose looks like a path more often than you would think ("see docs/api.md"),
    and a finding anchored to a file that does not exist is worse than one left
    unanchored. Without a root there is nothing to check against, so the scrape
    is taken at face value — which is what unit tests want and what a caller
    outside a checkout gets.
    """
    if not root:
        return True
    return os.path.isfile(os.path.join(root, relpath(candidate, root)))


def relpath(p: str, root: str = "") -> str:
    """A tool-reported path made repo-relative.

    Tools run either on the host (paths already relative to the worktree) or
    inside the tools image, which mounts the repo at a fixed prefix — so an
    absolute path has to have that prefix taken off before it means anything to
    anyone else.
    """
    out = (p or "").strip().replace("\\", "/")
    if root:
        r = root.replace("\\", "/").rstrip("/")
        if r and out.startswith(r):
            out = out[len(r) :]
    return out.lstrip("/").removeprefix("./")


def _place_from_prose(
    p: str, ln: int, col: int, text: str, root: str
) -> tuple[str, int, int, str]:
    """Recover `path:line:col` from a message that carries it in prose, and take
    the recovered prefix back off the message.

    Gates that hand back a raw tool line (mypy, tsc, codeql) have no location
    fields at all. Returns the inputs unchanged when there is nothing to scrape.
    """
    tp, tl, tc = text_location(text)
    if not tp or not _on_disk(tp, root):
        return p, ln, col, text
    scraped_path = not p
    if scraped_path:
        p = tp
    if not ln and tp == p:
        ln, col = tl, (col or tc)
    if not scraped_path:
        return p, ln, col, text
    # The location has its own fields now, so a message that merely repeats it
    # in front is shorter without it.
    head = text[: text.index(tp)] + tp
    if ln:
        head = f"{head}:{ln}" if f"{tp}:{ln}" in text else head
    if text.startswith(head):
        text = text[len(head) :].lstrip(" \t:-")
    return p, ln, col, text


def _path_in_prose(text: str, root: str) -> str:
    """The first bare path in a message that names a file actually on disk, or
    '' — the last resort for a finding with no location fields at all."""
    for candidate in _TEXT_PATH.findall(text):
        if _on_disk(candidate, root):
            return candidate
    return ""


def normalise(f: object, root: str = "") -> dict:
    """Everything above, as one dict.

    This is what goes on the wire under ``_gandalf`` so a consumer — the VS Code
    extension, the Neovim plugin, anything else reading the JSON report — never
    has to know that ruff says ``location.row`` and trivy says ``Target``.
    ``path`` is repo-relative; ``line``/``column`` are 1-based, 0 meaning
    unknown; ``severity`` is '' when the tool published none.
    """
    p, ln, col = path(f), line(f), column(f)
    text = message(f)
    sev = severity(f)

    # kics and the licenses gate put the severity in front of the message.
    if not sev:
        sev, text = message_level(text)

    # Some gates carry the whole finding in a location key — the format gate's
    # `{"file": "Would reformat: src/x.py"}`. That sentence is the message; the
    # path inside it is found by the scrape below.
    if not text and p:
        text, p = p, ""

    if not p or not ln:
        p, ln, col, text = _place_from_prose(p, ln, col, text, root)
    # Still unplaced: a bare path somewhere in the text. The message is left
    # whole — for these gates the sentence is the finding.
    if not p:
        p = _path_in_prose(text, root)

    return {
        "path": relpath(p, root),
        "line": ln,
        "column": col,
        "rule": rule(f),
        "message": text,
        "severity": sev,
        "url": url(f),
    }


# --- frozen vocabulary -------------------------------------------------------

# Suppression fingerprints are hashes of these fields, and a baseline file is a
# list of those hashes sitting in someone's repository. Widening the key lists
# above would change what a finding hashes to and silently un-accept every
# finding in every committed .gandalf-baseline.json — the tool would go loud
# again on exactly the findings a team had agreed to live with.
#
# So fingerprints keep the vocabulary they were computed with. This is the one
# place where "the lists disagree" is a decision rather than an accident, and it
# is why it lives here next to the lists it deliberately differs from.
#
# Do not edit these without a baseline format version and a migration.
_FP_PATH_KEYS: tuple[str, ...] = ("path", "filename", "file", "file_path")
_FP_RULE_KEYS: tuple[str, ...] = (
    "rule_id",
    "check_id",
    "RuleID",
    "test_id",
    "code",
    "check_name",
    "QueryName",
    "VulnerabilityID",
    "id",
    "rule",
)
_FP_MESSAGE_KEYS: tuple[str, ...] = (
    "message",
    "issue_text",
    "description",
    "Description",
    "finding",
    "typo",
    "missing",
)


def _first_truthy(f: object, keys: tuple[str, ...]) -> str:
    """The or-chain the suppression helpers used, preserved exactly.

    Deliberately not `first_str`: that one strips whitespace and skips bools,
    and either difference would move a hash. A fingerprint helper may only
    change when the baseline format does.
    """
    if not _is_mapping(f):
        return ""
    for k in keys:
        v = f.get(k)  # type: ignore[union-attr]
        if v:
            return str(v)
    return ""


def fingerprint_keys(f: object) -> tuple[str, str, str]:
    """`(path, rule, message)` as suppression hashes them. Frozen — see above.

    A non-dict finding has no fields to read, and its whole string form is the
    only thing there is to identify it by — which is what `_message` did.
    """
    if not _is_mapping(f):
        return "", "", str(f)
    return (
        _first_truthy(f, _FP_PATH_KEYS),
        _first_truthy(f, _FP_RULE_KEYS),
        _first_truthy(f, _FP_MESSAGE_KEYS),
    )


def annotate(f: object, root: str = "") -> object:
    """A finding with `normalise()`'s answers attached under `_gandalf`.

    The tool's own keys are left exactly as they were — a consumer that already
    knows a given tool keeps reading it directly — and everything else can read
    one shape. A non-dict finding has nowhere to put the block, so it passes
    through untouched.
    """
    if not _is_mapping(f):
        return f
    return {**f, "_gandalf": normalise(f, root)}  # type: ignore[dict-item]


def annotate_all(items: list, root: str = "") -> list:
    return [annotate(f, root) for f in items or []]
