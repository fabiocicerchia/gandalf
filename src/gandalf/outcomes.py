"""GateResult sentinels for the cases where a gate has nothing to say.

"We could not check this" is not a quality signal, and every one of these
builders exists so a gate never has to spell that out — or accidentally report
it as a clean pass.
"""

from __future__ import annotations

from .base import GateOutcome, GateResult
from .toolrun import _TIMEOUT_RC, tool_missing


def unavailable(name: str, summary: str) -> GateResult:
    """A gate that produced no signal about the code: its tool is not installed,
    it timed out, its judge was unreachable, or it had nothing in scope to look at.

    Still amber and still 0.8, so every existing consumer sees what it saw before.
    What is new is the `_unavailable` marker, set out-of-band the same way the
    runner sets `_blocking` and `_duration` — the `Gate` protocol is unchanged and
    `GateOutcome` gains no member, so gate files still move between this project
    and ai-harness untouched.

    It matters because "we could not check this" is not a quality signal, and
    scoring it as one is wrong in both directions: 0.8 drags a clean repo down and
    props a bad one up, and a host with no scanners installed lands on a red
    scorecard that says nothing about the code. `report.aggregate` leaves marked
    results out of the composite and the verdict; the report counts them instead.
    """
    r = GateResult(name, GateOutcome.WARN, 0.8, summary)
    r._unavailable = True  # type: ignore[attr-defined]
    return r


def carry_over(src: GateResult, dst: GateResult) -> GateResult:
    """Copy the out-of-band attributes from one result onto a rebuilt one.

    suppress and severity both rebuild a GateResult to change its score, and both
    used to name the attributes worth keeping. That list went stale every time one
    was added: `_duration` was never in it, so every reweighted run wrote a null
    duration into the JSON, and `_unavailable` had to be added to two call sites
    the day it was introduced. Copy whatever is actually there instead — the
    underscore prefix is exactly what distinguishes runner metadata from the
    dataclass's own fields.
    """
    for key, value in vars(src).items():
        if key.startswith("_"):
            setattr(dst, key, value)
    return dst


def did_not_run(r: GateResult) -> bool:
    """Whether this result came from `unavailable` — the reader for the marker,
    so no caller has to know it is an underscore attribute."""
    return bool(getattr(r, "_unavailable", False))


def timeout_result(name: str, rc: int) -> GateResult | None:
    """WARN sentinel: the tool did not actually run (timeout, or a dockerized tool
    missing from the image). Never let that masquerade as a clean pass."""
    if rc == _TIMEOUT_RC:
        return unavailable(
            name, f"{name}: did not run (timeout or tool unavailable) — skipped"
        )
    return None


def missing_result(
    name: str, binary: str, *, tool: str | None = None
) -> GateResult | None:
    """WARN sentinel for a gate whose `binary` is neither on PATH nor in the tools
    image, else None so the gate proceeds. Mirrors timeout_result's idiom. `tool`
    overrides the name shown in the message (e.g. the licenses gate runs trivy)."""
    if not tool_missing(binary):
        return None
    return unavailable(
        name,
        f"{tool or binary} unavailable (no host binary or gandalf-tools image) — skipped",
    )
