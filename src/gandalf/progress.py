"""Minimal single-line stderr progress for a gandalf run — stdlib only.

One line that updates in place through the run's stages (and the gate bar).
Writes to stderr so stdout (the scorecard) and the JSON stay clean, and stays
silent unless stderr is a TTY (or GANDALF_PROGRESS=1), so piped / CI output isn't
littered with carriage returns.
"""

from __future__ import annotations

import os
import sys

from . import debug


class Progress:
    def __init__(self, total: int):
        self.total = total
        self.i = 0
        self.label = ""
        # Debug logging writes multi-line to stderr; a single-line progress bar
        # would collide with it, so step aside when --debug is on.
        self.on = (
            os.environ.get("GANDALF_PROGRESS") == "1" or sys.stderr.isatty()
        ) and not debug.enabled()

    def _draw(self, extra: str = "") -> None:
        if self.on:
            # \r + clear-to-end keeps everything on one in-place line.
            sys.stderr.write(
                f"\r\033[K\033[36m[{self.i}/{self.total}]\033[0m {self.label}{extra}"
            )
            sys.stderr.flush()

    def stage(self, label: str) -> None:
        """Advance to the next stage (redraws the single line)."""
        self.i += 1
        self.label = label
        self._draw()

    def bar(self, done: int, total: int, label: str = "") -> None:
        """Redraw the line with an inline progress bar (e.g. gates completing)."""
        if not self.on:
            return
        width = 20
        fill = int(width * done / total) if total else width
        bar = "█" * fill + "░" * (width - fill)
        self._draw(f"  [{bar}] {done}/{total} {label[:22]}")

    def finish(self) -> None:
        """End the single progress line so following output starts fresh."""
        if self.on:
            sys.stderr.write("\n")
            sys.stderr.flush()
