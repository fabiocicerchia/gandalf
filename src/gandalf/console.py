"""Where gandalf writes to the terminal.

Every line the CLI prints goes through here. Two reasons: the rest of the code
then contains no bare `print`, so T201 stays a real signal rather than noise to
be switched off; and a test can capture output by patching one module instead of
stdout.
"""

from __future__ import annotations

import sys


def out(text: str = "", *, flush: bool = False) -> None:
    """Write a line to stdout — the CLI's result, not a log line."""
    print(text, flush=flush)  # noqa: T201 — this function is the CLI's stdout


def err(text: str) -> None:
    """Write a line to stderr — a warning the run continues past."""
    print(text, file=sys.stderr)  # noqa: T201 — this function is the CLI's stderr
