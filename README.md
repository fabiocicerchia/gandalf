# 🧙 Gandalf — codebase quality-gate evaluator

> **"You shall not pass!"**

[![code-quality](https://github.com/fabiocicerchia/gandalf/actions/workflows/code-quality.yml/badge.svg)](https://github.com/fabiocicerchia/gandalf/actions/workflows/code-quality.yml)
[![security](https://github.com/fabiocicerchia/gandalf/actions/workflows/security.yml/badge.svg)](https://github.com/fabiocicerchia/gandalf/actions/workflows/security.yml)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![OpenSSF Scorecard](https://api.securityscorecards.dev/projects/github.com/fabiocicerchia/gandalf/badge)](https://securityscorecards.dev/viewer/?uri=github.com/fabiocicerchia/gandalf)
[![CI carbon](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/fabiocicerchia/gandalf/gh-pages/badge.json)](.github/workflows/carbon-badge.yml)
[![Release](https://img.shields.io/github/v/release/fabiocicerchia/gandalf)](https://github.com/fabiocicerchia/gandalf/releases)

Evaluate the codebase as-is, get an LLM summary and a Red/Amber/Green
traffic-light scorecard from pluggable gates. Stdlib-only, no dependencies.

> **0.x, and gandalf runs other people's tools.** It is stdlib-only itself and
> installs nothing: a gate whose scanner is neither on your `PATH` nor in the
> `gandalf-tools` image reports that it could not run, rather than failing or
> pretending to pass. Such gates are not scored — "we could not check this" is
> not a quality signal — and a first run on a bare machine prints a setup
> banner pointing at `make tools`. The LLM summary is optional (`--no-llm`)
> and never gates anything on its own.

```bash
PYTHONPATH=src python -m gandalf                 # whole working tree, as-is (default)
PYTHONPATH=src python -m gandalf --staged        # staged changes only
PYTHONPATH=src python -m gandalf --commit <sha>  # a specific commit (in a throwaway git worktree)
PYTHONPATH=src python -m gandalf --path <dir>    # limit scanning to a folder
```

The package lives under `src/`, so put `src` on `PYTHONPATH` (the wrapper below does this for you).

Or `make analyze`. Exit code is `1` when the verdict is red, `0` otherwise — CI-usable.

## How it works

One pass over a scope, every gate against the same file set:

```
  gandalf [--staged | --commit <sha> | --path <dir>]
      │
  scope ──────────────────► working tree, the index, or a commit checked out
      │                      into a THROWAWAY worktree (removed on exit, so an
      │                      interrupted run leaves your repo alone)
      │
  classify ───────────────► the languages present decide which gates apply;
      │                      a Python-only change never waits on the Go toolchain
      │
  discover ───────────────► every .py in gates/ exporting a Gate, plus anything
      │                      on GANDALF_GATES_PATH
      │
      ▼  concurrently, bounded by --concurrency
  ┌─ gate ─────────────────────────────────────────────────┐
  │  cache hit on the scope's content hash?  → reuse       │
  │  tool on PATH?               → run it                  │
  │  tool in the gandalf-tools image?  → run it there      │
  │  neither                     → not run, and say which  │
  └────────────────────────────────────────────────────────┘
      │
  suppress ───────────────► .gandalf.toml rules + baseline; findings are marked,
      │                      never deleted, so the suppressed count stays visible
      │
  policy ─────────────────► blocking gates decide the colour, every gate feeds
      │                      the 0-100 score  (--fail-on, --min-score)
      ▼
  RED · 81/100
      │
      ├─ terminal scorecard        ├─ SARIF   → GitHub code scanning
      ├─ HTML report (one file)    ├─ JUnit   → any CI's test panel
      ├─ JSON / NDJSON stream      ├─ badge   → shields.io endpoint
      └─ trend line, appended      └─ PR review comments, file:line
```

Gates are the extension point and the policy is not inside them: a gate reports
an outcome and a score, and what turns that into a verdict lives in one place.

More in [`docs/architecture.md`](docs/architecture.md).

## What it does

- **Runs ~60 gates** across security, dependencies, code quality, complexity,
  documentation, build & tests, best practices and architecture. Caveat: most
  wrap a third-party scanner, so what actually runs depends on what is
  installed — see the status note above.
- **Speaks nine ecosystems.** Python, Go, Rust, Node/TypeScript, Java/Kotlin,
  Ruby, PHP, C/C++ and .NET each get build, lint, dependency-audit and test
  gates wired to that ecosystem's standard tooling — and only the ones matching
  the languages in scope run.
- **Never scores what it could not check.** A gate whose tool is missing, that
  timed out, or that had nothing in scope is reported as not run, with the
  reason in the line — and left out of the composite and the verdict, so a
  missing scanner neither drags a clean repo down nor props a bad one up. When
  most gates land there, the run says so and points at the setup step.
- **Evaluates a scope, not a file.** Working tree, the index, or a commit —
  and a commit is checked out into a throwaway worktree, so the run cannot
  disturb what you are working on.
- **Caches on content.** One hash over the scope's files skips gates whose
  input has not changed. Caveat: the hash covers file contents only, so a tool
  upgrade or a newly published CVE does not invalidate a hit.
- **Suppresses without hiding.** Rules and a baseline mark findings; the count
  of what was suppressed stays in the report.
- **Emits what other tools already read** — SARIF for code scanning, JUnit for
  a CI test panel, a shields.io endpoint badge, PR review comments anchored at
  `file:line`, NDJSON while the run is still going.
- **Fixes what can be fixed.** `--fix` cascades to the tools themselves (ruff,
  ruff format, eslint, golangci-lint, clippy, rubocop, ktlint, phpcbf,
  dotnet format, sqlfluff, codespell, shellcheck),
  so the scorecard reflects the fixed tree and what is left is what needs a
  person. On a pull request the same fixes arrive as GitHub `suggestion`
  blocks — one click to commit, no retyping.
- **Zero host installs, optionally.** `make tools` builds one image holding
  every scanner; gates find it automatically. Caveat: it is built, never
  pulled — a quality gate should not reach the network on its own initiative.

## Install a `gandalf` command

```bash
make install                       # drops a wrapper in ~/.local/bin (on your PATH)
make install BINDIR=/usr/local/bin # …or anywhere else
```

Or the one-line installer (clones/updates a checkout under
`~/.local/share/gandalf` and runs `make install`):

```bash
curl -fsSL https://raw.githubusercontent.com/fabiocicerchia/gandalf/main/install.sh | bash
```

Pure-stdlib, so the "install" is just a one-line wrapper that runs this checkout
(`python -m gandalf`) against whatever repo you're in. Equivalent one-liner:

```bash
printf '#!/bin/sh\nexport PYTHONPATH="%s/src:$PYTHONPATH"\nexec python3 -m gandalf "$@"\n' "$PWD" > ~/.local/bin/gandalf && chmod +x ~/.local/bin/gandalf
```

### `.gandalfignore` — paths no gate should read

Add a `.gandalfignore` at the repo root (gitignore-style: one glob per line, `#`
comments) to keep vendored, generated and local-state paths out of every scan —
a `.env`, a `data/` dir, `src/generated`. Built-in defaults (`reports`,
`node_modules`, `llama.cpp`, `.venv`, `.git`) always apply.

A bare name skips that directory wherever it appears (`node_modules`), a path
anchors at the repository root (`src/generated`), and globs work (`*.min.js`).
`--exclude <glob>` (repeatable) and `[gandalf] exclude = [...]` add to the same
list without writing a file into the repository — which is how the VS Code
extension passes on the folders you already excluded from the editor.

## Usage

```sh
PYTHONPATH=src python -m gandalf                 # whole working tree (default)
PYTHONPATH=src python -m gandalf --staged        # staged changes only
PYTHONPATH=src python -m gandalf --commit <sha>  # a specific commit
PYTHONPATH=src python -m gandalf --path subdir/  # limit scanning to a folder
```

The flag reference is long; `--help` is the authoritative copy. Its opening:

```console
$ gandalf --help
usage: gandalf [-h] [--commit SHA | --staged] [--path DIR] [--no-html]
               [--out-dir DIR] [--no-trend] [--sarif [PATH]] [--junit [PATH]]
               [--badge [PATH]] [--pr-comments [PATH]] [--pr N]
               [--pr-repo OWNER/REPO] [--json] [--stream] [--no-llm] [--debug]
               [--fix] [--target TARGET] [--allow-remote] [--title TITLE]
               [--body BODY] [--config PATH] [--exclude GLOB]
               [--fail-on {fail,warn}] [--min-score N] [--concurrency N]
               [--severity-weight] [--baseline PATH] [--write-baseline [PATH]]
               [--cache [PATH]]

gandalf CLI — evaluate the codebase, run pluggable gates, show RAG traffic lights.

    python -m gandalf                 # whole working tree, as-is
    python -m gandalf --staged        # staged changes only
    python -m gandalf --commit <sha>  # a specific commit (in a throwaway worktree)
    python -m gandalf --path <dir>    # limit scanning to a folder

Exit code is non-zero when the overall verdict is red, so it's CI-usable.
...
```

A real run against this repo, on a machine with neither the scanner image nor
the host binaries — which is exactly the case the amber lines describe:

```console
$ gandalf --no-llm
🧙  GANDALF — working-tree
commit 447b5d1 — docs(cli): stop --help reflowing the usage examples into a paragraph
generated 2026-08-19 07:32:16 UTC

  RED · 81/100

Security · 80%
  🟡 bandit                 bandit unavailable (no host binary or gandalf-tools image) — skipped
  🟡 gitleaks               gitleaks unavailable (no host binary or gandalf-tools image) — skipped [blocking]
  🟡 semgrep                semgrep unavailable (no host binary or gandalf-tools image) — skipped
...
Code quality · 92%
  🟢 ruff                   ruff clean
  🟢 tsc                    tsc: no tsconfig.json
...
Build & tests · 62%
  🟢 build                  66 file(s) compile [blocking]
  🟡 ci_act                 'act' not found; CI not verified locally
  🔴 tests                  tests: ? failure(s) — /usr/local/bin/python: No module named pytest

Languages: node, python, shell, ts, yaml  ·  skipped 11 irrelevant gate(s): cargo_audit, …
```

Every amber line names its own cause, which is the point: `make tools` turns
most of that page green, and nothing above was silently skipped.

More in [`docs/getting-started.md`](docs/getting-started.md).

## Configuration

`.gandalf.toml` at the repo root, version-controlled so it reviews with the
code. Simple and not comprehensive — the full reference, and the environment
variables that override it, are in
[`docs/configuration.md`](docs/configuration.md):

```toml
[gandalf]
skip        = ["atheris"]                    # never run these
concurrency = 8                              # ~60 gates each able to spawn a
                                             # docker run: bound them
exclude     = ["src/generated", "*.min.js"]  # paths no gate should read

[gandalf.verdict]
fail_on   = "fail"   # "fail" (default) | "warn" — lowest outcome that reddens
min_score = 70       # 0-100; red below this composite score

[gandalf.timeouts]
default = 120        # per-gate subprocess timeout (seconds)
semgrep = 300        # ...overridden per gate

[gandalf.suppress]
rules = ["gitleaks:generic-api-key"]
```

Precedence is environment variable → config file → built-in default: the file
is the repo's decision, and the environment is CI's override of it.

## Editor integration

A VS Code extension lives in [`extensions/vscode/`](extensions/vscode/): findings as
inline diagnostics, a bottom pane filtered to the current file or the whole
project, and the same HTML scorecard in an editor tab. It scans the saved file
on save and the whole tree on demand, so it stays off your CPU.

Install it from the
[VS Marketplace](https://marketplace.visualstudio.com/items?itemName=fabiocicerchia.gandalf-quality-gates)
or from [Open VSX](https://open-vsx.org/extension/fabiocicerchia/gandalf-quality-gates)
for the forks:

```bash
code --install-extension fabiocicerchia.gandalf-quality-gates
make ext-install                   # ...or build the .vsix from this checkout
make ext-install CODE=cursor       # ...into a fork
```

More in [docs/editors.md](docs/editors.md).

## Documentation

Full docs live in [`docs/`](docs/) (mkdocs). Runnable examples live in
[`examples/`](examples/).

## Common errors

**`<gate> unavailable (no host binary or gandalf-tools image) — skipped`**
Not a failure. The gate wraps a scanner that is not installed, so it reports
amber and names the reason. `make tools` builds the image that holds all of
them; installing the binary on the host works too.

**`RED` with everything amber.**
A blocking gate that could not run still colours the verdict, because "we did
not check" is not "it passed". `--fail-on warn` makes that stricter,
`.gandalf.toml`'s `skip` makes it quieter — deliberately, and in the repository
where it can be reviewed.

**`skill judge unavailable (<urlopen error [Errno 111] Connection refused>)`**
The LLM-backed gates and the summary talk to an OpenAI-compatible endpoint at
`GANDALF_LLM_URL`. With nothing listening they degrade to amber and the run
continues; `--no-llm` skips them outright.

**`No module named gandalf`**
The package lives under `src/`, so it needs `PYTHONPATH=src` — or `make
install`, which drops a wrapper that sets it for you.

**A gate reads a file it should not.**
`.gandalfignore` at the repo root, `exclude` in `.gandalf.toml`, or a
repeatable `--exclude <glob>`. All three feed one list: a bare name skips that
directory anywhere, a path anchors at the repository root, and globs work.

## References

- [SARIF 2.1.0](https://docs.oasis-open.org/sarif/sarif/v2.1.0/sarif-v2.1.0.html)
  and [GitHub code scanning](https://docs.github.com/en/code-security/code-scanning/integrating-with-code-scanning/uploading-a-sarif-file-to-github)
  — the format that turns findings into annotations rather than log lines.
- [shields.io endpoint badge](https://shields.io/badges/endpoint-badge) — the
  JSON schema `--badge` writes, so gandalf never renders pixels itself.
- [JUnit XML](https://github.com/testmoapp/junitxml) — why the results are
  shaped as a test suite: every CI already knows how to display one.
- [OpenSSF Scorecard](https://github.com/ossf/scorecard),
  [Semgrep](https://semgrep.dev/docs/), [gitleaks](https://github.com/gitleaks/gitleaks),
  [CodeQL](https://codeql.github.com/docs/) — a sample of what the gates wrap;
  each gate file names its own.
- [Conventional Commits](https://www.conventionalcommits.org/) — what the PR
  gates read, and what release-please cuts releases from.

## Release cycle

[Semantic Versioning](https://semver.org/), cut by release-please from
[Conventional Commits](https://www.conventionalcommits.org/).

- **Major** — a change to the gate contract in `base.py`, the JSON report
  shape, or the exit codes.
- **Minor** — new gates, new flags, new report formats. A new gate can turn a
  green run amber the first time it runs, which is why it degrades rather than
  fails when its tool is missing.
- **Patch** — fixes, including a gate that was scoring the wrong thing.

The gate contract is kept byte-compatible with the sibling project's, so a gate
written for either drops into the other. That compatibility is a major-version
promise, not a convenience.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). By participating you agree to the
[Code of Conduct](CODE_OF_CONDUCT.md).

## Security

Found a vulnerability? See [SECURITY.md](SECURITY.md) — please don't open a
public issue.

## Support

Need help implementing this? [Get in touch](https://fabiocicerchia.it/contact).

## License

[Apache-2.0](LICENSE) © Fabio Cicerchia
