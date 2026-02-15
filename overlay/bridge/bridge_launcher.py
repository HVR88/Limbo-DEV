#!/usr/bin/env python3
import os
import sys


def _ensure_path(path: str) -> None:
    if path and path not in sys.path:
        sys.path.insert(0, path)


def main() -> int:
    base_dir = os.path.dirname(os.path.abspath(__file__))

    # Ensure the repo root (parent of lidarrmetadata/) is on sys.path
    _ensure_path(base_dir)

    # Default to the bridge config unless explicitly overridden
    os.environ.setdefault("LIDARR_METADATA_CONFIG", "BRIDGE")

    init_state_dir = os.environ.get("LMBRIDGE_INIT_STATE_DIR", "/metadata/init-state")
    cache_fail_flag = os.path.join(init_state_dir, "cache_init_failed")
    if os.path.exists(cache_fail_flag):
        os.environ.setdefault("USE_CACHE", "false")
        print(
            "LM-Bridge: cache init failed; starting with USE_CACHE=false (null cache).",
            file=sys.stderr,
        )

    # Register overlay config (adds BRIDGE to CONFIGS)
    import lidarrmetadata.bridge_config  # noqa: F401

    # Optional runtime patches
    if os.environ.get("LMBRIDGE_APPLY_PATCHES", "").lower() in {"1", "true", "yes"}:
        from lidarrmetadata import app_patch

        app_patch.apply()

    # Then import the upstream server entrypoint
    from lidarrmetadata.server import main as upstream_main

    return upstream_main()


if __name__ == "__main__":
    raise SystemExit(main())
