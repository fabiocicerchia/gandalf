"""Tests for the result cache. Run: pytest tests/test_cache.py"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from gandalf import cache, plugins
from gandalf.base import GateOutcome, GateResult


def test_content_hash_changes_with_file_content(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("x = 1\n")
    files = cache.target_files(str(tmp_path), ["a.py"])
    h1 = cache.content_hash(str(tmp_path), files)
    (tmp_path / "a.py").write_text("x = 2\n")
    h2 = cache.content_hash(str(tmp_path), files)
    assert h1 != h2


def test_get_put_roundtrip() -> None:
    data: dict[str, Any] = {}
    r = GateResult("ruff", GateOutcome.WARN, 0.8, "ruff: 1 issue", [{"path": "a.py"}])
    cache.put(data, "ruff", "abc123", r)
    got = cache.get(data, "ruff", "abc123")
    assert got == r
    # a different hash (file set changed) is a miss
    assert cache.get(data, "ruff", "different") is None
    # a different gate name is a miss
    assert cache.get(data, "eslint", "abc123") is None


def test_load_save_roundtrip(tmp_path: Path) -> None:
    path = str(tmp_path / ".gandalf-cache.json")
    data: dict[str, Any] = {}
    cache.put(data, "bandit", "h1", GateResult("bandit", GateOutcome.PASS, 1.0, "clean"))
    cache.save(path, data)
    loaded = cache.load(path)
    hit = cache.get(loaded, "bandit", "h1")
    assert hit is not None
    assert hit.outcome is GateOutcome.PASS


def test_load_missing_file_is_empty(tmp_path: Path) -> None:
    assert cache.load(str(tmp_path / "nope.json")) == {}


# --- key salt + expiry ------------------------------------------------------
def test_salt_changes_the_key(tmp_path: Path) -> None:
    """A cached answer is only valid for the toolchain that produced it."""
    (tmp_path / "a.py").write_text("x = 1\n")
    files = cache.target_files(str(tmp_path), ["a.py"])
    plain = cache.content_hash(str(tmp_path), files)
    salted = cache.content_hash(str(tmp_path), files, salt="v2||sha256:abc")
    other = cache.content_hash(str(tmp_path), files, salt="v2||sha256:def")
    assert plain != salted != other
    assert plain != other


def test_toolchain_salt_tracks_the_image_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cache.plugins, "tools_image_id", lambda: "sha256:aaa")
    first = cache.toolchain_salt()
    monkeypatch.setattr(cache.plugins, "tools_image_id", lambda: "sha256:bbb")
    assert cache.toolchain_salt() != first
    assert f"v{cache.CACHE_VERSION}" in first


def test_advisory_gates_expire_but_others_do_not() -> None:
    class G:
        name = "trivy"

    class Ruff:
        name = "ruff"

    assert cache.max_age(G()) == cache.ADVISORY_TTL
    assert cache.max_age(Ruff()) is None


def test_a_gate_may_override_its_own_ttl() -> None:
    class Custom:
        name = "trivy"
        cache_ttl = 60

    class Never:
        name = "trivy"
        cache_ttl = 0

    assert cache.max_age(Custom()) == 60
    assert cache.max_age(Never()) is None


def test_a_stale_advisory_entry_is_a_miss() -> None:
    """The reported bug: a fresh CVE against an unchanged lockfile must not be
    served from cache just because no byte moved."""
    data: dict[str, Any] = {}
    r = GateResult("trivy", GateOutcome.PASS, 1.0, "no known vulns")
    cache.put(data, "trivy", "h1", r)
    assert cache.get(data, "trivy", "h1", cache.ADVISORY_TTL) == r
    data["trivy"]["ts"] -= cache.ADVISORY_TTL + 1
    assert cache.get(data, "trivy", "h1", cache.ADVISORY_TTL) is None
    # ...but a gate with no expiry still hits.
    assert cache.get(data, "trivy", "h1", None) == r


def test_entry_without_a_timestamp_is_expired_when_a_max_age_applies() -> None:
    """Caches written before expiry existed must not be trusted indefinitely."""
    data = {
        "trivy": {
            "hash": "h1",
            "result": {"name": "trivy", "outcome": "pass", "score": 1.0},
        }
    }
    assert cache.get(data, "trivy", "h1", cache.ADVISORY_TTL) is None
    assert cache.get(data, "trivy", "h1", None) is not None


def test_durations_are_recorded_and_read_back_regardless_of_hash() -> None:
    """A stale entry's verdict is worthless; its duration is still the best
    estimate of what that gate costs here, and it is what orders the next run."""
    data: dict[str, Any] = {}
    r = GateResult("trivy", GateOutcome.PASS, 1.0, "no known vulns")
    cache.put(data, "trivy", "h1", plugins.mark(r, duration=42.5))
    assert cache.timings(data) == {"trivy": 42.5}
    # The files changed, so the result is a miss — the timing is not.
    assert cache.get(data, "trivy", "h2") is None
    assert cache.timings(data) == {"trivy": 42.5}


def test_timings_ignores_entries_that_have_none() -> None:
    """Caches written before durations were recorded must not become zeroes —
    a zero would schedule the heaviest gate last."""
    data: dict[str, Any] = {"trivy": {"hash": "h1", "result": {}}, "junk": "not a dict"}
    assert cache.timings(data) == {}


def test_an_inert_plan_has_no_timings() -> None:
    """No --cache means nowhere to have kept them; the scheduler uses priors."""
    assert cache.Plan().timings() == {}


class _Named:
    """A gate whose result carries a different name than the gate does — legal
    for a plugin, and the case that used to disappear."""

    def __init__(self, name: str) -> None:
        self.name = name


def test_merging_without_a_cache_keeps_a_result_the_gate_list_cannot_claim() -> None:
    """Ordering the report by the gate list is presentation; it must not also
    decide which results exist."""
    active = [_Named("ruff"), _Named("wrapper")]
    fresh = [
        GateResult("wrapper-inner", GateOutcome.PASS, 1.0, "renamed itself"),
        GateResult("ruff", GateOutcome.PASS, 1.0, "clean"),
    ]
    merged, cached = cache.Plan().merge(fresh, active, active)
    assert cached == []
    # Gate order for what lines up, then whatever was left — but nothing lost.
    assert [r.name for r in merged] == ["ruff", "wrapper-inner"]


def test_merging_survives_a_cache_entry_that_expired_mid_run(tmp_path: Path) -> None:
    """An advisory entry can pass `pending` and then expire before `merge` reads
    it back. That gate has no result at all; indexing the gate list by name used
    to raise rather than leave it out."""
    path = str(tmp_path / "c.json")
    data: dict[str, Any] = {}
    cache.put(data, "trivy", "h1", GateResult("trivy", GateOutcome.PASS, 1.0, "no known vulns"))
    data["trivy"]["ts"] -= cache.ADVISORY_TTL + 1  # expired since `pending` said "hit"
    plan = cache.Plan(path, data, "h1")

    active = [_Named("ruff"), _Named("trivy")]
    fresh = [GateResult("ruff", GateOutcome.PASS, 1.0, "clean")]
    merged, cached = plan.merge(fresh, active, [active[0]])
    assert cached == []
    assert [r.name for r in merged] == ["ruff"]
