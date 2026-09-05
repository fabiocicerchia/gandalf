"""Score-over-time trend log: one JSONL line appended per run, so the report
header can show the delta vs. the previous commit.

ponytail: no rotation/pruning — the log grows with every run. Add a max-lines
trim if that ever matters; for a local quality-gate history it won't.
"""

from __future__ import annotations

import json
from pathlib import Path

DEFAULT_TREND = ".gandalf-trend.jsonl"


def previous_score(path: str, current_commit: str) -> int | None:
    """Score of the most recent recorded run whose commit differs from the
    current one (so re-running the same commit doesn't compare against itself)."""
    p = Path(path)
    if not p.is_file():
        return None
    prev = None
    for line in p.read_text().splitlines():
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if entry.get("commit") and entry["commit"] != current_commit:
            prev = entry
    return prev["score"] if prev else None


def record(path: str, commit: str, score: int, generated_at: str) -> None:
    """Append one run to the trend log.

    Append-only JSONL: a corrupt or half-written line costs one data point, and
    previous_score() already skips lines it cannot parse.
    """
    with Path(path).open("a") as f:
        f.write(json.dumps({"commit": commit, "score": score, "generated_at": generated_at}) + "\n")
