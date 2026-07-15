#!/usr/bin/env bash
set -euo pipefail
# One-line installer for gandalf
# Usage: curl -fsSL https://raw.githubusercontent.com/fabiocicerchia/gandalf/main/install.sh | bash
#
# gandalf is stdlib-only and runs from its own checkout (PYTHONPATH=src), so
# "installing" it means keeping a persistent clone and dropping the `make
# install` wrapper on PATH — see README for the equivalent manual steps.

REPO_DIR="${GANDALF_HOME:-$HOME/.local/share/gandalf}"

if [ -d "$REPO_DIR/.git" ]; then
  git -C "$REPO_DIR" pull --ff-only
else
  git clone --depth 1 https://github.com/fabiocicerchia/gandalf "$REPO_DIR"
fi

make -C "$REPO_DIR" install
echo "gandalf installed. Run 'gandalf' inside any git repo."
