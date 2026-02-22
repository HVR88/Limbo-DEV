#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEPLOY_DIR="${ROOT}/deploy"
OUT_DIR="${OUT_DIR:-${ROOT}/dist}"
DEPLOY_REPO="${DEPLOY_REPO:-}"
DEPLOY_DELETE="${DEPLOY_DELETE:-0}"

if [[ ! -d "${DEPLOY_DIR}" ]]; then
  echo "deploy/ folder not found at ${DEPLOY_DIR}" >&2
  exit 1
fi

mkdir -p "${OUT_DIR}"
timestamp="$(date +%Y%m%d%H%M%S)"
archive="${OUT_DIR}/limbo-deploy-${timestamp}.tar.gz"

stage="$(mktemp -d)"
trap 'rm -rf "${stage}"' EXIT

rsync -a \
  --exclude=".env" \
  --exclude=".env.*" \
  --exclude=".DS_Store" \
  "${DEPLOY_DIR}/" "${stage}/"

mkdir -p "${stage}/License"
if [[ -f "${ROOT}/LICENSE" ]]; then
  cp "${ROOT}/LICENSE" "${stage}/License/"
fi
if [[ -f "${ROOT}/THIRD_PARTY_NOTICES.md" ]]; then
  cp "${ROOT}/THIRD_PARTY_NOTICES.md" "${stage}/License/"
fi

tar -czf "${archive}" -C "${stage}" .
echo "Wrote ${archive}"

if [[ -n "${DEPLOY_REPO}" ]]; then
  if [[ ! -d "${DEPLOY_REPO}" ]]; then
    echo "DEPLOY_REPO does not exist: ${DEPLOY_REPO}" >&2
    exit 1
  fi
  rsync_flags=(-a)
  if [[ "${DEPLOY_DELETE}" == "1" ]]; then
    rsync_flags+=("--delete")
  fi
  rsync "${rsync_flags[@]}" \
    --exclude=".env" \
    --exclude=".env.*" \
    --exclude=".DS_Store" \
    --exclude=".git" \
    "${stage}/" "${DEPLOY_REPO}/"
  echo "Synced deploy/ to ${DEPLOY_REPO}"
fi
