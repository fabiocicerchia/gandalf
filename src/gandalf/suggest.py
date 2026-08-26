"""Turn a tool's own machine-applicable fix into a GitHub suggestion block.

Several scanners already know the exact replacement text for what they flag —
ruff ships `fix.edits`, shellcheck `fix.replacements`, semgrep `extra.fix`,
codespell spells the correction out in its message — and gandalf was throwing
all of it away: the PR comment said what was wrong and left the reader to type
the fix themselves.

This module reconciles those shapes into one `Edit` vocabulary (1-based lines,
1-based columns, end-exclusive — the convention every one of them already
uses), applies the edits to the file on disk, and hands back the *whole* new
text of the lines they touch. That is what a ```suggestion block has to carry:
GitHub replaces the commented line range with the block verbatim, so a partial
replacement would silently truncate someone's code when they click Apply.

Nothing here guesses. A finding with no fix attached, an edit that doesn't line
up with the file as it stands, or a replacement that changes nothing produces no
suggestion at all — a wrong one-click patch is far worse than none.
"""

from __future__ import annotations

import itertools
import re
from dataclasses import dataclass
from pathlib import Path

from . import findings as gfindings

# A suggestion that spans half a screen stops being a one-click fix and starts
# burying the comment it hangs off. Anything longer is left to the prose.
MAX_LINES = 40


@dataclass(frozen=True)
class Edit:
    """One replacement, in the coordinate system every tool here reports in:
    1-based line and column, `end` exclusive (it points at the first character
    the edit does *not* replace)."""

    start_line: int
    start_col: int
    end_line: int
    end_col: int
    text: str


def _int(v) -> int:
    """A coordinate as an int, or 0 — tools disagree on int vs digit-string."""
    if isinstance(v, bool):
        return 0
    if isinstance(v, int):
        return v
    if isinstance(v, str) and v.strip().isdigit():
        return int(v)
    return 0


def _dict(obj, key) -> dict:
    v = obj.get(key) if isinstance(obj, dict) else None
    return v if isinstance(v, dict) else {}


def _ruff(f: dict, _lines: list[str]) -> list[Edit]:
    """ruff: `fix.edits[] = {content, location{row,column}, end_location{…}}`."""
    out = []
    for e in _dict(f, "fix").get("edits") or []:
        if not isinstance(e, dict):
            continue
        start, end = _dict(e, "location"), _dict(e, "end_location")
        out.append(
            Edit(
                _int(start.get("row")),
                _int(start.get("column")),
                _int(end.get("row")) or _int(start.get("row")),
                _int(end.get("column")) or _int(start.get("column")),
                e.get("content") or "",
            )
        )
    return out


def _shellcheck(f: dict, _lines: list[str]) -> list[Edit]:
    """shellcheck: `fix.replacements[] = {line,endLine,column,endColumn,replacement}`."""
    out = []
    for r in _dict(f, "fix").get("replacements") or []:
        if not isinstance(r, dict):
            continue
        out.append(
            Edit(
                _int(r.get("line")),
                _int(r.get("column")),
                _int(r.get("endLine")) or _int(r.get("line")),
                _int(r.get("endColumn")) or _int(r.get("column")),
                r.get("replacement") or "",
            )
        )
    return out


def _semgrep(f: dict, _lines: list[str]) -> list[Edit]:
    """semgrep: autofix text under `extra.fix`, range in `start`/`end`."""
    text = _dict(f, "extra").get("fix")
    start, end = _dict(f, "start"), _dict(f, "end")
    if not isinstance(text, str) or not (start and end):
        return []
    return [
        Edit(
            _int(start.get("line")),
            _int(start.get("col")) or _int(start.get("column")),
            _int(end.get("line")),
            _int(end.get("col")) or _int(end.get("column")),
            text,
        )
    ]


def _normalised(f: dict, _lines: list[str]) -> list[Edit]:
    """`_fix.edits[]` — the shape a gate emits when its tool reports a fix in a
    format only that gate can read (eslint's character offsets, say). Written by
    the gate, in this module's own vocabulary, so nothing downstream has to
    learn a fifth dialect."""
    out = []
    for e in _dict(f, "_fix").get("edits") or []:
        if not isinstance(e, dict):
            continue
        out.append(
            Edit(
                _int(e.get("start_line")),
                _int(e.get("start_column")),
                _int(e.get("end_line")) or _int(e.get("start_line")),
                _int(e.get("end_column")) or _int(e.get("start_column")),
                e.get("text") or "",
            )
        )
    return out


