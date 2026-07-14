.PHONY: help setup lint test analyze install tools

BINDIR ?= $(HOME)/.local/bin

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	  awk 'BEGIN {FS = ":.*?## "}; {printf "  %-10s %s\n", $$1, $$2}'

setup: ## Install git hooks and dev tooling
	git config core.hooksPath .githooks
	@command -v pre-commit >/dev/null 2>&1 && pre-commit install || true

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
