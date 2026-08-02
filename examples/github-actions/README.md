# GitHub Action: inline PR review

What it shows: a drop-in workflow that runs gandalf on every pull request inside
a container of scanners and posts each finding as an **inline review comment**
anchored to the `file:line` it flags — plus a rolled-up summary for findings that
aren't on changed lines. It can also **ingest the same findings into GitHub Code
Scanning** (Security tab + PR diff annotations) behind a true/false toggle.

[`gandalf-pr-review.yml`](gandalf-pr-review.yml) is the whole thing. It needs
nothing installed on the runner and no secrets beyond the built-in
`GITHUB_TOKEN`.

## Install

1. Copy `gandalf-pr-review.yml` into your repo at
   `.github/workflows/gandalf-pr-review.yml`.
2. Pin the gandalf checkout: change `ref: main` to a release tag or a full
   commit SHA so your CI is reproducible and you control upgrades.
3. Open a pull request. gandalf reviews it and posts comments.

That's it — the workflow builds the scanner image itself and posts with the
token GitHub already provides.

## How it works

1. **Two checkouts** — your repo (the code under review) and gandalf itself into
   `./.gandalf` (untracked in your repo, so it never enters the scan).
2. **One image** — `tools.Dockerfile` bundles every scanner (`ruff`, `semgrep`,
   `bandit`, `trivy`, `gitleaks`, `hadolint`, `yamllint`, `shellcheck`,
   `actionlint`, …) on `PATH`. gandalf resolves each tool directly inside the
   container, so there's no nested Docker and nothing touches the runner.
3. **PR-diff scope** — the workflow stages `merge-base…head` and runs
   `--staged`, so gandalf sees exactly the PR's diff. That matters because
   GitHub rejects review comments placed off the diff.
4. **Post** — `--pr <n>` submits a single review via the REST API using
   `GITHUB_TOKEN` + `GITHUB_REPOSITORY`. Findings on changed lines become inline
   comments; the rest roll up into the review summary.

## What lands where

- **Inline comments** — findings that carry a file and line: `ruff`, `bandit`,
  `semgrep`, `sqlfluff`, `squawk`, `kics`, `codeql`, and any tool that reports
  structured locations. Multiple findings on one line merge into one comment.
- **Summary body** — findings without a usable line, or off the changed lines
  (e.g. `yamllint`, `mdl`, `shellcheck`, `actionlint`, repo-level checks). They
  roll up under "Other findings" so nothing is dropped.

## Permissions & the token

The workflow requests the minimum:

```yaml
permissions:
  contents: read
  pull-requests: write   # required to post the review
  security-events: write # required to upload SARIF to code scanning
```

It runs on the `pull_request` event, which is the safe choice: untrusted PR code
never sees your secrets. The trade-off is that **pull requests from forks get a
read-only token**, so both comment posting and code-scanning upload are skipped
there — a GitHub limitation, not a gandalf one. For a fork-friendly setup, post
from a separate `workflow_run` job triggered after this one; keep scanning on
`pull_request`.

## Code scanning (Security tab)

The workflow also produces SARIF and uploads it via
`github/codeql-action/upload-sarif`, so findings show up as **code scanning
alerts** in the Security tab and as annotations on the PR diff — with GitHub's
alert lifecycle (severity ranking, dismiss, and auto-close when a finding is
fixed). gandalf appears as its own tool named `gandalf`, alongside CodeQL and
anything else you upload; it is *not* merged into CodeQL's results.

Toggle it with a repository **Variable** (Settings → Secrets and variables →
Actions → Variables) named `GANDALF_INGEST_CODE_SCANNING`:

- unset or `true` (default) — upload SARIF to code scanning.
- `false` — skip the upload; only inline comments post. The `security-events`
  permission is still granted but goes unused.

Two things to know:

- **Private repos need GitHub Advanced Security** to accept SARIF uploads (code
  scanning is free on public repos). Without it the upload step fails; set the
  variable to `false`, or keep the workflow on public repos only.
- **Scope is the PR diff.** The upload reflects the PR's changed files, which is
  what you want for per-PR feedback. For a persistent whole-repo baseline in the
  Security tab, add a second trigger that runs gandalf whole-tree on push to your
  default branch (drop `--staged`) and uploads that SARIF too.

## Advisory vs blocking

By default the check is **advisory**: the inline comments are the signal, and a
red gandalf verdict doesn't fail the job. To gate merges on the verdict, change
the last line of the final step from `exit 0` to `exit "$code"` (gandalf exits
`1` on a red verdict, `0` otherwise). Tune the threshold with `--fail-on warn`
or `--min-score N`.

## Speeding up repeat runs

Building the tools image takes a few minutes. To avoid rebuilding it on every
PR, publish it once to a registry and pull it instead of building:

```yaml
- name: Pull gandalf-tools image
  run: docker pull ghcr.io/<you>/gandalf-tools:<tag> && \
       docker tag  ghcr.io/<you>/gandalf-tools:<tag> gandalf-tools
```

Then drop the checkout of gandalf and the `docker build` step, and point
`PYTHONPATH` at the gandalf source baked into your image (or `pip`-less-vendor it
in). Layer caching via `docker/build-push-action` with a `gha` cache is the
lighter-touch alternative if you'd rather keep building.
