"""Load `.gandalf.toml` — the per-repo, version-controlled gandalf config.

Everything gandalf can tune from a repo lives in one file so it reviews with the
code, instead of being scattered across env vars. Precedence is env var → config
file → built-in default (env still wins, for CI overrides).

    [gandalf]
    only        = ["ruff", "gitleaks"]   # allowlist: run ONLY these gates
    skip        = ["atheris"]            # denylist: never run these
    concurrency = 8                       # max gates running at once

    [gandalf.verdict]
    fail_on   = "fail"    # "fail" (default) | "warn" — lowest outcome that reddens
    min_score = 0         # 0-100; verdict is red below this composite score

    [gandalf.timeouts]
    default = 120         # per-gate subprocess timeout (seconds)
    semgrep = 300         # per-gate override, keyed by gate name

    [gandalf.severity]
    weight = true         # weight a gate's score by its findings' severity

    [gandalf.suppress]
    rules = ["gitleaks:generic-api-key", "ruff:E501:foo.py:12"]

The file is optional; with no file (or a broken one) gandalf uses its defaults.
"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path

from . import console

CONFIG_FILENAME = ".gandalf.toml"


class Config:
    """The `[gandalf]` table, with typed accessors. `data` is the raw table so
    later features can read their own sub-sections without touching this class."""

    def __init__(self, data: dict | None = None, path: str = "") -> None:
        self.data = data or {}
        self.path = path

    # --- gate selection -----------------------------------------------------
    @property
    def only(self) -> set[str]:
        return {str(x) for x in (self.data.get("only") or [])}

    @property
    def skip(self) -> set[str]:
        return {str(x) for x in (self.data.get("skip") or [])}

    def select(self, gates: list) -> tuple[list, list[str]]:
        """Apply only/skip. Returns (kept_gates, disabled_names). `only` is an
        allowlist (empty = allow all); `skip` always removes."""
        only, skip = self.only, self.skip
        kept, disabled = [], []
        for g in gates:
            if (only and g.name not in only) or g.name in skip:
                disabled.append(g.name)
            else:
                kept.append(g)
        return kept, sorted(disabled)

    @property
    def concurrency(self) -> int | None:
        v = self.data.get("concurrency")
        try:
            return int(v) if v is not None else None
        except (TypeError, ValueError):
            return None

    # --- sub-sections (used by later features) ------------------------------
    def section(self, name: str) -> dict:
        v = self.data.get(name)
        return v if isinstance(v, dict) else {}


def load(repo_root: str | None = None, explicit: str | None = None) -> Config:
    """Locate and parse the config. Order: explicit path (CLI --config) →
    GANDALF_CONFIG env → <repo_root>/.gandalf.toml → none (defaults)."""
    path = explicit or os.environ.get("GANDALF_CONFIG") or ""
    if not path and repo_root:
        cand = Path(repo_root) / CONFIG_FILENAME
        if cand.is_file():
            path = str(cand)
    if not path or not Path(path).is_file():
        return Config()
    try:
        with Path(path).open("rb") as fh:
            raw = tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        # A broken config must never sink the run — warn and fall back to defaults.
        console.err(f"gandalf: ignoring config {path}: {exc}")
        return Config()
    return Config(raw.get("gandalf", {}) or {}, path)
