import os

async def safe_spotify_set(spotify_id, albumid):
    """
    Overlay helper: only set SPOTIFY_CACHE if albumid is valid
    """
    from lidarrmetadata import app as upstream_app
    from lidarrmetadata import util
    if albumid:
        await util.SPOTIFY_CACHE.set(spotify_id, albumid, ttl=upstream_app.app.config['CACHE_TTL']['cloudflare'])
    else:
        # Skip caching 0 or invalid IDs to avoid polluting the cache
        upstream_app.app.logger.debug(f"Skipping caching invalid Spotify ID: {spotify_id}")


def apply() -> None:
    """
    Apply optional runtime patches. Currently a no-op unless enabled.
    """
    if os.environ.get("LMD_PATCH_SPOTIFY_CACHE", "").lower() in {"1", "true", "yes"}:
        # Placeholder: wire safe_spotify_set into call sites if/when needed.
        # Intentionally no behavior change today.
        return
