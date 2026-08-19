# gandalf — codebase quality-gate evaluator.
#
# Every verb this repo exposes lives here; `make` on its own prints them,
# grouped, straight out of the `##` comments below.

BINDIR ?= $(HOME)/.local/bin
EXT_DIR ?= extensions/vscode
# Read rather than hard-coded: vsce names the VSIX after the version in the
# manifest, so a release bump must not turn ext-publish into "file not found".
EXT_VERSION := $(shell node -p "require('./$(EXT_DIR)/package.json').version" 2>/dev/null)
VSIX := $(EXT_DIR)/gandalf-quality-gates-$(EXT_VERSION).vsix
# The editor's CLI. Override for a fork: make ext-install CODE=cursor
CODE ?= code

.DEFAULT_GOAL := help
# help is pure output; the recipe echo would only be noise.
.SILENT: help

##@ General

.PHONY: help
help: ## Show this help
	awk 'BEGIN {FS = ":.*## "} \
	  /^##@/ { printf "\n\033[1m%s\033[0m\n", substr($$0, 5) } \
	  /^[a-zA-Z_0-9-]+:.*## / { printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2 }' \
	  $(MAKEFILE_LIST)

.PHONY: setup
setup: ## Install the pre-commit hook
	pre-commit install

##@ Run

.PHONY: analyze
analyze: ## Run gandalf against this repo
	PYTHONPATH=src python3 -m gandalf

.PHONY: install
install: ## Drop a `gandalf` wrapper in BINDIR (default ~/.local/bin)
	@mkdir -p "$(BINDIR)"
	@printf '#!/bin/sh\nexport PYTHONPATH="%s/src:$$PYTHONPATH"\nexec python3 -m gandalf "$$@"\n' "$(CURDIR)" > "$(BINDIR)/gandalf"
	@chmod +x "$(BINDIR)/gandalf"
	@echo "installed $(BINDIR)/gandalf"

# Every scanner a gate can shell out to, in one image. A gate whose binary is
# neither on PATH nor in this image degrades to WARN rather than failing, so
# this is what turns a partial run into a complete one with zero host installs.
.PHONY: tools
tools: ## Build the scanner-tools image (zero host installs)
	docker build -f tools.Dockerfile -t gandalf-tools .

##@ Quality

.PHONY: lint
lint: ## Run all pre-commit checks on the whole tree
	pre-commit run --all-files

.PHONY: test
test: ## Run the test suite
	pytest

##@ VS Code extension

# The same four extension verbs, with the same meanings, in gandalf, greenlint
# and depwatch: build compiles, package writes the .vsix, install side-loads it,
# publish pushes it to both marketplaces.
.PHONY: ext-build
ext-build: ## Compile the VS Code extension
	@command -v npm >/dev/null 2>&1 || { echo "npm not found — Node 18+ is needed to build the extension"; exit 1; }
	@cd "$(EXT_DIR)" && { [ -d node_modules ] || npm install; } && npm run typecheck && npm run build

.PHONY: ext-package
ext-package: ext-build ## Build the VS Code extension into a .vsix
	@cd "$(EXT_DIR)" && npm run package

.PHONY: ext-install
ext-install: ext-package ## Build the VS Code extension and install it (override with CODE=)
	@command -v "$(CODE)" >/dev/null 2>&1 || { \
	  echo "'$(CODE)' CLI not found. Run \"Shell Command: Install '$(CODE)' command in PATH\""; \
	  echo "from the Command Palette, or install $(EXT_DIR)/*.vsix by hand:"; \
	  echo "  Extensions view -> ... -> Install from VSIX..."; \
	  exit 1; }
	@vsix=$$(ls -t "$(EXT_DIR)"/*.vsix | head -1) && "$(CODE)" --install-extension "$$vsix" --force
	@echo "installed — reload the window (Developer: Reload Window)"

# Normally CI's business: publishing happens in publish-extension.yml, called by
# release.yml when release-please cuts a release. This is the manual escape
# hatch, and it needs VSCE_PAT and OVSX_PAT in the environment.
.PHONY: ext-publish
ext-publish: ext-package ## Publish the .vsix to both marketplaces
	@cd "$(EXT_DIR)" && npm run publish -- --packagePath "$(notdir $(VSIX))"
	@cd "$(EXT_DIR)" && npx --yes ovsx@1.1.1 publish "$(notdir $(VSIX))" -p "$$OVSX_PAT"
