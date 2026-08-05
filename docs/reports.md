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
     "summary": "1 file(s) fail to compile — …", "findings": [...], "blocking": true}
  ]
}
```

`commit` is the evaluated commit for `--commit`, else the latest commit (HEAD)
even for `--staged` / working-tree scopes.

## Score badge

`--badge` writes a [shields.io endpoint badge](https://shields.io/badges/endpoint-badge)
JSON (default: `reports/<stem>-badge.json`) — score and RAG color, no SVG
rendering on gandalf's side. Commit it somewhere with a stable raw URL (a
`badge` branch, a gh-pages deploy, …) and point a README at it:

```md
![gandalf score](https://img.shields.io/endpoint?url=<raw-URL-to-that-file>)
```
