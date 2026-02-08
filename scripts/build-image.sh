#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

# Default to amd64; override with PLATFORMS=linux/amd64,linux/arm64
PLATFORMS="${PLATFORMS:-linux/amd64}"
IMAGE="${IMAGE:-hvr88/lidarr.metadata:dev}"
PUSH="${PUSH:-0}"

load_flag=(--load)
push_flag=()

if [[ "$PLATFORMS" == *","* ]]; then
  load_flag=()
  if [[ "$PUSH" != "1" ]]; then
    echo "Multi-arch build requires PUSH=1 (buildx cannot --load multi-arch)." >&2
    exit 1
  fi
  push_flag=(--push)
fi

docker buildx build \
  --platform "$PLATFORMS" \
  "${load_flag[@]}" \
  "${push_flag[@]}" \
  -f Dockerfile \
  -t "$IMAGE" \
  .
