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
[README](../README.md) for the full flag reference and configuration
(`.gandalf.toml`).
