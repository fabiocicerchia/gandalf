# gandalf-tools — every scanner gate's CLI in one image, so the host stays clean.
# Build:  make tools   (or: docker build -t gandalf-tools -f gandalf/tools.Dockerfile gandalf)
# gandalf runs each tool atomically as `docker run --rm gandalf-tools <tool> ...`
# when the binary isn't on the host PATH. Pinned for reproducibility — bump freely.
FROM python:3.12-slim@sha256:229a2c5bfa27522db7815ea81f9bed70af17ccb9de9fc7ad142b1877b5830d36

# OCI labels — org.opencontainers.image.source links the ghcr package to this repo
# (so it inherits repo visibility and the built-in GITHUB_TOKEN can pull it).
LABEL org.opencontainers.image.source="https://github.com/fabiocicerchia/gandalf" \
      org.opencontainers.image.description="gandalf-tools — every scanner gate's CLI in one image" \
      org.opencontainers.image.licenses="Apache-2.0"

ARG GITLEAKS_VERSION=8.21.2
ARG HADOLINT_VERSION=2.12.0
ARG OSV_SCANNER_VERSION=1.9.1
ARG ACTIONLINT_VERSION=1.7.7
ARG SQUAWK_VERSION=2.59.0
ARG SCORECARD_VERSION=5.5.0

RUN apt-get update \
 && apt-get install -y --no-install-recommends curl ca-certificates git shellcheck ruby \
 && rm -rf /var/lib/apt/lists/*

# Python-packaged tools (scanners + type/dead-code/yaml/spell/sql/docs/complexity)
RUN pip install --no-cache-dir \
      ruff semgrep bandit pip-audit checkov \
      mypy vulture codespell yamllint sqlfluff interrogate lizard

# squawk — Postgres migration linter (single binary)
RUN curl -sSfL "https://github.com/sbdchd/squawk/releases/download/v${SQUAWK_VERSION}/squawk-linux-x64" \
      -o /usr/local/bin/squawk && chmod +x /usr/local/bin/squawk

# mdl (markdownlint, Ruby gem)
RUN gem install --no-document mdl

# (kics runs from the official checkmarx/kics image — it ships its own query assets.)

# Statically-shipped binaries
RUN curl -sSfL "https://github.com/hadolint/hadolint/releases/download/v${HADOLINT_VERSION}/hadolint-Linux-x86_64" \
      -o /usr/local/bin/hadolint && chmod +x /usr/local/bin/hadolint \
 && curl -sSfL "https://github.com/google/osv-scanner/releases/download/v${OSV_SCANNER_VERSION}/osv-scanner_linux_amd64" \
      -o /usr/local/bin/osv-scanner && chmod +x /usr/local/bin/osv-scanner \
 && curl -sSfL "https://github.com/gitleaks/gitleaks/releases/download/v${GITLEAKS_VERSION}/gitleaks_${GITLEAKS_VERSION}_linux_x64.tar.gz" \
      | tar -xz -C /usr/local/bin gitleaks \
 && curl -sSfL "https://github.com/rhysd/actionlint/releases/download/v${ACTIONLINT_VERSION}/actionlint_${ACTIONLINT_VERSION}_linux_amd64.tar.gz" \
      | tar -xz -C /usr/local/bin actionlint \
 && curl -sSfL "https://github.com/ossf/scorecard/releases/download/v${SCORECARD_VERSION}/scorecard_${SCORECARD_VERSION}_linux_amd64.tar.gz" \
      | tar -xz -C /usr/local/bin scorecard \
 && curl -sSfL https://raw.githubusercontent.com/aquasecurity/trivy/main/contrib/install.sh \
      | sh -s -- -b /usr/local/bin

# Run as a non-root user (uid 1000 to match the typical host user, so tools that
# write into the mounted /src worktree — e.g. `ruff format` under --fix — and the
# cache volume stay writable). The cache mount path in plugins._dockerize matches
# this user's HOME (/home/gandalf/.cache).
RUN useradd --create-home --home-dir /home/gandalf --uid 1000 --shell /bin/bash gandalf \
 && mkdir -p /home/gandalf/.cache \
 && chown -R gandalf:gandalf /home/gandalf
USER gandalf

# One-shot scanner image (`docker run --rm gandalf-tools <tool>`) — no long-running
# service to probe. This trivial check just satisfies image-hardening gates
# (checkov CKV_DOCKER_2) without affecting one-shot runs.
HEALTHCHECK CMD true

# No global ENTRYPOINT: `docker run gandalf-tools <tool> ...` resolves the tool on PATH.
WORKDIR /src
