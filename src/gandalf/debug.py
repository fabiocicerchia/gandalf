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
    global _enabled
    _enabled = True


def enabled() -> bool:
    return _enabled


def log(msg: str) -> None:
    if _enabled:
        sys.stderr.write(
            f"\033[2m[gandalf +{time.monotonic() - _start:6.2f}s] {msg}\033[0m\n"
        )
        sys.stderr.flush()
