# GitHub Action: inline PR review

What it shows: a drop-in workflow that reviews every pull request with gandalf's
scanners in one container and posts each finding as an **inline review comment**
on the `file:line` it flags — plus a rolled-up summary for findings that aren't
on changed lines. It can also **ingest the same findings into GitHub Code
Scanning** (Security tab + PR diff annotations) behind a true/false toggle.

It's a reusable action, so the workflow is tiny: a checkout plus one `uses:`.
Nothing is installed on the runner and no secrets beyond the built-in
`GITHUB_TOKEN` are needed.

## Install

1. Copy [`gandalf-pr-review.yml`](gandalf-pr-review.yml) into your repo at
   `.github/workflows/gandalf-pr-review.yml`.
2. Pin the action: change `fabiocicerchia/gandalf@main` to a release tag or a
   full commit SHA so your CI is reproducible and you control upgrades.
3. Open a pull request. gandalf reviews it and posts comments.

The whole workflow:

```yaml
name: gandalf-pr-review
on: pull_request
permissions:
  contents: read
  packages: read         # pull the ghcr scanner image
  pull-requests: write   # post the review
  security-events: write # upload SARIF to code scanning
jobs:
  review:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0   # need base + head + merge-base for the PR diff
      - uses: fabiocicerchia/gandalf@main
        with:
          code-scanning: ${{ vars.GANDALF_INGEST_CODE_SCANNING || 'true' }}
```

## Inputs

| Input | Default | Purpose |
|-------|---------|---------|
| `code-scanning` | `true` | Also upload findings to GitHub Code Scanning. `false` = only inline comments. |
| `pr-number` | current PR | PR to post the review to. |
| `base-sha` / `head-sha` | from the PR event | Commits whose diff is scanned. |
| `tools-image` | `ghcr.io/fabiocicerchia/gandalf-tools:latest` | Scanner image to pull. Empty string = build from source instead. |
| `app-id` / `app-private-key` | — | GitHub App credentials to post as your own bot (see below). |
| `comment-title` / `comment-icon` | `gandalf` / `🧙` | Name + emoji shown in the comment text. |
| `extra-args` | — | Extra gandalf flags, e.g. `--fail-on warn` to fail the check on findings. |
| `github-token` | `${{ github.token }}` | Pulls the image and posts the review. |

## How it works

The action pulls a prebuilt scanner image
(`ghcr.io/fabiocicerchia/gandalf-tools`) that carries every scanner (`ruff`,
`semgrep`, `bandit`, `trivy`, `gitleaks`, `hadolint`, `yamllint`, `shellcheck`,
`actionlint`, …) on `PATH`, so gandalf runs each tool directly inside the
container — no nested Docker, nothing on the runner. If the pull fails (e.g. on a
fork, or before the image is published) it **builds the image from source**
automatically, so it always works.

It stages the PR's diff (`merge-base…head`) and scans with `--staged`, so gandalf
sees exactly the PR's changed lines — which matters because GitHub rejects review
comments placed off the diff. Findings on a line the diff **adds** that carry a
file+line (`ruff`, `bandit`, `semgrep`, `sqlfluff`, `squawk`, `kics`, …) become
inline comments; the rest (`yamllint`, `mdl`, `shellcheck`, repo-level checks, and
anything on an unchanged line) roll up under "Other findings" in the summary so
nothing is dropped.

Re-runs update, they don't pile up. The summary is a single sticky comment that
gets **edited in place** with a "Last updated …" stamp on every push, and inline
comments are reconciled against the PR: unchanged ones are left alone (so reply
threads and notifications survive), obsolete ones are **resolved**, new ones
posted. Nothing is ever deleted — a resolved thread collapses out of the way but
keeps the record of what was flagged and anything said back, and you can reopen
it. A finding that comes back after being resolved gets a fresh comment.

## Code scanning (Security tab)

With `code-scanning: true` (default), the action also uploads SARIF via
`github/codeql-action/upload-sarif`, so findings show up as **code scanning
alerts** in the Security tab and as annotations on the PR diff — with GitHub's
alert lifecycle (severity ranking, dismiss, and auto-close when a finding is
fixed). gandalf appears as its own tool named `gandalf`, alongside CodeQL and
anything else you upload; it is *not* merged into CodeQL's results.

To turn it off for a repo without editing the file, set a repository **Variable**
(Settings → Secrets and variables → Actions → Variables) named
`GANDALF_INGEST_CODE_SCANNING` to `false` — the example wires that variable into
the `code-scanning` input.

Three things to know:

- **The Security tab defaults to your default branch.** This workflow runs on
  `pull_request`, so its alerts belong to the PR, not to `main` — they show on
  the PR's *Files changed* tab and under its "Code scanning results" check. On
  `…/security/code-scanning` you have to switch the **Branch** filter to the PR's
  branch to see them; an empty list on `main` is expected until a run analyses
  `main` itself.
- **Private repos need GitHub Advanced Security** to accept SARIF uploads (code
  scanning is free on public repos). Without it the upload step fails; set
  `code-scanning: false`, or keep the workflow on public repos only.
- **Scope is the PR diff.** The upload reflects the PR's changed files, which is
  what you want for per-PR feedback. For a persistent whole-repo baseline in the
  Security tab, add a job that runs gandalf whole-tree on push to your default
  branch and uploads that SARIF too.

## Custom bot name + icon

By default comments are authored by **`github-actions[bot]`** with the generic
Actions avatar — GitHub binds the author to the token, and that name/icon can't be
changed. To post as your own bot with a custom **name and logo**, use a GitHub
App:

1. Create a GitHub App (Settings → Developer settings → GitHub Apps → New). Give
   it a **name** (this becomes `<name>[bot]`) and upload a **logo** (this is the
   icon shown next to every comment).
2. Permissions: **Pull requests: Read & write** (and **Contents: Read**). No
   webhook needed.
3. Generate a **private key**, then **Install** the App on your repo.
4. Add two repository secrets: `APP_ID` (the App's numeric id) and
   `APP_PRIVATE_KEY` (the private-key PEM).
5. Pass them to the action:

   ```yaml
   - uses: fabiocicerchia/gandalf@main
     with:
       app-id: ${{ secrets.APP_ID }}
       app-private-key: ${{ secrets.APP_PRIVATE_KEY }}
   ```

The action mints a short-lived installation token and posts the review as your
App. Leave the inputs unset to keep `github-actions[bot]`.

Separately, `comment-title` and `comment-icon` change the name + emoji shown
*inside* the comment text (the `🧙 gandalf — …` header and per-finding prefix) —
independent of the author account.

## Permissions, the token, and forks

The workflow runs on the `pull_request` event, the safe choice: untrusted PR code
never sees your secrets. The trade-off is that **pull requests from forks get a
read-only token**, so comment posting and code-scanning upload are skipped there
— a GitHub limitation, not a gandalf one. For a fork-friendly setup, run the
action from a separate `workflow_run` job triggered after this one.

## Advisory vs blocking

By default the check is **advisory**: the review and alerts are the signal, and a
red gandalf verdict doesn't fail the job. To gate merges on the verdict, pass
`extra-args: --fail-on warn` (or `--min-score N`) — gandalf then exits non-zero
and fails the step.