# codespell prints `path:12: <found> ==> <correction>`, and the gate keeps that
# line whole. A correction listing alternatives (`... ==> one, other`) is the
# tool saying it doesn't know which is meant either, so it is not suggestable.
_TYPO = re.compile(r"(?:^|[\s:])(\S+)\s+==>\s+(.+?)\s*$")


def _codespell(f: dict, lines: list[str]) -> list[Edit]:
    """codespell: the correction is in the message, the position is not — so the
    replacement is rebuilt from the source line itself."""
    text = gfindings.message(f) or ""
    if "==>" not in text:  # cheap reject: the regex is the expensive part
        return []
    hit = _TYPO.search(text)
    if not hit:
        return []
    typo, fixed = hit[1], hit[2]
    if "," in fixed:  # several candidates → the tool is not sure either
        return []
    # The whole finding is that one printed line, so the position is in the
    # prose too — same scrape the comment's anchor was placed by.
    ln = gfindings.line(f) or gfindings.text_location(text)[1]
    if not 1 <= ln <= len(lines):
        return []
    src = lines[ln - 1]
    # Word-boundary so a misspelling inside a longer word is left alone, and one
    # occurrence only: codespell reports each hit separately.
    swapped, n = re.subn(
        rf"\b{re.escape(typo)}\b", fixed.replace("\\", "\\\\"), src, count=1
    )
    if n != 1 or swapped == src:
        return []
    return [Edit(ln, 1, ln, len(src) + 1, swapped)]


_EXTRACTORS = (_ruff, _shellcheck, _semgrep, _normalised, _codespell)


def edits(f: object, lines: list[str]) -> list[Edit]:
    """Every edit a finding carries, in whichever dialect it carries them.

    First extractor with something to say wins — a finding only ever comes from
    one tool, so there is nothing to merge across them. All of that tool's edits
    or none of them: half of a fix that removes an import and rewrites its call
    site is not a smaller fix, it is a broken file.
    """
    if not isinstance(f, dict):
        return []
    for extract in _EXTRACTORS:
        found = [_clamp(e, lines) for e in extract(f, lines)]
        if found:
            return found if all(_sane(e, lines) for e in found) else []
    return []


def _sane(e: Edit, lines: list[str]) -> bool:
    """Whether an edit actually lands on the file as it is on disk now."""
    if min(e.start_line, e.start_col, e.end_line, e.end_col) < 1:
        return False
    if (e.end_line, e.end_col) < (e.start_line, e.start_col):
        return False
    if not (1 <= e.start_line <= len(lines) and 1 <= e.end_line <= len(lines)):
        return False
    return (
        e.start_col <= len(lines[e.start_line - 1]) + 1
        and e.end_col <= len(lines[e.end_line - 1]) + 1
    )


def _clamp(e: Edit, lines: list[str]) -> Edit:
    """A deletion that runs to the start of the line after the last one (how
    ruff removes a whole line at EOF) points one line past the file. Pull it
    back onto the final line so it stays applicable."""
    if e.end_line == len(lines) + 1 and e.end_col <= 1 and lines:
        return Edit(e.start_line, e.start_col, len(lines), len(lines[-1]) + 1, e.text)
    return e


def _overlapping(sorted_edits: list[Edit]) -> bool:
    return any(
        (nxt.start_line, nxt.start_col) < (prev.end_line, prev.end_col)
        for prev, nxt in itertools.pairwise(sorted_edits)
    )


