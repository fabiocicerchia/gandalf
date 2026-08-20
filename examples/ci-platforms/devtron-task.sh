#!/bin/sh
# Devtron — run the gates before an image is built or a release deploys.
#
# Two ways to run this, and the container one is better:
#   - Task type "Container image": image ghcr.io/fabiocicerchia/gandalf-tools,
#     with this script as the command. Every gate finds its binary on PATH.
#   - Task type "Shell": this script on the CI node, where gates whose tool is
#     missing degrade to a yellow WARN rather than failing.
#
# Put it on Pre-Build to gate the build, or Pre-Deployment to gate the release.
# A non-zero exit fails the stage.
set -eu

GANDALF_VERSION="${GANDALF_VERSION:-v0.4.0}"
# No LLM endpoint in CI: don't spend 7s per judge gate retrying a connection
# that will not come up. Point GANDALF_LLM_URL at an OpenAI-compatible endpoint
# to get the summary and the judge gates back.
export GANDALF_LLM_RETRIES="${GANDALF_LLM_RETRIES:-0}"

git config --global --add safe.directory "*"
git clone --quiet --depth 1 --branch "$GANDALF_VERSION" \
  https://github.com/fabiocicerchia/gandalf /tmp/gandalf

# Exit code is 1 when the verdict is red, 0 otherwise. --min-score gates on the
# composite score instead, which is the gentler on-ramp for an existing repo:
# add --min-score 70 and drop it a notch at a time.
PYTHONPATH=/tmp/gandalf/src python3 -m gandalf \
  --no-llm --no-html --no-trend \
  --out-dir /tmp/gandalf-reports \
  --junit /tmp/gandalf-reports/gandalf.junit.xml
