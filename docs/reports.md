# Reports and badges

## JSON report shape

```json
{
  "scope": "staged",
  "generated_at": "2026-07-03 13:10:42 UTC",
  "commit": {"sha": "…", "short": "ccfc3ec", "subject": "fix: …", "date": "2026-07-02T23:17:13+02:00"},
  "languages": ["python", "shell"],
  "verdict": "fail",
  "passed": false,
  "score": 60,
  "summary": "…",
  "remediation": "…markdown…",
  "improvement": "…markdown…",
  "skipped_gates": ["eslint", "go_build"],
  "tools": {
    "resolved": {"ruff": {"source": "host", "version": "ruff 0.15.8"},
                 "trivy": {"source": "image"}},
    "image": {"name": "gandalf-tools", "id": "sha256:…"}
  },
  "gates": [
    {"name": "build", "outcome": "fail", "score": 0.0,
     "summary": "1 file(s) fail to compile — …", "findings": [...],
     "category": "Build & tests", "blocking": true, "unavailable": false,
     "duration": 0.42}
  ]
}
```

`tools` records where each scanner actually came from — `host` (found on `PATH`)
or `image` (run inside `gandalf-tools`) — plus the image's content id, which is
what distinguishes one `make tools` build from another. `version` is present only
with `--tool-versions`. Gates that build their own `docker run` (kics, codeql)
name their image in their own summary instead. `unavailable` is true for a gate
that produced no signal about the code; those are excluded from `score`.

`commit` is the evaluated commit for `--commit`, else the latest commit (HEAD)
even for `--staged` / working-tree scopes. `category` is the same grouping the
scorecard uses ("Security", "Code quality", …), so a consumer doesn't have to
re-derive it; `duration` is the gate's wall-clock time in seconds.

`findings` are passed through from each underlying tool unchanged, so the same
field goes by different names across gates (`path` / `filename` / `file`,
`line` / `line_no` / `location.row`, …). Every finding additionally carries a
`_gandalf` block with those keys already reconciled, so a consumer doesn't have
to know which tool produced it:

```json
{
  "filename": "src/app.py", "line_number": 42, "test_id": "B105",
  "issue_text": "Possible hardcoded password", "issue_severity": "HIGH",
  "_gandalf": {
    "path": "src/app.py", "line": 42, "column": 0,
    "rule": "B105", "message": "Possible hardcoded password",
    "severity": "high", "url": ""
  }
}
```

`path` is repo-relative (container mounts are rebased); `line` and `column` are
1-based with `0` meaning unknown; `severity` is one of `critical`, `high`,
`medium`, `low`, `info`, `unknown`, or `""` when the tool published none — which
is not the same as `unknown`, where it published one and declined to rate it.
Where a gate hands back a bare tool line (`{"error": "src/a.py:552: …"}`), the
location is scraped from the text and only trusted when it names a file that
exists. A severity written into the message instead of a key (`[HIGH] …`, as
kics and the licenses gate do) is lifted out of it the same way.

`gandalf/findings.py` is the one place those keys are read; `report.py`,
`sarif.py`, `suppress.py`, `severity.py` and `pr_comments.py` all go through it.
Suppression fingerprints are the deliberate exception and keep a frozen
vocabulary — a baseline file is a list of hashes in someone's repository, so
widening the lists would silently un-accept every finding they had agreed to
live with.

## Score badge

`--badge` writes a [shields.io endpoint badge](https://shields.io/badges/endpoint-badge)
JSON (default: `reports/<stem>-badge.json`) — score and RAG color, no SVG
rendering on gandalf's side. Commit it somewhere with a stable raw URL (a
`badge` branch, a gh-pages deploy, …) and point a README at it:

```md
![gandalf score](https://img.shields.io/endpoint?url=<raw-URL-to-that-file>)
```