def apply(lines: list[str], to_apply: list[Edit]) -> tuple[int, int, str] | None:
    """→ `(first_line, last_line, replacement)` for the lines the edits touch.

    The replacement is the complete new text of `first_line..last_line`, which
    is what a suggestion block means. Applied back-to-front so an edit that adds
    or removes lines doesn't shift the ones still to be applied.
    """
    ordered = sorted(to_apply, key=lambda e: (e.start_line, e.start_col))
    if not ordered or _overlapping(ordered):
        return None  # conflicting fixes: applying both would corrupt the line
    first, last = ordered[0].start_line, max(e.end_line for e in ordered)
    if last - first + 1 > MAX_LINES:
        return None
    buf = list(lines)
    delta = 0
    for e in reversed(ordered):
        head = buf[e.start_line - 1][: e.start_col - 1]
        tail = buf[e.end_line - 1][e.end_col - 1 :]
        merged = (head + e.text + tail).split("\n")
        delta += len(merged) - (e.end_line - e.start_line + 1)
        buf[e.start_line - 1 : e.end_line] = merged
    new = buf[first - 1 : last + delta]
    if new == lines[first - 1 : last]:
        return None  # the "fix" changes nothing — nothing to suggest
    return first, last, "\n".join(new)


def read_lines(workdir: str, path: str) -> list[str]:
    """The file's lines without their endings, or [] if it can't be read.

    `\\r` is dropped: a suggestion is inserted into the comment as text, and a
    stray carriage return would be applied as part of the line.
    """
    try:
        text = (Path(workdir) / path).read_text(errors="replace")
    except (OSError, ValueError):
        return []
    return [ln.rstrip("\r") for ln in text.splitlines()]


def for_anchor(
    workdir: str,
    path: str,
    line: int,
    items: list,
    anchorable: set[int] | None = None,
) -> tuple[int, str] | None:
    """→ `(last_line, replacement)` for one review comment, or None.

    `items` are the findings merged into that comment; their fixes are applied
    together, so two ruff hits on the same line come back as one suggestion
    rather than two that invalidate each other.

    The block must start exactly on the commented line — GitHub applies it to
    the range the comment covers, so a suggestion computed for the line below
    would overwrite the wrong code. `anchorable`, when known, is the set of
    lines the PR diff adds: a multi-line suggestion has to stay inside it or
    GitHub rejects the comment outright.
    """
    lines = read_lines(workdir, path)
    if not lines:
        return None
    pending: list[Edit] = []
    for f in items:
        pending += [e for e in edits(f, lines) if e.start_line >= line]
    if not pending or min(e.start_line for e in pending) != line:
        return None
    applied = apply(lines, pending)
    if applied is None:
        return None
    first, last, text = applied
    if first != line or "```" in text:
        return None
    if anchorable and not set(range(first, last + 1)) <= anchorable:
        return None
    return last, text


def block(text: str) -> str:
    """The finding's fix as GitHub renders it: a fenced `suggestion` block with
    an Apply button on it."""
    return f"```suggestion\n{text}\n```"


def _line_col(source: str, index: int) -> tuple[int, int]:
    """1-based line and column of a character index."""
    return source.count("\n", 0, index) + 1, index - source.rfind("\n", 0, index)


def _from_utf16(source: str, offset: int, astral: bool) -> int | None:
    """A UTF-16 code-unit offset as a Python string index, or None if it lands
    inside a surrogate pair or past the end."""
    if not astral:
        return offset if 0 <= offset <= len(source) else None
    units = 0
    for i, ch in enumerate(source):
        if units == offset:
            return i
        units += 2 if ord(ch) > 0xFFFF else 1
    return len(source) if units == offset else None


def utf16_edit(source: str, start: int, end: int, text: str) -> dict | None:
    """A `_fix` edit built from a pair of UTF-16 code-unit offsets — how eslint,
    and anything else built on a JavaScript AST, reports the range it would
    replace.

    Python indexes a string by code point and JavaScript by UTF-16 code unit;
    the two part company on anything outside the BMP, so a single emoji earlier
    in the file shifts every later offset by one. The common case (no astral
    characters at all) is checked for once and indexed directly.
    """
    if isinstance(start, bool) or isinstance(end, bool):
        return None
    if not isinstance(start, int) or not isinstance(end, int) or not 0 <= start <= end:
        return None
    astral = not source.isascii() and max(source, default="") > "\uffff"
    begin, finish = (
        _from_utf16(source, start, astral),
        _from_utf16(source, end, astral),
    )
    if begin is None or finish is None:
        return None
    start_line, start_column = _line_col(source, begin)
    end_line, end_column = _line_col(source, finish)
    return {
        "start_line": start_line,
        "start_column": start_column,
        "end_line": end_line,
        "end_column": end_column,
        "text": text if isinstance(text, str) else "",
    }
