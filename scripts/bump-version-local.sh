#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION_ARG="${1:-}"

usage() {
  cat <<'EOF'
Usage: bump-version-local.sh [version]

If no version is provided, bumps the patch version from VERSION.
If version is provided, it must be x.y.z or x.y.z.bb.

Examples:
  scripts/bump-version-local.sh
  scripts/bump-version-local.sh 1.9.6.50
EOF
}

case "${VERSION_ARG:-}" in
  --help|-h)
    usage
    exit 0
    ;;
esac

if [[ $# -gt 1 ]]; then
  echo "Too many arguments." >&2
  usage >&2
  exit 2
fi

cd "$ROOT_DIR"

export INPUT_VERSION="$VERSION_ARG"

python3 - <<'PY'
import re
import os
from pathlib import Path

version_path = Path("VERSION")
version_input = os.environ.get("INPUT_VERSION", "").strip()

def _clean(raw: str) -> str:
    raw = "".join(raw.split())
    if raw.startswith("v"):
        raw = raw[1:]
    return raw

if not version_path.exists():
    raise SystemExit("VERSION file not found.")

if version_input:
    version_input = _clean(version_input)
    if not re.fullmatch(r"\d+\.\d+\.\d+(?:\.\d{1,3})?", version_input):
        raise SystemExit(
            f"Invalid version override (use x.y.z or x.y.z.bb): {version_input!r}"
        )
    new_version = version_input
else:
    version = _clean(version_path.read_text())
    m3 = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", version)
    m4 = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)\.(\d{1,3})", version)
    if not m3 and not m4:
        raise SystemExit(f"VERSION format invalid: {version!r}")
    if m3:
        major, minor, patch = map(int, m3.groups())
        patch += 1
        new_version = f"{major}.{minor}.{patch}"
    else:
        major, minor, patch, _build = map(int, m4.groups())
        patch += 1
        new_version = f"{major}.{minor}.{patch}.00"

version_path.write_text(new_version + "\n")
Path("deploy/VERSION").write_text(new_version + "\n")

csproj_path = Path("lm-bridge-plugin/plugin/LMBridgePlugin.csproj")
text = csproj_path.read_text()
text, count1 = re.subn(
    r"<AssemblyVersion>[^<]+</AssemblyVersion>",
    f"<AssemblyVersion>{new_version}</AssemblyVersion>",
    text,
    count=1,
)
text, count2 = re.subn(
    r"<Version>[^<]+</Version>",
    f"<Version>{new_version}</Version>",
    text,
    count=1,
)
if count1 != 1 or count2 != 1:
    raise SystemExit("Failed to update LMBridgePlugin.csproj version fields.")
csproj_path.write_text(text)

readme_path = Path("deploy/README.md")
if readme_path.exists():
    readme_text = readme_path.read_text()
    readme_text, count = re.subn(
        r"Deploy version: `[^`]+`",
        f"Deploy version: `{new_version}`",
        readme_text,
        count=1,
    )
    if count == 1:
        readme_path.write_text(readme_text)

print(new_version)
PY
