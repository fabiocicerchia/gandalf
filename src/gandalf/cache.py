"""Result cache: skip re-running a gate when the scanned file set is unchanged.

Keyed on a single content hash of the scope's target files (same set every
gate sees — ctx.changed_files, or the whole tracked tree). One hash covers
every gate because they all run against the same scope.

ponytail: hash only covers file content, not tool versions or config — a
`ruff` upgrade or a newly-published CVE won't invalidate a hit. Add a
cache_version/tool-version component if that turns out to matter. Callers
also skip the cache entirely for scope inputs the hash can't see (--target,
--title, --body — see __main__.py), since those change gate behavior without
changing any file.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from pathlib import Path

from .base import GateOutcome, GateResult
from .plugins import ignore_patterns, is_ignored, scannable_files

DEFAULT_CACHE = ".gandalf-cache.json"


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


def content_hash(workdir: str, files: list[str]) -> str:
    """One hash over the scope's file names and contents.

    Names are hashed as well as bytes, so a rename invalidates the entry even
    when nothing inside the files changed — a gate that reads paths would
    otherwise return a stale answer. An unreadable file hashes as a fixed
    marker rather than raising: a cache key is not the place to fail a run.
    """
    h = hashlib.sha256()
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


def get(cache: dict, gate_name: str, file_hash: str) -> GateResult | None:
    """The cached result for a gate, if it was recorded against this hash.

    An entry that no longer deserialises is treated as a miss rather than an
    error: the shape of GateResult can change between versions, and an old
    cache must not stop a run.
    """
    entry = cache.get(gate_name)
    if not entry or entry.get("hash") != file_hash:
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
    """Record a gate's result against the hash of the files it saw."""
    cache[gate_name] = {"hash": file_hash, "result": asdict(result)}
