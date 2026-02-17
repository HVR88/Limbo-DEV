#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJ="$ROOT/plugin/LMBridgePlugin.csproj"
OUT_DIR="$ROOT/plugin/bin/Release/net8.0"
DIST_DIR="$ROOT/dist"

DOTNET_BIN="dotnet"
if [[ -x "$HOME/.dotnet/dotnet" ]]; then
  DOTNET_BIN="$HOME/.dotnet/dotnet"
  export DOTNET_ROOT="$HOME/.dotnet"
  export PATH="$HOME/.dotnet:$PATH"
fi

if [[ ! -f "$PROJ" ]]; then
  echo "Missing project: $PROJ" >&2
  exit 1
fi

# PluginInfo.cs is generated at build time via PluginInfo.targets; remove any stale copy
rm -f "$ROOT/plugin/PluginInfo.cs"

if [[ ! -d "$ROOT/Submodules/Lidarr/src" ]]; then
  echo "Missing Lidarr submodule. Expected: $ROOT/Submodules/Lidarr" >&2
  exit 1
fi

if [[ -n "${VERSION_OVERRIDE:-}" ]]; then
  if [[ ! "$VERSION_OVERRIDE" =~ ^[0-9]+(\.[0-9]+){2,3}$ ]]; then
    echo "Invalid VERSION_OVERRIDE: $VERSION_OVERRIDE (expected x.y.z or x.y.z.w)" >&2
    exit 1
  fi
  VERSION="$VERSION_OVERRIDE"
  ASSEMBLY_VERSION="$VERSION_OVERRIDE"
else
  CURRENT_VERSION=$(grep -m1 "<Version>" "$PROJ" | sed -E "s/.*<Version>([^<]+).*/\\1/")
  if [[ -z "$CURRENT_VERSION" ]]; then
    CURRENT_VERSION="1.0.0.0"
  fi

  IFS='.' read -r MAJOR MINOR PATCH REV <<< "$CURRENT_VERSION"
  if [[ -z "${MAJOR:-}" || -z "${MINOR:-}" || -z "${PATCH:-}" ]]; then
    echo "Invalid version format in $PROJ: $CURRENT_VERSION" >&2
    exit 1
  fi
  if [[ -z "${REV:-}" ]]; then
    REV=0
  fi

  # Normalize to 4-part version with bounds: MAJOR.*.*.*, MINOR/PATCH 0-9, REV 0-99
  if (( REV > 99 )); then
    carry=$((REV / 100))
    REV=$((REV % 100))
    PATCH=$((PATCH + carry))
  fi
  if (( PATCH > 9 )); then
    carry=$((PATCH / 10))
    PATCH=$((PATCH % 10))
    MINOR=$((MINOR + carry))
  fi
  if (( MINOR > 9 )); then
    carry=$((MINOR / 10))
    MINOR=$((MINOR % 10))
    MAJOR=$((MAJOR + carry))
  fi

  if (( REV < 99 )); then
    REV=$((REV + 1))
  else
    REV=0
    PATCH=$((PATCH + 1))
    if (( PATCH > 9 )); then
      PATCH=0
      MINOR=$((MINOR + 1))
      if (( MINOR > 9 )); then
        MINOR=0
        MAJOR=$((MAJOR + 1))
      fi
    fi
  fi

  VERSION="${MAJOR}.${MINOR}.${PATCH}.${REV}"
  ASSEMBLY_VERSION="${VERSION}"
fi

export PROJ VERSION ASSEMBLY_VERSION
python3 - <<'PY'
from pathlib import Path
import os
import re

proj = Path(os.environ["PROJ"])
version = os.environ["VERSION"]
assembly_version = os.environ["ASSEMBLY_VERSION"]
text = proj.read_text()

def replace(tag, value, content):
    pattern = re.compile(rf"<{tag}>[^<]*</{tag}>")
    if not pattern.search(content):
        raise SystemExit(f"Missing <{tag}> in {proj}")
    return pattern.sub(f"<{tag}>{value}</{tag}>", content, count=1)

new_text = text
new_text = replace("Version", version, new_text)
new_text = replace("AssemblyVersion", assembly_version, new_text)

if new_text != text:
    proj.write_text(new_text)
PY

DOTNET_CLI_TELEMETRY_OPTOUT=1 "$DOTNET_BIN" build "$PROJ" -c Release -p:SolutionDir="$ROOT/"

mkdir -p "$DIST_DIR"
ZIP="$DIST_DIR/LMBridge_Plugin-${VERSION}-net8.0.zip"
rm -f "$ZIP"

FILES=("$OUT_DIR/Lidarr.Plugin.LMBridge.dll")
for ext in pdb deps.json; do
  f="$OUT_DIR/Lidarr.Plugin.LMBridge.$ext"
  if [[ -f "$f" ]]; then
    FILES+=("$f")
  fi
done

zip -j "$ZIP" "${FILES[@]}"

echo "Created $ZIP"
