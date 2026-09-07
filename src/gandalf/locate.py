"""Finding a `path:line:col` that a tool only ever wrote into its prose.

Several gates hand back a raw tool line (mypy, tsc, codeql) or a whole sentence
(the format gate's "Would reformat: src/x.py") with no location fields at all.
Scraping one out of the text is guesswork, so every candidate is checked against
the disk before it is believed — a finding anchored to a file that does not
exist is worse than one left unanchored.
"""

from __future__ import annotations

import re
from pathlib import Path

# `src/a.py:12:` or `src/a.py:12:5:` inside a message — the gates that hand back
# a raw tool line (mypy, tsc, codeql) carry their location nowhere else.
_TEXT_LOCATION = re.compile(r"(?:^|[\s(\[\"'])([\w.@+-]+(?:[/\\][\w.@+-]+)*\.\w{1,12}):(\d+)(?::(\d+))?")
# A bare path with no line — the format gate's "Would reformat: src/x.py". Needs
# a separator to match, so an ordinary word with a dot in it is not a candidate.
_TEXT_PATH = re.compile(r"[\w.@+-]+(?:[/\\][\w.@+-]+)+\.\w{1,12}")


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
    return (Path(root) / relpath(candidate, root)).is_file()


def place_from_prose(p: str, ln: int, col: int, text: str, root: str) -> tuple[str, int, int, str]:
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


def path_in_prose(text: str, root: str) -> str:
    """The first bare path in a message that names a file actually on disk, or
    '' — the last resort for a finding with no location fields at all."""
    for candidate in _TEXT_PATH.findall(text):
        if _on_disk(candidate, root):
            return candidate
    return ""
