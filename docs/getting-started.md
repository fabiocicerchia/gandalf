# Getting Started

## Prerequisites

- Python 3.11+ (stdlib only — no packages to install).
- `git` (gandalf evaluates a git repo).
- Optional: the external scanner tools used by some gates (see the README's
  "tools" section, or `make tools` / `tools.Dockerfile`).

## Setup

```sh
git clone https://github.com/fabiocicerchia/gandalf
cd gandalf
```

The package lives under `src/`, so put `src` on `PYTHONPATH` (or use the
one-line wrapper in the README to install a `gandalf` command).

## Run

```sh
PYTHONPATH=src python -m gandalf                 # whole working tree (default)
PYTHONPATH=src python -m gandalf --staged        # staged changes only
PYTHONPATH=src python -m gandalf --commit <sha>  # a specific commit
PYTHONPATH=src python -m gandalf --path subdir/  # limit scanning to a folder
```

Exit code is `1` when the verdict is red, `0` otherwise — CI-usable. See the
[README](README.md) for the full flag reference and configuration
(`.gandalf.toml`).

## Scanners run in Docker — host stays clean

gandalf itself is pure-stdlib Python (nothing to install). The scanner tools live
in one image so they never touch the host:

```bash
make tools   # builds the gandalf-tools image (docker build -f gandalf/tools.Dockerfile)
```

Once built, any gate whose binary isn't on the host `PATH` runs its command
atomically as `docker run --rm -v <worktree>:/src gandalf-tools <tool> …`. A named
`gandalf-cache` volume keeps tool DBs (trivy, semgrep rules) warm across runs and
off the host. Resolution per tool, in order:

1. host binary on `PATH` → run it directly (no Docker);
1. else `gandalf-tools` image present → run the tool in a throwaway container;
1. else → the gate degrades to 🟡 WARN.

So you can `make tools` for zero host installs, *or* install any subset of tools
on the host and skip the image — both work, mixed freely. Override the image
name with `GANDALF_TOOLS_IMAGE`.

The image covers the language-agnostic tools: `ruff`, `semgrep`, `bandit`,
`pip-audit` (osv), `osv-scanner`, `trivy`, `gitleaks`, `checkov`, `hadolint`,
`scorecard`, `mypy`, `vulture`, `codespell`, `yamllint`, `shellcheck`,
`actionlint`. The Go
and Node gates use the host toolchain (`go`/`npx`/`npm`), and `ci_act` (host
Docker daemon), `tests` (project env), the `dynamic` DAST tools, and `atheris`
also run on the host.

### Review pull requests inline

gandalf ships as a reusable GitHub Action (`action.yml`), so a drop-in PR review
is a checkout plus one step:

```yaml
- uses: actions/checkout@v4
  with:
    fetch-depth: 0
- uses: fabiocicerchia/gandalf@main   # pin to a tag/SHA
  with:
    code-scanning: true               # also ingest into GitHub Code Scanning
```

On every pull request it pulls the prebuilt `ghcr.io/fabiocicerchia/gandalf-tools`
scanner image (building from source if the pull fails), scans the PR's diff, and
posts each finding as an inline review comment on the `file:line` it flags —
scoped to the diff so anchors match GitHub's view. With `code-scanning: true` it
also uploads SARIF so findings appear in the Security tab and as PR diff
annotations. It needs only the built-in `GITHUB_TOKEN`. gandalf reviews its own
PRs the same way via `.github/workflows/gandalf-pr.yml` (`uses: ./`). See
[`examples/github-actions/`](https://github.com/fabiocicerchia/gandalf/blob/main/examples/github-actions/README.md) for the full
drop-in workflow, inputs, code scanning, and the advisory-vs-blocking toggle.

### Other CI systems

The Action is GitHub-specific; gandalf is not. Anything that can run a
container and a git checkout can run the gates — the exit code is the verdict
(`1` red, `0` otherwise):

```sh
git clone --depth 1 --branch v0.4.0 https://github.com/fabiocicerchia/gandalf /opt/gandalf
PYTHONPATH=/opt/gandalf/src python3 -m gandalf --no-llm --no-html --no-trend \
  --out-dir reports --junit reports/gandalf.junit.xml
```

The decision that matters off GitHub Actions is **run the job inside
`ghcr.io/fabiocicerchia/gandalf-tools`** rather than letting gandalf shell out
to Docker per tool. Inside the image every scanner is already on `PATH`, so no
Docker daemon is involved — which is not just tidier, it is the only thing that
works where the CI's Docker cannot bind-mount the job's filesystem (CircleCI's
`setup_remote_docker`, GitLab with a dind service) or where mounting a socket
into the pod would be a much bigger ask (Tekton, Argo).

Two things bite everywhere: `git config --global --add safe.directory "*"`
(the checkout is owned by a different uid, and git otherwise refuses to read
it), and `--out-dir` pointed somewhere writable when the platform cannot run
the container as root.

Drop-in files for GitLab CI, CircleCI, Travis, Azure DevOps, AWS CodePipeline,
Devtron, Northflank, Spacelift, Jenkins, Bitbucket Pipelines, Google Cloud
Build, Tekton, Argo Workflows, Harness, Buildkite and Drone/Woodpecker are in
[`examples/ci-platforms/`](https://github.com/fabiocicerchia/gandalf/blob/main/examples/ci-platforms/README.md), along with which
platform ingests `--junit` where, and how to adopt on a repo that isn't green
yet (`--min-score`, `--write-baseline`).
