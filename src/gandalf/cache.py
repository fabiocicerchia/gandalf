"""Result cache: skip re-running a gate when the scanned file set is unchanged.

Keyed on a single content hash of the scope's target files (same set every
gate sees — ctx.changed_files, or the whole tracked tree). One hash covers
every gate because they all run against the same scope.

The key is salted with the toolchain that produces the answers (see
`toolchain_salt`), because a cached result is only valid for the tools that
produced it. And entries for gates backed by an external advisory database
expire on age (see `max_age`): a newly-published CVE changes the right answer
for a lockfile that did not change at all, so content alone cannot decide.

Still uncovered: an upgrade to a scanner installed on the host PATH. Host
versions are only known after the tools have run, and the key is needed before
— see `toolchain_salt`. Delete the cache file, or skip `--cache`, after
upgrading host scanners. Callers also skip the cache entirely for scope inputs
the hash can't see (--target, --title, --body — see __main__.py), since those
change gate behavior without changing any file.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass, field
from functools import lru_cache
from pathlib import Path

from . import plugins
from .base import GateOutcome, GateResult
from .plugins import ignore_patterns, is_ignored, scannable_files

DEFAULT_CACHE = ".gandalf-cache.json"

# Bump when a change alters what a gate reports for input it already saw —
# new scoring, a reshaped result — so old entries are misses rather than lies.
CACHE_VERSION = 2

# Gates whose answer depends on an advisory database that moves without the repo
# moving: a fresh CVE against an untouched lockfile is a different answer for
# identical bytes, and a content hash cannot see it. Six hours keeps the cache
# useful within a working day while bounding how stale a dependency verdict gets.
# A gate may override with a `cache_ttl` attribute (seconds; 0 = never expire),
# the same plugin-friendly escape hatch report.py gives for `category`.
ADVISORY_TTL = 6 * 3600
ADVISORY_GATES = frozenset(
    {
        "osv",
        "osv_scanner",
        "trivy",
        "govulncheck",
        "cargo_audit",
        "bundler_audit",
        "composer_audit",
        "dotnet_audit",
        "licenses",
        "scorecard",
    }
)


@lru_cache(maxsize=1)
def _gandalf_version() -> str:
    """Best effort — an installed wrapper may not ship version.txt, and a missing
    version just means this component contributes nothing to the salt."""
    try:
        return (Path(__file__).resolve().parents[2] / "version.txt").read_text().strip()
    except OSError:
        return ""


def toolchain_salt() -> str:
    """Identity of the toolchain the results will come from.

    A cached result is only valid for the tools that produced it. The image is
    identified by content id, not by its tag: `gandalf-tools:latest` is rebuilt
    from whatever the package indexes served that day, so the tag is precisely
    the part that does not change when the tools inside do.

    Host binaries are absent by necessity — their versions are only known once
    they have run, and this has to be computed before anything runs.
    """
    return f"v{CACHE_VERSION}|{_gandalf_version()}|{plugins.tools_image_id()}"


def max_age(gate) -> float | None:
    """Seconds a cached result for this gate stays valid, or None for forever."""
    ttl = getattr(gate, "cache_ttl", None)
    if ttl is not None:
        return float(ttl) or None
    return ADVISORY_TTL if getattr(gate, "name", "") in ADVISORY_GATES else None


def target_files(workdir: str, changed_files: list[str]) -> list[str]:
    """Same file-set logic as plugins._scan_targets: the change's own files,
    falling back to the whole tracked tree, minus anything excluded.

    Excluded files are left out on purpose — the hash decides whether a gate's
    cached result still holds, and a file no gate reads cannot change it."""
    root = Path(workdir)
    pats = ignore_patterns(workdir)
    files = [
        f for f in changed_files if (root / f).is_file() and not is_ignored(f, pats)
    ]
    if files:
        return files
    return [f for f in scannable_files(workdir) if (root / f).is_file()]


def content_hash(workdir: str, files: list[str], salt: str = "") -> str:
    """One hash over the scope's file names and contents, plus the toolchain salt.

    Names are hashed as well as bytes, so a rename invalidates the entry even
    when nothing inside the files changed — a gate that reads paths would
    otherwise return a stale answer. An unreadable file hashes as a fixed
    marker rather than raising: a cache key is not the place to fail a run.
    """
    h = hashlib.sha256()
    h.update(salt.encode())
    root = Path(workdir)
    for f in sorted(files):
        h.update(f.encode())
        try:
            # file_digest reads in fixed-size blocks; `read_bytes()` pulled every
            # file into memory whole, and this walks the entire tracked tree.
            with (root / f).open("rb") as fh:
                h.update(hashlib.file_digest(fh, "sha256").digest())
        except OSError:
            h.update(b"?")
    return h.hexdigest()


def load(path: str) -> dict:
    """Read the cache file, or an empty cache.

    A missing, unreadable or corrupt file is not an error — the worst it can
    cost is a full re-run, which is exactly what happens.
    """
    p = Path(path)
    if not p.is_file():
        return {}
    try:
        return json.loads(p.read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def save(path: str, data: dict) -> None:
    """Write the cache back, pretty-printed so a diff on it is readable."""
    with Path(path).open("w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, default=str)


def get(
    cache: dict, gate_name: str, file_hash: str, max_age_s: float | None = None
) -> GateResult | None:
    """The cached result for a gate, if it was recorded against this hash and is
    not older than `max_age_s` (None = no expiry).

    An entry that no longer deserialises is treated as a miss rather than an
    error: the shape of GateResult can change between versions, and an old
    cache must not stop a run. An entry with no timestamp predates expiry and is
    treated as expired whenever a max age applies — the safe direction, since the
    cost is one re-run.
    """
    entry = cache.get(gate_name)
    if not entry or entry.get("hash") != file_hash:
        return None
    if max_age_s is not None:
        ts = entry.get("ts")
        if not isinstance(ts, (int, float)) or time.time() - ts > max_age_s:
            return None
    r = entry.get("result") or {}
    try:
        return GateResult(
            r["name"],
            GateOutcome(r["outcome"]),
            r["score"],
            r.get("summary", ""),
            r.get("findings", []),
        )
    except (KeyError, ValueError):
        return None


def put(cache: dict, gate_name: str, file_hash: str, result: GateResult) -> None:
    """Record a gate's result against the hash of the files it saw, and when.

    The timestamp is what lets a dependency verdict expire while the lockfile
    that produced it stays byte-identical — see `max_age`.
    """
    cache[gate_name] = {
        "hash": file_hash,
        "ts": time.time(),
        "result": asdict(result),
    }


@dataclass
class Plan:
    """What this run may skip, and how the skipped results come back.

    An inert Plan — no path — is what a run gets when the cache cannot apply:
    the content hash cannot see --target, --title or --body, and those change
    what a gate reports without changing a file. Every method then behaves as
    if nothing were cached, so the caller has no branch to write.
    """

    path: str | None = None
    data: dict = field(default_factory=dict)
    file_hash: str = ""

    def pending(self, active: list) -> list:
        """The gates with no live cache entry — all of them when caching is off."""
        if self.path is None:
            return active
        return [
            g
            for g in active
            if get(self.data, g.name, self.file_hash, max_age(g)) is None
        ]

    def merge(
        self, fresh: list[GateResult], active: list, ran: list
    ) -> tuple[list, list]:
        """Store what just ran → (every result in `active` order, the cached ones).

        The cached ones come back separately because they never ran, so nothing
        has reported them yet — --stream still has to.
        """
        if self.path is None:
            return fresh, []
        for r in fresh:
            put(self.data, r.name, self.file_hash, r)
        save(self.path, self.data)
        cached = [
            get(self.data, g.name, self.file_hash, max_age(g))
            for g in active
            if g not in ran
        ]
        by_name = {r.name: r for r in fresh + cached}
        return [by_name[g.name] for g in active], cached
