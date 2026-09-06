"""Finding suppression + baseline.

Two ways to stop a KNOWN finding from failing the gate — without disabling the
whole gate (that's `skip` in config):

* **rules** — `[gandalf.suppress] rules = ["gate:rule:pathglob", ...]`. Any field
  may be empty to wildcard: `"ruff:E501"` mutes that code everywhere;
  `"gitleaks::tests/*"` mutes gitleaks under `tests/`; `"vulture"` mutes the gate
  entirely (but keeps it running, unlike `skip`).
* **baseline** — a generated `.gandalf-baseline.json` snapshot of the findings
  present today. On later runs those exact findings are muted, so only *new*
  findings can fail. Regenerate with `--write-baseline`.

Suppression removes findings from a gate and re-scores it: if every finding was
muted the gate passes; a partial mute keeps the gate's outcome but raises its
score toward green and hides the muted findings. Suppression can only make a
gate better, never worse.
"""

from __future__ import annotations

import hashlib
import json
from fnmatch import fnmatch
from pathlib import Path

from . import findings
from .base import GateOutcome, GateResult
from .plugins import carry_over

DEFAULT_BASELINE = ".gandalf-baseline.json"


# Reading a finding is findings.py's job — these names stay as the vocabulary
# the rest of the codebase already imports from here.
finding_path = findings.path
finding_rule = findings.rule


def fingerprint(gate: str, f: dict) -> str:
    """Stable id for a finding, line-insensitive so it survives edits above it.
    gate + path + rule + a short message hash.

    Reads through `findings.fingerprint_keys`, which is frozen: a baseline file
    is a list of these hashes sitting in someone's repository, so widening the
    vocabulary would silently un-accept every finding they had agreed to live
    with. See the comment on it.
    """
    fp_path, fp_rule, fp_message = findings.fingerprint_keys(f)
    key = f"{gate}|{fp_path}|{fp_rule}|{fp_message[:200]}"
    # nosemgrep: insecure-hash-algorithm-sha1 — content-dedup key, not security
    return hashlib.sha1(key.encode("utf-8", "replace"), usedforsecurity=False).hexdigest()


class _Rule:
    """A parsed 'gate:rule:pathglob' suppression rule ('' = wildcard)."""

    def __init__(self, spec: str) -> None:
        parts = ([*spec.split(":", 2), "", "", ""])[:3]
        self.gate, self.rule, self.path = (p.strip() for p in parts)

    def matches(self, gate: str, f: dict) -> bool:
        if self.gate and self.gate != gate:
            return False
        if self.rule and self.rule != findings.rule(f):
            return False
        return not (self.path and not fnmatch(findings.path(f), self.path))


class Suppressor:
    """Decides which findings a run is allowed to stop reporting.

    Two mechanisms, deliberately separate: explicit rules are a standing
    decision about a class of finding, a baseline is "everything as of today,
    so only new ones nag". Neither deletes a finding — both mark it, so the
    count of what was suppressed stays visible.
    """

    def __init__(self, rules: list[str] | None = None, baseline: set[str] | None = None) -> None:
        self.rules = [_Rule(r) for r in (rules or []) if r.strip()]
        self.baseline = baseline or set()

    @property
    def active(self) -> bool:
        return bool(self.rules or self.baseline)

    def _muted(self, gate: str, f: dict) -> bool:
        if any(r.matches(gate, f) for r in self.rules):
            return True
        return fingerprint(gate, f) in self.baseline

    def apply(self, res: GateResult) -> GateResult:
        """Filter a gate's findings and re-score. Never makes a gate worse."""
        if not self.active or not res.findings:
            return res
        kept, muted = [], 0
        for f in res.findings:
            if self._muted(res.name, f):
                muted += 1
            else:
                kept.append(f)
        if muted == 0:
            return res
        total = muted + len(kept)
        if not kept:
            return carry_over(
                res,
                GateResult(
                    res.name,
                    GateOutcome.PASS,
                    1.0,
                    f"{res.summary}  · all {muted} finding(s) suppressed",
                    [],
                ),
            )
        # Partial: keep outcome, nudge score toward green by the muted fraction.
        score = res.score + (1.0 - res.score) * (muted / total)
        return carry_over(
            res,
            GateResult(
                res.name,
                res.outcome,
                min(1.0, max(res.score, score)),
                f"{res.summary}  · {muted} suppressed, {len(kept)} remaining",
                kept,
            ),
        )


def load_baseline(path: str) -> set[str]:
    """The accepted fingerprints from a baseline file, or an empty set.

    A missing or unreadable baseline suppresses nothing, which is the safe
    direction: the failure mode is noise, not a silently green run.
    """
    p = Path(path)
    if not p.is_file():
        return set()
    try:
        data = json.loads(p.read_text())
    except (OSError, json.JSONDecodeError):
        return set()
    return set(data.get("fingerprints", []) or [])


def build(cfg_section: dict, baseline_path: str | None) -> Suppressor:
    """Assemble a Suppressor from the [gandalf.suppress] table + a baseline file."""
    rules = list(cfg_section.get("rules", []) or [])
    path = baseline_path or cfg_section.get("baseline") or ""
    baseline = load_baseline(path) if path else set()
    return Suppressor(rules, baseline)


def write_baseline(path: str, results: list[GateResult], generated_at: str) -> int:
    """Snapshot every current finding's fingerprint so later runs mute them.
    Returns the count written."""
    fps = sorted({fingerprint(r.name, f) for r in results for f in r.findings})
    Path(path).write_text(json.dumps({"generated_at": generated_at, "fingerprints": fps}, indent=2))
    return len(fps)
