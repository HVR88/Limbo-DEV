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

    # Map cache DB envs into upstream CACHE_CONFIG overrides (avoid upstream edits)
    cache_user = os.environ.get("POSTGRES_CACHE_USER") or os.environ.get("LMBRIDGE_CACHE_USER")
    cache_password = os.environ.get("POSTGRES_CACHE_PASSWORD") or os.environ.get("LMBRIDGE_CACHE_PASSWORD")
    cache_db = os.environ.get("POSTGRES_CACHE_DB") or os.environ.get("LMBRIDGE_CACHE_DB")
    cache_table_keys = ("fanart", "tadb", "wikipedia", "artist", "album", "spotify")
    for key in cache_table_keys:
        if cache_user and f"CACHE_CONFIG__{key}__user" not in os.environ:
            os.environ[f"CACHE_CONFIG__{key}__user"] = cache_user
        if cache_password and f"CACHE_CONFIG__{key}__password" not in os.environ:
            os.environ[f"CACHE_CONFIG__{key}__password"] = cache_password
        if cache_db and f"CACHE_CONFIG__{key}__db_name" not in os.environ:
            os.environ[f"CACHE_CONFIG__{key}__db_name"] = cache_db

    # Register overlay config (adds BRIDGE to CONFIGS)
    import lidarrmetadata.bridge_config  # noqa: F401

    from lidarrmetadata import version_patch
    version_patch.register_version_route()
    from lidarrmetadata import config_patch
    config_patch.register_config_routes()

    # Optional runtime patches (auto-enable if MITM hook configured)
    apply_patches = os.environ.get("LMBRIDGE_APPLY_PATCHES", "").lower() in {"1", "true", "yes"}
    if not apply_patches and (
        os.environ.get("LMBRIDGE_MITM_MODULE")
        or os.environ.get("LMBRIDGE_MITM_PATH")
        or os.environ.get("LMBRIDGE_DB_HOOK_MODULE")
        or os.environ.get("LMBRIDGE_DB_HOOK_PATH")
    ):
        apply_patches = True

    if apply_patches:
        from lidarrmetadata import app_patch

        app_patch.apply()

    # Then import the upstream server entrypoint
    from lidarrmetadata.server import main as upstream_main

    return upstream_main()


if __name__ == "__main__":
    raise SystemExit(main())
