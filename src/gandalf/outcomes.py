"""GateResult sentinels for the cases where a gate has nothing to say.

"We could not check this" is not a quality signal, and every one of these
builders exists so a gate never has to spell that out — or accidentally report
it as a clean pass.
"""

from __future__ import annotations

from typing import Any

from .base import GateOutcome, GateResult
from .toolrun import TIMEOUT_RC, tool_missing


def mark(r: GateResult, **meta: object) -> GateResult:
    """Attach runner metadata to a result, under the underscore names the
    readers below and in `stream`, `outputs`, `junit` and `render_text` look for.

    Set out-of-band rather than declared on `GateResult`, which is the whole
    point: the dataclass stays byte-identical to ai-harness's, so a gate file
    still moves between the two projects untouched. This function is where that
    deliberate looseness is confined, instead of a `setattr` in every caller.
    """
    for key, value in meta.items():
        setattr(r, f"_{key}", value)
    return r


def meta(r: GateResult, name: str, default: Any = None) -> Any:
    """A value `mark` attached, or `default`. The reader half of the pair, so
    no caller has to spell the underscore name itself."""
    return getattr(r, f"_{name}", default)


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
    return mark(GateResult(name, GateOutcome.WARN, 0.8, summary), unavailable=True)


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
    return bool(meta(r, "unavailable", False))


def timeout_result(name: str, rc: int) -> GateResult | None:
    """WARN sentinel: the tool did not actually run (timeout, or a dockerized tool
    missing from the image). Never let that masquerade as a clean pass."""
    if rc == TIMEOUT_RC:
        return unavailable(name, f"{name}: did not run (timeout or tool unavailable) — skipped")
    return None


def missing_result(name: str, binary: str, *, tool: str | None = None) -> GateResult | None:
    """WARN sentinel for a gate whose `binary` is neither on PATH nor in the tools
    image, else None so the gate proceeds. Mirrors timeout_result's idiom. `tool`
    overrides the name shown in the message (e.g. the licenses gate runs trivy)."""
    if not tool_missing(binary):
        return None
    return unavailable(
        name,
        f"{tool or binary} unavailable (no host binary or gandalf-tools image) — skipped",
    )
