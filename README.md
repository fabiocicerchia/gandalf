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

More in [`docs/getting-started.md`](docs/getting-started.md).

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
