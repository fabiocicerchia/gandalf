"""Tiny stderr debug log — stdlib only.

Off by default; `--debug` or `GANDALF_DEBUG=1` turns it on. Messages carry a
monotonic elapsed stamp and go to stderr (so stdout / the JSON stay clean).
When on, the runner logs each gate's timing and run_tool logs every external
command; the progress bar steps aside so lines don't collide.
"""

from __future__ import annotations

import os
import sys
import time

_enabled = os.environ.get("GANDALF_DEBUG") == "1"
_start = time.monotonic()


def enable() -> None:
    """Turn debug logging on for the rest of the process (what --debug calls)."""
    global _enabled
    _enabled = True


def enabled() -> bool:
    """Whether debug logging is on. Read by the progress bar, which steps aside
    rather than collide with multi-line stderr output."""
    return _enabled


def log(msg: str) -> None:
    """Write one dimmed, elapsed-stamped line to stderr, if debugging is on.

    stderr, never stdout: the scorecard and the JSON report have to stay clean
    enough to pipe.
    """
    if _enabled:
        sys.stderr.write(
            f"\033[2m[gandalf +{time.monotonic() - _start:6.2f}s] {msg}\033[0m\n"
        )
        sys.stderr.flush()
