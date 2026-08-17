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

```bash
PYTHONPATH=src python -m gandalf                 # whole working tree, as-is (default)
PYTHONPATH=src python -m gandalf --staged        # staged changes only
PYTHONPATH=src python -m gandalf --commit <sha>  # a specific commit (in a throwaway git worktree)
PYTHONPATH=src python -m gandalf --path <dir>    # limit scanning to a folder
```

The package lives under `src/`, so put `src` on `PYTHONPATH` (the wrapper below does this for you).

Or `make analyze`. Exit code is `1` when the verdict is red, `0` otherwise — CI-usable.

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

### `.gandalfignore` — skip paths in tree-scanning gates

The container/dependency gates (`trivy`, `checkov`, `kics`) scan the whole tree.
Add a `.gandalfignore` at the repo root (gitignore-style: one glob per line, `#`
comments) to skip local secrets/state that aren't committed — e.g. a `.env` or a
`data/` dir — so they aren't reported as false-positive leaks. Built-in defaults
(`reports`, `node_modules`, `llama.cpp`, `.venv`, `.git`) always apply.

## Usage

```sh
PYTHONPATH=src python -m gandalf                 # whole working tree (default)
PYTHONPATH=src python -m gandalf --staged        # staged changes only
PYTHONPATH=src python -m gandalf --commit <sha>  # a specific commit
PYTHONPATH=src python -m gandalf --path subdir/  # limit scanning to a folder
```

More in [`docs/getting-started.md`](docs/getting-started.md).

## Editor integration

A VS Code extension lives in [`editors/vscode/`](editors/vscode/): findings as
inline diagnostics, a bottom pane filtered to the current file or the whole
project, and the same HTML scorecard in an editor tab. It scans the saved file
on save and the whole tree on demand, so it stays off your CPU.

```bash
make ext-install                   # build the .vsix and install it into VS Code
make ext-install CODE=cursor       # ...or into a fork
```

More in [docs/editors.md](docs/editors.md).

## Documentation

Full docs live in [`docs/`](docs/) (mkdocs). Runnable examples live in
[`examples/`](examples/).

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
