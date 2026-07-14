"""Tests for the debug logger. Run: pytest gandalf/test_debug.py"""

from __future__ import annotations

import io
import sys

from gandalf import debug


def _capture(fn):
    old, sys.stderr = sys.stderr, io.StringIO()
    try:
        fn()
        return sys.stderr.getvalue()
    finally:
        sys.stderr = old


def test_silent_when_disabled():
    debug._enabled = False
    assert _capture(lambda: debug.log("hi")) == ""


def test_writes_when_enabled():
    prev = debug._enabled
    try:
        debug.enable()
        out = _capture(lambda: debug.log("hello-world"))
        assert "hello-world" in out and "gandalf" in out
    finally:
        debug._enabled = prev


if __name__ == "__main__":
    test_silent_when_disabled()
    test_writes_when_enabled()
    print("ok")
