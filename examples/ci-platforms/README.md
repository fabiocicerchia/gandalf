# CI Platforms

What it shows: running gandalf's gates on the sixteen CI/CD systems that aren't
GitHub Actions. One file per platform, each one a drop-in.

The action is GitHub-specific; gandalf is not. It is pure-stdlib Python, it
scans a git checkout, and its exit code is the verdict:

```sh
git clone --depth 1 --branch v0.4.0 https://github.com/fabiocicerchia/gandalf /opt/gandalf
PYTHONPATH=/opt/gandalf/src python3 -m gandalf --no-llm --no-html --no-trend \
  --out-dir reports --junit reports/gandalf.junit.xml
```

| exit | meaning |
|---|---|
| `0` | verdict is green or amber |
| `1` | verdict is red — or, with `--min-score N`, the composite score is below N |

## Files

| Platform | File | Copy it to |
|---|---|---|
| GitLab CI | [`gitlab-ci.yml`](gitlab-ci.yml) | `.gitlab-ci.yml` |
| CircleCI | [`circleci-config.yml`](circleci-config.yml) | `.circleci/config.yml` |
| Travis CI | [`travis.yml`](travis.yml) | `.travis.yml` |
| Azure DevOps | [`azure-pipelines.yml`](azure-pipelines.yml) | `azure-pipelines.yml` |
| AWS CodePipeline | [`buildspec.yml`](buildspec.yml) | `buildspec.yml` (CodeBuild stage) |
| Devtron | [`devtron-task.sh`](devtron-task.sh) | a Pre-Build or Pre-Deployment task |
| Northflank | [`northflank-job.json`](northflank-job.json) | `northflank create job manual -f …` |
| Spacelift | [`spacelift-config.yml`](spacelift-config.yml) | `.spacelift/config.yml` |
| Jenkins | [`Jenkinsfile`](Jenkinsfile) | `Jenkinsfile` |
| Bitbucket Pipelines | [`bitbucket-pipelines.yml`](bitbucket-pipelines.yml) | `bitbucket-pipelines.yml` |
| Google Cloud Build | [`cloudbuild.yaml`](cloudbuild.yaml) | `cloudbuild.yaml` |
| Tekton | [`tekton.yaml`](tekton.yaml) | `kubectl apply -f` |
| Argo Workflows | [`argo-workflow.yaml`](argo-workflow.yaml) | `argo submit` |
| Harness | [`harness-pipeline.yml`](harness-pipeline.yml) | the pipeline's YAML editor |
| Buildkite | [`buildkite-pipeline.yml`](buildkite-pipeline.yml) | `.buildkite/pipeline.yml` |
| Drone / Woodpecker | [`drone.yml`](drone.yml) | `.drone.yml` / `.woodpecker.yml` |

For GitHub Actions use the action itself — see
[`../github-actions/`](../github-actions/README.md), which additionally posts
inline `file:line` review comments and uploads SARIF to Code Scanning.

## Run the job *inside* the scanner image

This is the one decision that matters, and fifteen of the sixteen files make
the same one: **use `ghcr.io/fabiocicerchia/gandalf-tools` as the job's own
image** rather than letting gandalf shell out to Docker per tool.

gandalf resolves each tool in order — host binary on `PATH`, else the
`gandalf-tools` image via `docker run`, else the gate degrades to a yellow
WARN. Inside the image, every tool is on `PATH`, so the first branch wins and
no Docker daemon is involved at all. That is not just tidier, it is the only
arrangement that works on several of these platforms:

- **CircleCI's `setup_remote_docker`** cannot bind-mount the job's filesystem.
  A `docker run -v $PWD:/src` there mounts nothing, the scan sees an empty
  tree, and everything passes. Silently.
- **GitLab with a dind service** has the same problem: `-v $PWD` resolves
  against the *dind daemon's* filesystem, not your checkout.
- **Kubernetes-native platforms** (Tekton, Argo) would need a Docker socket
  mounted into the pod, which is a much larger ask than a different image.

Travis is the exception: it runs the job on the VM rather than an image you
choose, so [`travis.yml`](travis.yml) takes the other path — pull the image,
let gandalf drive it. `docker image inspect` is how gandalf finds it, and it
never pulls on its own, so the `docker pull` has to be in the file.

The image is `python:3.14-slim` with git and every scanner added, so it can run
gandalf itself; nothing else has to be installed.

## Two things bite on every platform

**Git ownership.** The checkout is created by the runner and the container runs
as a different uid, so git refuses to touch it ("dubious ownership") and the
diff-scoped gates come back empty. `git config --global --add safe.directory
"*"` first, in every file here.

**Writing reports.** The image runs as uid 1000; most runners clone as root.
Where the platform can set the container user, these files do
(`docker: {user: root}`, `user: root`, `run-as-user: 0`, `--user 0:0`). Where it
cannot — Drone, Devtron, Northflank, Spacelift — `--out-dir` points at `/tmp`
instead, and `--no-trend` keeps gandalf from writing `.gandalf-trend.jsonl`
into the checkout.

