#!/usr/bin/env python
"""Atheris harness for gandalf's output *adapters* — the pure functions that turn
untrusted external text (LLM replies, tool JSON, config specs) into structured
findings. These are the parsers most exposed to malformed input, so a crash here
is a real bug; deterministic tool gates own everything else.

Run under the atheris gate (``gandalf.gates.dynamic.AtherisGate``):

    python tests/fuzz/fuzz_adapters.py -max_total_time=60

Or self-check the dispatch without atheris installed (CI-friendly smoke test):

    python tests/fuzz/fuzz_adapters.py --selfcheck
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# The harness runs from a throwaway worktree; make gandalf importable either way.
_SRC = Path(__file__).resolve().parents[2] / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

# Instrument the adapters for coverage when atheris is present, so libFuzzer gets
# feedback and converges fast instead of burning the whole time budget on blind
# random bytes. Falls back to a plain import for the atheris-free --selfcheck path.
try:
    import atheris

    with atheris.instrument_imports():
        from gandalf import llm, report, severity, skills, suppress  # noqa: E402
except ImportError:
    from gandalf import llm, report, severity, skills, suppress  # noqa: E402

# Exceptions each adapter is CONTRACTED to raise on bad input — expected, not a
# fuzz finding. Anything outside these propagates and atheris flags it.
_EXPECTED = (ValueError, KeyError, TypeError, IndexError, json.JSONDecodeError)


def _exercise(text: str) -> None:
    """Feed one fuzzed string through every text adapter, and through the dict
    adapters as both a message string and a nested finding dict."""
    finding = {"path": text[:80], "message": text, "extra": {"message": text}}

    llm._split_sections(text)
    llm._split_gates(text)
    report.fmt_finding(finding)
    report.fmt_finding({"finding": text})
    severity.of(finding)
    severity.of({"extra": {"severity": text}})

    try:
        skills._parse_json(text)
    except json.JSONDecodeError:
        pass  # documented: tolerant parser still rejects non-JSON

    try:
        suppress._Rule(text)
    except _EXPECTED:
        pass  # malformed "gate:rule:path:line" specs are rejected, not fatal


def _test_one_input(data: bytes) -> None:
    try:
        text = data.decode("utf-8", "surrogatepass")
    except UnicodeDecodeError:
        return
    _exercise(text)


def _selfcheck() -> None:
    """Smallest thing that fails if an adapter crashes on hostile-but-plausible
    input. Runs without atheris so it can live in the normal test path too."""
    seeds = [
        "",
        "@@GATE@@\n@@GATE x@@\nbody",
        "@@SUMMARY@@\nhi\n@@REMEDIATION@@\n@@GATE ruff@@\n- fix",
        '```json\n{"score": 5}\n```',
        "not json { broken",
        "ruff:E501:foo.py:12",
        ":::::",
        "\x00￿\U0001f4a9",
        "[" * 20000,  # over-nested JSON: json.loads raises RecursionError, not JSONDecodeError
    ]
    for s in seeds:
        _exercise(s)  # must not raise anything outside each adapter's contract
    print(f"selfcheck ok: {len(seeds)} seeds")


def main() -> None:
    if "--selfcheck" in sys.argv:
        _selfcheck()
        return

    atheris.Setup(sys.argv, _test_one_input)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
