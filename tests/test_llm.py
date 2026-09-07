"""Tests for LLM network retry. Run: pytest gandalf/test_llm.py"""

from __future__ import annotations

import email.message
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any, cast

import pytest

from gandalf import llm

# HTTPError wants a header object; nothing under test reads one.
_NO_HEADERS = email.message.Message()


class _FakeResp:
    def __init__(self, payload: bytes) -> None:
        self._p = payload

    def __enter__(self) -> _FakeResp:
        return self

    def __exit__(self, *a: object) -> bool:
        return False

    def read(self) -> bytes:
        return self._p


def test_split_gates_drops_already_addressed_stubs() -> None:
    md = (
        "@@GATE grill_me@@\n"
        "- (Already addressed above.)\n"
        "@@GATE mypy@@\n"
        "- src/gandalf/report.py:42 add a type hint for `f`\n"
    )
    _pre, groups = llm._split_gates(md)
    assert [name for name, _ in groups] == ["mypy"]


def test_retryable_classification() -> None:
    assert llm._retryable(urllib.error.URLError("x"))
    assert llm._retryable(urllib.error.HTTPError("u", 503, "m", _NO_HEADERS, None))
    assert llm._retryable(TimeoutError())
    assert not llm._retryable(urllib.error.HTTPError("u", 400, "m", _NO_HEADERS, None))
    assert not llm._retryable(ValueError())
    # An OSError subclass, so this only holds while it is checked first.
    assert not llm._retryable(llm.LLMUnreachableError("nothing listening"))


def test_connect_check_fails_fast_on_a_dead_endpoint(monkeypatch: pytest.MonkeyPatch):
    """A port with nothing on it must cost the connect budget, not the
    generation budget — and must not then be retried three more times."""
    import time as _time

    # Port 1 on loopback: refused immediately, so this asserts the fast path
    # without waiting out CONNECT_TIMEOUT.
    monkeypatch.setattr(llm, "LLM_URL", "http://127.0.0.1:1/v1")
    monkeypatch.setattr(
        llm.urllib.request,
        "urlopen",
        _never_called,
    )
    t0 = _time.monotonic()
    with pytest.raises(llm.LLMUnreachableError) as excinfo:
        llm.chat([{"role": "user", "content": "hi"}])
    assert "127.0.0.1:1" in str(excinfo.value)
    assert _time.monotonic() - t0 < llm.CONNECT_TIMEOUT


def _never_called(*a: object, **k: object) -> Any:
    raise AssertionError("must not be reached")


def _patch(monkeypatch: pytest.MonkeyPatch, fn: Callable[..., Any]) -> None:
    monkeypatch.setattr(llm.urllib.request, "urlopen", fn)
    monkeypatch.setattr(llm, "BACKOFF", 0.0)  # no real sleeping
    monkeypatch.setattr(llm, "RETRIES", 2)


def test_retries_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"n": 0}

    def flaky(req: urllib.request.Request, timeout: int = 0) -> _FakeResp:
        calls["n"] += 1
        if calls["n"] < 3:
            raise urllib.error.URLError("boom")
        return _FakeResp(b'{"ok": 1}')

    _patch(monkeypatch, flaky)
    assert llm._request_with_retry(urllib.request.Request("http://x"), 1) == {"ok": 1}
    assert calls["n"] == 3  # two failures + one success


def test_non_retryable_raises_immediately(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"n": 0}

    def bad(req: urllib.request.Request, timeout: int = 0) -> _FakeResp:
        calls["n"] += 1
        raise urllib.error.HTTPError("u", 400, "bad", _NO_HEADERS, None)

    _patch(monkeypatch, bad)
    with pytest.raises(urllib.error.HTTPError):
        llm._request_with_retry(urllib.request.Request("http://x"), 1)
    assert calls["n"] == 1  # no retry on 4xx


def test_exhausts_retries_and_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"n": 0}

    def always_down(req: urllib.request.Request, timeout: int = 0) -> _FakeResp:
        calls["n"] += 1
        raise urllib.error.URLError("down")

    _patch(monkeypatch, always_down)
    with pytest.raises(urllib.error.URLError):
        llm._request_with_retry(urllib.request.Request("http://x"), 1)
    assert calls["n"] == 3  # RETRIES(2) + 1


if __name__ == "__main__":
    import contextlib

    class _MP:
        """Minimal monkeypatch shim so the file runs without pytest."""

        def __init__(self) -> None:
            self._undo: list[tuple[object, str, object]] = []

        def setattr(self, obj: object, name: str, val: object) -> None:
            self._undo.append((obj, name, getattr(obj, name)))
            setattr(obj, name, val)

        def undo(self) -> None:
            for obj, name, val in reversed(self._undo):
                setattr(obj, name, val)

    test_retryable_classification()
    for t in (
        test_retries_then_succeeds,
        test_non_retryable_raises_immediately,
        test_exhausts_retries_and_raises,
    ):
        mp = _MP()
        with contextlib.suppress(Exception):
            pass
        try:
            # The shim implements the one method these tests call.
            t(cast("pytest.MonkeyPatch", mp))
        finally:
            mp.undo()
