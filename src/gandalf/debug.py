"""Tiny stderr debug log — stdlib only.

Off by default; `--debug` or `GANDALF_DEBUG=1` turns it on. Messages carry a
monotonic elapsed stamp and go to stderr (so stdout / the JSON stay clean).
When on, the runner logs each gate's start, each gate's timing, and run_tool
logs every external command.

The progress bar shares stderr, and it owns a single line it rewrites in place.
Rather than one of the two standing down — which cost you the bar whenever you
most wanted to watch a run — the bar hands `around_log` a pair of callbacks: the
line is cleared before a debug line is written and redrawn after it. Both work at
once, and the log stays line-delimited for whoever is parsing it.
"""

from __future__ import annotations

import os
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass


@dataclass
class _State:
    """Process-wide debug switch, and whoever else is writing to stderr. An
    object rather than module-level names so turning it on mutates state instead
    of rebinding through `global`."""

    enabled: bool
    before: Callable[[], None] | None = None
    after: Callable[[], None] | None = None


_state = _State(enabled=os.environ.get("GANDALF_DEBUG") == "1")
_start = time.monotonic()


def enable() -> None:
    """Turn debug logging on for the rest of the process (what --debug calls)."""
    _state.enabled = True


def enabled() -> bool:
    """Whether debug logging is on."""
    return _state.enabled


def around_log(before: Callable[[], None] | None, after: Callable[[], None] | None) -> None:
    """Register what to do either side of a debug line — the progress bar clears
    its line and redraws it. Pass (None, None) to deregister; a bar that has
    finished must not be redrawn over the scorecard that follows it."""
    _state.before, _state.after = before, after


def log(msg: str) -> None:
    """Write one dimmed, elapsed-stamped line to stderr, if debugging is on.

    stderr, never stdout: the scorecard and the JSON report have to stay clean
    enough to pipe.
    """
    if not _state.enabled:
        return
    if _state.before:
        _state.before()
    sys.stderr.write(f"\033[2m[gandalf +{time.monotonic() - _start:6.2f}s] {msg}\033[0m\n")
    if _state.after:
        _state.after()
    sys.stderr.flush()
