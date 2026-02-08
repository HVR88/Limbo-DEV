#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

# BuildKit workaround if your Docker Desktop buildx is busted:
#   DOCKER_BUILDKIT=0 docker build ...
# Otherwise remove DOCKER_BUILDKIT=0 once buildx is fixed.
DOCKER_BUILDKIT=0 docker build \
  -f Dockerfile \
  -t hvr88/lidarr.metadata:dev \
  .
