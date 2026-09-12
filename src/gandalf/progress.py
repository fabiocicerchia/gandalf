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
    """A single stderr line that updates in place through a run.

    Silent unless stderr is a TTY, so piped and CI output is not littered with
    carriage returns.

    Under --debug it shares stderr with the debug log rather than standing down:
    it registers a clear/redraw pair with `debug.around_log`, so each debug line
    lands on a clean line and the bar comes straight back underneath it. That
    keeps the two legible together on a terminal, and — because the bar's redraw
    re-issues the `\\r` that delimits it — keeps both parsable for a consumer
    reading the stream, which is how the editor extension shows progress for a
    run it also has debug logging turned on for.
    """

    def __init__(self, total: int) -> None:
        self.total = total
        self.i = 0
        self.label = ""
        self.extra = ""
        self.on = os.environ.get("GANDALF_PROGRESS") == "1" or sys.stderr.isatty()
        if self.on:
            debug.around_log(self._clear, self._draw)

    def _clear(self) -> None:
        """Blank the line so something else can write a whole one of its own."""
        if self.on:
            sys.stderr.write("\r\033[K")

    def _draw(self, extra: str | None = None) -> None:
        if not self.on:
            return
        if extra is not None:
            self.extra = extra
        # \r + clear-to-end keeps everything on one in-place line.
        sys.stderr.write(f"\r\033[K\033[36m[{self.i}/{self.total}]\033[0m {self.label}{self.extra}")
        sys.stderr.flush()

    def stage(self, label: str) -> None:
        """Advance to the next stage (redraws the single line).

        Also the one place a run announces its phases, so --debug stamps each
        one with the elapsed time it started at — that is what makes "which
        step is this run spending its minutes in" answerable from the log.
        """
        self.i += 1
        self.label = label
        self._draw("")
        debug.log(f"stage {self.i}/{self.total}: {label}")

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
        # Deregister first: past this point the line is finished, and a debug
        # line from the report-writing stage must not redraw a stale bar over
        # the scorecard.
        debug.around_log(None, None)
        if self.on:
            sys.stderr.write("\n")
            sys.stderr.flush()
