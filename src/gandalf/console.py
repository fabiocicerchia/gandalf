"""Where gandalf writes to the terminal.

Every line the CLI prints goes through here. Two reasons: the rest of the code
then contains no bare `print`, so T201 stays a real signal rather than noise to
be switched off; and a test can capture output by patching one module instead of
stdout.
"""

from __future__ import annotations

import sys

# --json gives stdout to the payload, so every human line has to move aside. A
# module flag rather than contextlib.redirect_stdout: `data` still needs the real
# stdout, and a process-wide redirect would take that too.
_human_to_stderr = False


def divert_human_output(*, to_stderr: bool) -> None:
    """Send `out` to stderr, leaving `data` alone on stdout.

    Always set, even to False: this is process state, and a second run in the
    same process must not inherit the first one's choice.
    """
    global _human_to_stderr  # noqa: PLW0603 — one flag, one writer
    _human_to_stderr = to_stderr


def out(text: str = "", *, flush: bool = False) -> None:
    """Write a line to stdout — the CLI's result, not a log line."""
    # Streams resolved per call, not at import: pytest's capsys swaps them.
    stream = sys.stderr if _human_to_stderr else sys.stdout
    print(text, flush=flush, file=stream)


def data(text: str = "", *, flush: bool = False) -> None:
    """Write machine-readable output — always stdout, never diverted.

    What a `--json` or `--stream` consumer parses. Kept apart from `out` so a
    scorecard line can never land in the middle of a JSON document.
    """
    print(text, flush=flush)  # noqa: T201 — this function is the CLI's stdout


def err(text: str) -> None:
    """Write a line to stderr — a warning the run continues past."""
    print(text, file=sys.stderr)  # noqa: T201 — this function is the CLI's stderr
