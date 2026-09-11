"""Tests for the debug logger. Run: pytest gandalf/test_debug.py"""

from __future__ import annotations

import io
import sys
from collections.abc import Callable

import pytest

from gandalf import debug
from gandalf.progress import Progress


def _capture(fn: Callable[[], None]) -> str:
    old, sys.stderr = sys.stderr, io.StringIO()
    try:
        fn()
        return sys.stderr.getvalue()
    finally:
        sys.stderr = old


def test_silent_when_disabled() -> None:
    debug._state.enabled = False
    assert _capture(lambda: debug.log("hi")) == ""


def test_writes_when_enabled() -> None:
    prev = debug._state.enabled
    try:
        debug.enable()
        out = _capture(lambda: debug.log("hello-world"))
        assert "hello-world" in out
        assert "gandalf" in out
    finally:
        debug._state.enabled = prev


def test_hooks_bracket_a_log_line() -> None:
    """The progress bar clears its line before a debug line and redraws after,
    so the two share stderr instead of one of them standing down."""
    prev = debug._state.enabled
    calls: list[str] = []
    try:
        debug.enable()
        debug.around_log(lambda: calls.append("clear"), lambda: calls.append("redraw"))
        out = _capture(lambda: debug.log("gate trivy: start"))
        assert calls == ["clear", "redraw"]
        assert "gate trivy: start" in out
    finally:
        debug.around_log(None, None)
        debug._state.enabled = prev


def test_hooks_do_not_fire_when_debug_is_off() -> None:
    """Nothing is written, so nothing has to be cleared or redrawn."""
    prev = debug._state.enabled
    calls: list[str] = []
    try:
        debug._state.enabled = False
        debug.around_log(lambda: calls.append("clear"), lambda: calls.append("redraw"))
        _capture(lambda: debug.log("hi"))
        assert calls == []
    finally:
        debug.around_log(None, None)
        debug._state.enabled = prev


def test_progress_keeps_drawing_under_debug(monkeypatch: pytest.MonkeyPatch) -> None:
    """The bar used to stand down under --debug, which took progress away from
    exactly the run you most wanted to watch. It registers with the logger
    instead, and the `\\r` its redraw re-issues is what keeps both halves
    parsable for a consumer reading the stream."""
    prev = debug._state.enabled
    monkeypatch.setenv("GANDALF_PROGRESS", "1")
    try:
        debug.enable()
        prog = Progress(3)
        out = _capture(lambda: (prog.stage("Running 5 gates"), prog.bar(1, 5, "ruff"), debug.log("x"))[0])
        assert "Running 5 gates" in out
        assert "[gandalf" in out
        # Bar, then a whole debug line, then the bar again — every segment
        # delimited by the \r the redraw starts with.
        assert out.count("\r") >= 3
    finally:
        prog.finish()
        debug._state.enabled = prev
