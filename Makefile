.PHONY: help setup lint test analyze install tools ext-package ext-install ext-publish

BINDIR ?= $(HOME)/.local/bin
EXT_DIR ?= editors/vscode
# The editor's CLI. Override for a fork: make ext-install CODE=cursor
CODE ?= code

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	  awk 'BEGIN {FS = ":.*?## "}; {printf "  %-12s %s\n", $$1, $$2}'

setup: ## Install the pre-commit hook
	pre-commit install

lint: ## Run all pre-commit checks on the whole tree
	pre-commit run --all-files

test: ## Run the test suite
	pytest

analyze: ## Run gandalf against this repo
	PYTHONPATH=src python3 -m gandalf

install: ## Drop a `gandalf` wrapper in BINDIR (default ~/.local/bin)
	@mkdir -p "$(BINDIR)"
	@printf '#!/bin/sh\nexport PYTHONPATH="%s/src:$$PYTHONPATH"\nexec python3 -m gandalf "$$@"\n' "$(CURDIR)" > "$(BINDIR)/gandalf"
	@chmod +x "$(BINDIR)/gandalf"
	@echo "installed $(BINDIR)/gandalf"

tools: ## Build the scanner-tools image (zero host installs)
	docker build -f tools.Dockerfile -t gandalf-tools .

ext-package: ## Build the VS Code extension into a .vsix
	@command -v npm >/dev/null 2>&1 || { echo "npm not found — Node 18+ is needed to build the extension"; exit 1; }
	@cd "$(EXT_DIR)" && { [ -d node_modules ] || npm install; } && npm run package

ext-install: ext-package ## Build the VS Code extension and install it (override with CODE=)
	@command -v "$(CODE)" >/dev/null 2>&1 || { \
	  echo "'$(CODE)' CLI not found. Run \"Shell Command: Install '$(CODE)' command in PATH\""; \
	  echo "from the Command Palette, or install $(EXT_DIR)/*.vsix by hand:"; \
	  echo "  Extensions view -> ... -> Install from VSIX..."; \
	  exit 1; }
	@vsix=$$(ls -t "$(EXT_DIR)"/*.vsix | head -1) && "$(CODE)" --install-extension "$$vsix" --force
	@echo "installed — reload the window (Developer: Reload Window)"

# Normally CI's business: publishing happens in publish-extension.yml when a
# release is published. This is the manual escape hatch, and it needs VSCE_PAT
# in the environment (or `vsce login fabiocicerchia` once).
ext-publish: ## Publish the VS Code extension to the Marketplace
	@cd "$(EXT_DIR)" && { [ -d node_modules ] || npm install; } && npm run publish
