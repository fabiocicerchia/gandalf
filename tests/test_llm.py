"""Tests for LLM network retry. Run: pytest gandalf/test_llm.py"""

from __future__ import annotations

import urllib.error
import urllib.request

from gandalf import llm


class _FakeResp:
    def __init__(self, payload):
        self._p = payload

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return self._p


def test_retryable_classification():
    assert llm._retryable(urllib.error.URLError("x"))
    assert llm._retryable(urllib.error.HTTPError("u", 503, "m", {}, None))
    assert llm._retryable(TimeoutError())
    assert not llm._retryable(urllib.error.HTTPError("u", 400, "m", {}, None))
    assert not llm._retryable(ValueError())


def _patch(monkeypatch, fn):
    monkeypatch.setattr(llm.urllib.request, "urlopen", fn)
    monkeypatch.setattr(llm, "BACKOFF", 0.0)  # no real sleeping
    monkeypatch.setattr(llm, "RETRIES", 2)


def test_retries_then_succeeds(monkeypatch):
    calls = {"n": 0}

    def flaky(req, timeout=0):
        calls["n"] += 1
        if calls["n"] < 3:
            raise urllib.error.URLError("boom")
        return _FakeResp(b'{"ok": 1}')

    _patch(monkeypatch, flaky)
    assert llm._request_with_retry(urllib.request.Request("http://x"), 1) == {"ok": 1}
    assert calls["n"] == 3  # two failures + one success


def test_non_retryable_raises_immediately(monkeypatch):
    calls = {"n": 0}

    def bad(req, timeout=0):
        calls["n"] += 1
        raise urllib.error.HTTPError("u", 400, "bad", {}, None)

    _patch(monkeypatch, bad)
    try:
        llm._request_with_retry(urllib.request.Request("http://x"), 1)
        assert False, "should have raised"
    except urllib.error.HTTPError:
        pass
    assert calls["n"] == 1  # no retry on 4xx


def test_exhausts_retries_and_raises(monkeypatch):
    calls = {"n": 0}

    def always_down(req, timeout=0):
        calls["n"] += 1
        raise urllib.error.URLError("down")

    _patch(monkeypatch, always_down)
    try:
        llm._request_with_retry(urllib.request.Request("http://x"), 1)
        assert False, "should have raised"
    except urllib.error.URLError:
        pass
    assert calls["n"] == 3  # RETRIES(2) + 1


if __name__ == "__main__":
    import contextlib

    class _MP:
        """Minimal monkeypatch shim so the file runs without pytest."""

        def __init__(self):
            self._undo = []

        def setattr(self, obj, name, val):
            self._undo.append((obj, name, getattr(obj, name)))
            setattr(obj, name, val)

        def undo(self):
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
            t(mp)
        finally:
            mp.undo()
    print("ok")
