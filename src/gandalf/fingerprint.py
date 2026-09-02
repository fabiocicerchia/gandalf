"""The frozen vocabulary suppression fingerprints are computed from.

Suppression fingerprints are hashes of these fields, and a baseline file is a
list of those hashes sitting in someone's repository. Widening the key lists
`findings.py` reads with would change what a finding hashes to and silently
un-accept every finding in every committed .gandalf-baseline.json — the tool
would go loud again on exactly the findings a team had agreed to live with.

So fingerprints keep the vocabulary they were computed with. That is a decision
rather than an accident, and it is why it lives in a file of its own: the lists
here deliberately differ from the ones next door, and nothing may reconcile them.

Do not edit any of this without a baseline format version and a migration.
"""

from __future__ import annotations

_FP_PATH_KEYS: tuple[str, ...] = ("path", "filename", "file", "file_path")
_FP_RULE_KEYS: tuple[str, ...] = (
    "rule_id",
    "check_id",
    "RuleID",
    "test_id",
    "code",
    "check_name",
    "QueryName",
    "VulnerabilityID",
    "id",
    "rule",
)
_FP_MESSAGE_KEYS: tuple[str, ...] = (
    "message",
    "issue_text",
    "description",
    "Description",
    "finding",
    "typo",
    "missing",
)


def _first_truthy(f: object, keys: tuple[str, ...]) -> str:
    """The or-chain the suppression helpers used, preserved exactly.

    Deliberately not `findings.first_str`: that one strips whitespace and skips
    bools, and either difference would move a hash. A fingerprint helper may
    only change when the baseline format does.
    """
    if not isinstance(f, dict):
        return ""
    for k in keys:
        v = f.get(k)
        if v:
            return str(v)
    return ""


def fingerprint_keys(f: object) -> tuple[str, str, str]:
    """`(path, rule, message)` as suppression hashes them. Frozen — see above.

    A non-dict finding has no fields to read, and its whole string form is the
    only thing there is to identify it by — which is what `_message` did.
    """
    if not isinstance(f, dict):
        return "", "", str(f)
    return (
        _first_truthy(f, _FP_PATH_KEYS),
        _first_truthy(f, _FP_RULE_KEYS),
        _first_truthy(f, _FP_MESSAGE_KEYS),
    )
