import os
import contextvars

_CACHE_STATUS = contextvars.ContextVar("lmbridge_cache_status", default=None)


def _record_cache_event(hit: bool) -> None:
    status = _CACHE_STATUS.get()
    next_status = "hit" if hit else "miss"
    if status is None:
        _CACHE_STATUS.set(next_status)
        return
    if status != next_status:
        _CACHE_STATUS.set("mixed")


def _get_cache_status() -> str:
    return _CACHE_STATUS.get()


def _reset_cache_status() -> None:
    _CACHE_STATUS.set(None)

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
    from lidarrmetadata import mitm
    from lidarrmetadata import db_hooks
    from lidarrmetadata import app as upstream_app
    from lidarrmetadata import api as api_mod
    from lidarrmetadata import provider as provider_api
    from lidarrmetadata import util
    from lidarrmetadata import release_filters
    if mitm.is_enabled():
        @upstream_app.app.after_request
        async def _lmbridge_mitm_hook(response):
            return await mitm.apply_response(response)

    if not getattr(api_mod.get_release_group_info, "_lmbridge_release_filter_wrapped", False):
        original_release_group_info = api_mod.get_release_group_info

        async def _lmbridge_get_release_group_info(*args, **kwargs):
            release_group, expiry = await original_release_group_info(*args, **kwargs)
            try:
                release_group = release_filters.apply_release_group_filters(release_group)
            except Exception:
                pass
            return release_group, expiry

        _lmbridge_get_release_group_info._lmbridge_release_filter_wrapped = True
        api_mod.get_release_group_info = _lmbridge_get_release_group_info

    if not getattr(api_mod.get_release_group_info_basic, "_lmbridge_cache_status", False):
        original_release_group_info_basic = api_mod.get_release_group_info_basic

        async def _lmbridge_get_release_group_info_basic(mbid, *args, **kwargs):
            try:
                cached, expiry = await util.ALBUM_CACHE.get(mbid)
                now = provider_api.utcnow()
                if cached and expiry > now:
                    _record_cache_event(True)
                else:
                    _record_cache_event(False)
            except Exception:
                pass
            return await original_release_group_info_basic(mbid, *args, **kwargs)

        _lmbridge_get_release_group_info_basic._lmbridge_cache_status = True
        api_mod.get_release_group_info_basic = _lmbridge_get_release_group_info_basic

    if not getattr(upstream_app.app, "_lmbridge_cache_header", False):

        @upstream_app.app.before_request
        async def _lmbridge_cache_header_reset():
            _reset_cache_status()

        @upstream_app.app.after_request
        async def _lmbridge_cache_header(response):
            status = _get_cache_status()
            if status:
                response.headers["X-LMBridge-Cache"] = status
            _reset_cache_status()
            return response

        upstream_app.app._lmbridge_cache_header = True

    if db_hooks.is_enabled():
        from lidarrmetadata import provider as provider_mod

        original_query_from_file = provider_mod.MusicbrainzDbProvider.query_from_file
        if not getattr(original_query_from_file, "_lmbridge_sql_file_hooked", False):

            async def _lmbridge_query_from_file(self, sql_file, *args):
                token = db_hooks.set_sql_file(sql_file)
                try:
                    return await original_query_from_file(self, sql_file, *args)
                finally:
                    db_hooks.reset_sql_file(token)

            _lmbridge_query_from_file._lmbridge_sql_file_hooked = True
            provider_mod.MusicbrainzDbProvider.query_from_file = _lmbridge_query_from_file

        original = provider_mod.MusicbrainzDbProvider.map_query
        if not getattr(original, "_lmbridge_db_hooked", False):

            async def _lmbridge_map_query(self, sql, *args, _conn=None):
                context = {
                    "provider": self.__class__.__name__,
                    "sql": sql,
                    "args": args,
                    "sql_file": db_hooks.get_sql_file(),
                }

                new_sql, new_args, pool_key = db_hooks.apply_before(sql, args, context)
                context["sql"] = new_sql
                context["args"] = new_args
                context["pool_key"] = pool_key

                if pool_key and pool_key != "default":
                    pool = await db_hooks.get_pool(self, pool_key)
                    async with pool.acquire() as _alt_conn:
                        results = await original(self, new_sql, *new_args, _conn=_alt_conn)
                else:
                    results = await original(self, new_sql, *new_args, _conn=_conn)
                return db_hooks.apply_after(results, context)

            _lmbridge_map_query._lmbridge_db_hooked = True
            provider_mod.MusicbrainzDbProvider.map_query = _lmbridge_map_query

    if os.environ.get("LMBRIDGE_PATCH_SPOTIFY_CACHE", "").lower() in {"1", "true", "yes"}:
        # Placeholder: wire safe_spotify_set into call sites if/when needed.
        # Intentionally no behavior change today.
        return
