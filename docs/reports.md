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
  "gates": [
    {"name": "build", "outcome": "fail", "score": 0.0,
     "summary": "1 file(s) fail to compile — …", "findings": [...],
     "category": "Build & tests", "blocking": true, "duration": 0.42}
  ]
}
```

`commit` is the evaluated commit for `--commit`, else the latest commit (HEAD)
even for `--staged` / working-tree scopes. `category` is the same grouping the
scorecard uses ("Security", "Code quality", …), so a consumer doesn't have to
re-derive it; `duration` is the gate's wall-clock time in seconds.

`findings` are passed through from each underlying tool unchanged, so the same
field goes by different names across gates (`path` / `filename` / `file`,
`line` / `line_no` / `location.row`, …). `gandalf/report.py`, `gandalf/sarif.py`
and `editors/vscode/src/parse.ts` each reconcile the same key lists.

## Score badge

`--badge` writes a [shields.io endpoint badge](https://shields.io/badges/endpoint-badge)
JSON (default: `reports/<stem>-badge.json`) — score and RAG color, no SVG
rendering on gandalf's side. Commit it somewhere with a stable raw URL (a
`badge` branch, a gh-pages deploy, …) and point a README at it:

```md
![gandalf score](https://img.shields.io/endpoint?url=<raw-URL-to-that-file>)
```