## The LLM gates

Several gates ask an LLM to judge (`quality_gate_review`, `grill_me`,
`codebase_architecture`, `well_architected`, `pr_code_summary`), and the
summary is written by one. Without an endpoint they degrade to yellow WARN —
but not before retrying three times with backoff, seven seconds of sleeping
each, which is pure waste in CI. Every file sets:

```sh
GANDALF_LLM_RETRIES=0
```

`--no-llm` skips the *summary*; it does not stop the judge gates from trying.
To get all of them back, point gandalf at any OpenAI-compatible endpoint:

```sh
GANDALF_LLM_URL=https://your-endpoint/v1
GANDALF_API_KEY=…
GANDALF_MODEL=gpt-oss-120b
```

## Where the findings show up

The action posts inline review comments and Code Scanning alerts. Neither
exists off GitHub, so `--junit` is the portable equivalent: every gate becomes a
test case, and the platform's own test UI does the rest.

| Platform | Ingests JUnit as |
|---|---|
| GitLab CI | `artifacts: reports: junit` → the MR's test report widget |
| CircleCI | `store_test_results` → the Tests tab |
| Azure DevOps | `PublishTestResults@2` → the Tests tab |
| AWS CodeBuild | `reports:` with `file-format: JUNITXML` → a report group |
| Jenkins | `junit` step → the build's test trend |
| Bitbucket | anything under `test-results/` → the Tests tab |
| Buildkite | the `junit-annotate` plugin → a build annotation |
| Harness | `reports: {type: JUnit}` on the Run step |
| Everything else | uploaded as an artifact |

`--sarif` is also there, and worth wiring up if your platform has a security
dashboard that reads it. `--badge` writes shields.io endpoint JSON for the
score, and `--json` prints the whole report for anything downstream.

## Adopting on a repo that isn't green yet

A gate that fails on day one gets switched off on day two. Two ways in:

- `--min-score 70` fails on the composite score instead of the verdict. Raise
  it a notch at a time.
- `--write-baseline` records today's findings and `--baseline` suppresses them,
  so only *new* findings fail the build. Commit the baseline file.

Both compose with `--path src/` to start on one directory.

## Platform notes

**GitLab CI** — `image: {docker: {user: root}}` needs a recent GitLab; on older
runners set `user = "root"` in the runner's `config.toml`. `GIT_DEPTH: "0"`
because a shallow clone has no merge base for the diff scopes.

**CircleCI** — `user: root` on the docker executor image. Reports go to
`reports/`, which `store_test_results` and `store_artifacts` both read.

**Travis CI** — the odd one out: gandalf drives the scanner image itself, via
the Docker daemon Travis provides as a service.

**Azure DevOps** — `container:` runs every step inside the image;
`options: --user 0:0` because the image's uid cannot write to the workspace.

**AWS CodePipeline** — set the CodeBuild project's image to `gandalf-tools`
and leave privileged mode off; nothing here needs a daemon.

**Devtron** — a Container-image task with `gandalf-tools` beats a Shell task on
the CI node, where a missing tool silently becomes a WARN. Pre-Build gates the
build, Pre-Deployment gates the release.

**Northflank** — a manual job, run as a step in the environment's workflow. A
failed step stops the rest of the workflow. It clones the repository itself,
since a job has no checkout of its own.

**Spacelift** — `before_plan`, not `before_apply`: this reviews the code in the
repository, so it should fail before Spacelift spends a plan on it. checkov,
trivy, gitleaks and hadolint are the gates that earn their keep on an IaC stack.

**Jenkins** — `agent { docker { … } }` needs the Docker Pipeline plugin. `-u
root` for the same workspace-ownership reason as everywhere else.

**Bitbucket Pipelines** — `run-as-user: 0`, and reports go to `test-results/`,
which Bitbucket picks up without being told.

**Google Cloud Build** — steps already run as root and share `/workspace`.
`E2_HIGHCPU_8` because the scanners, not gandalf, are the slow part.

**Tekton** — the Task takes a `source` workspace (a `git-clone` Task's output)
and a `reports` workspace. `--min-score` is wired to a param so a Pipeline can
tighten the gate without editing the Task.

**Argo Workflows** — the DAG is the gate: `build` depends on `gandalf`, so a
red verdict leaves it unrun.

**Harness** — a `Run` step with `reports: {type: JUnit}`, so each gate lands in
the execution's Tests tab.

**Buildkite** — `$$VAR` for anything the shell must expand at run time, and a
`wait: ~` with `continue_on_failure: true` so the annotate step still runs when
the gates fail. Pin `junit-annotate` to whatever version is current for you.

**Drone / Woodpecker** — no way to set the container user, so reports go to
`/tmp` and `HOME` is set for the same reason.
