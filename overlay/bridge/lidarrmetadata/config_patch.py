from quart import jsonify, request

from lidarrmetadata import app as upstream_app
from lidarrmetadata import release_filters


def register_config_routes() -> None:
    for rule in upstream_app.app.url_map.iter_rules():
        if rule.rule == "/config/release-filter":
            return

    @upstream_app.app.route("/config/release-filter", methods=["POST"])
    async def _lmbridge_release_filter_config():
        payload = await request.get_json(silent=True) or {}
        enabled = _is_truthy(payload.get("enabled", True))
        exclude = payload.get("exclude_media_formats")
        if exclude is None:
            exclude = payload.get("excludeMediaFormats")
        if exclude is None:
            exclude = payload.get("media_exclude")
        include = payload.get("include_media_formats")
        if include is None:
            include = payload.get("includeMediaFormats")
        if include is None:
            include = payload.get("media_include")
        keep_only_count = payload.get("keep_only_media_count")
        if keep_only_count is None:
            keep_only_count = payload.get("keepOnlyMediaCount")
        prefer = payload.get("prefer")
        if not enabled:
            exclude = []
            include = []
            keep_only_count = None
            prefer = None

        release_filters.set_runtime_media_exclude(exclude)
        release_filters.set_runtime_media_include(include)
        release_filters.set_runtime_media_keep_only(keep_only_count)
        release_filters.set_runtime_media_prefer(prefer)
        return jsonify(
            {
                "ok": True,
                "enabled": bool(enabled),
                "exclude_media_formats": release_filters.get_runtime_media_exclude() or [],
                "include_media_formats": release_filters.get_runtime_media_include() or [],
                "keep_only_media_count": release_filters.get_runtime_media_keep_only(),
                "prefer": release_filters.get_runtime_media_prefer(),
            }
        )


def _is_truthy(value) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)
