import json
import os
from pathlib import Path
from typing import Any, Dict, Optional, List, Tuple

import aiohttp

from quart import jsonify, request

from lidarrmetadata import app as upstream_app
from lidarrmetadata import release_filters
from lidarrmetadata import root_patch

_STATE_DIR = Path(os.environ.get("LMBRIDGE_INIT_STATE_DIR", "/metadata/init-state"))
_STATE_FILE = Path(
    os.environ.get(
        "LMBRIDGE_RELEASE_FILTER_STATE_FILE",
        str(_STATE_DIR / "release-filter.json"),
    )
)


def register_config_routes() -> None:
    for rule in upstream_app.app.url_map.iter_rules():
        if rule.rule == "/config/release-filter":
            return

    _load_persisted_config()

    @upstream_app.app.route("/config/release-filter", methods=["POST"])
    async def _lmbridge_release_filter_config():
        payload = await request.get_json(silent=True) or {}
        enabled = _is_truthy(payload.get("enabled", True))
        lidarr_base_url, base_url_provided = _extract_lidarr_base_url(payload)
        lidarr_url_base = _extract_lidarr_url_base(payload)
        lidarr_port = _extract_lidarr_port(payload)
        lidarr_use_ssl = _extract_lidarr_use_ssl(payload)
        lidarr_api_key, api_key_provided = _extract_lidarr_api_key(payload)
        lidarr_client_ip = _extract_client_ip(request)
        if lidarr_client_ip:
            upstream_app.app.logger.info("LM-Bridge config sync from Lidarr at %s", lidarr_client_ip)
        if lidarr_client_ip and (not base_url_provided or _is_localhost_url(lidarr_base_url)):
            scheme = "https" if lidarr_use_ssl else "http"
            port = lidarr_port or (6868 if lidarr_use_ssl else 8686)
            lidarr_base_url = f"{scheme}://{lidarr_client_ip}:{port}{lidarr_url_base}"
            base_url_provided = True
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
        _persist_config(
            {
                "enabled": bool(enabled),
                "exclude_media_formats": release_filters.get_runtime_media_exclude() or [],
                "include_media_formats": release_filters.get_runtime_media_include() or [],
                "keep_only_media_count": release_filters.get_runtime_media_keep_only(),
                "prefer": release_filters.get_runtime_media_prefer(),
                "lidarr_version": _extract_lidarr_version(payload),
                "plugin_version": _extract_plugin_version(payload),
                "lidarr_base_url": lidarr_base_url if base_url_provided else None,
                "lidarr_api_key": lidarr_api_key if api_key_provided else None,
                "lidarr_client_ip": lidarr_client_ip,
            }
        )
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

    for rule in upstream_app.app.url_map.iter_rules():
        if rule.rule == "/config/refresh-releases":
            return

    @upstream_app.app.route("/config/refresh-releases", methods=["POST"])
    async def _lmbridge_refresh_releases():
        payload = await request.get_json(silent=True) or {}
        lidarr_ids = _parse_int_list(payload.get("lidarr_ids") or payload.get("lidarrIds"))
        mbids = _parse_mbid_list(payload.get("mbids") or payload.get("mbid") or payload.get("foreignAlbumIds"))

        base_url = root_patch.get_lidarr_base_url()
        api_key = root_patch.get_lidarr_api_key()
        if not base_url or not api_key:
            return jsonify({"ok": False, "error": "Missing Lidarr base URL or API key."}), 400

        resolved_ids: List[int] = []
        resolved_artist_ids: List[int] = []
        missing_mbids: List[str] = []
        errors: List[str] = []
        timeout = aiohttp.ClientTimeout(total=5)
        headers = {"X-Api-Key": api_key}

        async with aiohttp.ClientSession(timeout=timeout) as session:
            for mbid in mbids:
                url = base_url.rstrip("/") + "/api/v1/album"
                try:
                    async with session.get(url, headers=headers, params={"foreignAlbumId": mbid}) as resp:
                        if resp.status != 200:
                            errors.append(f"MBID {mbid}: status {resp.status}")
                            continue
                        data = await resp.json()
                except Exception as exc:
                    errors.append(f"MBID {mbid}: {exc}")
                    continue
                if data:
                    for item in data:
                        album_id = item.get("id")
                        if isinstance(album_id, int):
                            resolved_ids.append(album_id)
                    continue

                artist_url = base_url.rstrip("/") + "/api/v1/artist"
                try:
                    async with session.get(artist_url, headers=headers, params={"mbId": mbid}) as resp:
                        if resp.status != 200:
                            errors.append(f"Artist MBID {mbid}: status {resp.status}")
                            continue
                        artist_data = await resp.json()
                except Exception as exc:
                    errors.append(f"Artist MBID {mbid}: {exc}")
                    continue
                if not artist_data:
                    missing_mbids.append(mbid)
                    continue
                for artist in artist_data:
                    artist_id = artist.get("id")
                    if isinstance(artist_id, int):
                        resolved_artist_ids.append(artist_id)

            artist_ids_unique = sorted(set(resolved_artist_ids))
            for artist_id in artist_ids_unique:
                try:
                    async with session.get(
                        base_url.rstrip("/") + "/api/v1/album",
                        headers=headers,
                        params={"artistId": artist_id},
                    ) as resp:
                        if resp.status != 200:
                            errors.append(f"Artist {artist_id}: status {resp.status}")
                            continue
                        albums = await resp.json()
                except Exception as exc:
                    errors.append(f"Artist {artist_id}: {exc}")
                    continue
                for item in albums or []:
                    album_id = item.get("id")
                    if isinstance(album_id, int):
                        resolved_ids.append(album_id)

            all_ids = sorted(set(lidarr_ids + resolved_ids))
            queued: List[int] = []
            for album_id in all_ids:
                try:
                    cmd_url = base_url.rstrip("/") + "/api/v1/command"
                    payload = {"name": "RefreshAlbum", "albumId": album_id}
                    async with session.post(cmd_url, headers=headers, json=payload) as resp:
                        if resp.status not in {200, 201}:
                            errors.append(f"Album {album_id}: status {resp.status}")
                            continue
                    queued.append(album_id)
                except Exception as exc:
                    errors.append(f"Album {album_id}: {exc}")

        return jsonify(
            {
                "ok": True,
                "requested_ids": lidarr_ids,
                "resolved_ids": resolved_ids,
                "queued_ids": queued,
                "resolved_artist_ids": artist_ids_unique,
                "missing_mbids": missing_mbids,
                "errors": errors,
            }
        )


def _is_truthy(value) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _extract_lidarr_version(payload: Dict[str, Any]) -> str:
    value = payload.get("lidarr_version")
    if value is None:
        value = payload.get("lidarrVersion")
    if value is None:
        value = payload.get("lidarr_version_string")
    if value is None:
        value = payload.get("lidarrVersionString")
    return str(value).strip() if value else ""


def _extract_plugin_version(payload: Dict[str, Any]) -> str:
    value = payload.get("plugin_version")
    if value is None:
        value = payload.get("pluginVersion")
    if value is None:
        value = payload.get("lmbridge_plugin_version")
    if value is None:
        value = payload.get("lmbridgePluginVersion")
    if value is None:
        value = payload.get("lmbridge_version")
    if value is None:
        value = payload.get("lmbridgeVersion")
    return str(value).strip() if value else ""


def _extract_lidarr_base_url(payload: Dict[str, Any]) -> tuple[str, bool]:
    for key in (
        "lidarr_base_url",
        "lidarrBaseUrl",
        "lidarr_url",
        "lidarrUrl",
        "base_url",
        "baseUrl",
    ):
        if key in payload:
            value = payload.get(key)
            return (str(value).strip() if value is not None else "", True)
    return "", False


def _extract_lidarr_api_key(payload: Dict[str, Any]) -> tuple[str, bool]:
    for key in (
        "lidarr_api_key",
        "lidarrApiKey",
        "api_key",
        "apiKey",
        "lidarr_key",
        "lidarrKey",
    ):
        if key in payload:
            value = payload.get(key)
            return (str(value).strip() if value is not None else "", True)
    return "", False


def _extract_lidarr_port(payload: Dict[str, Any]) -> Optional[int]:
    for key in ("lidarr_port", "lidarrPort", "port"):
        if key in payload:
            value = payload.get(key)
            try:
                return int(value)
            except (TypeError, ValueError):
                return None
    return None


def _extract_lidarr_use_ssl(payload: Dict[str, Any]) -> bool:
    for key in ("lidarr_ssl", "lidarrSsl", "use_ssl", "useSsl", "ssl"):
        if key in payload:
            return _is_truthy(payload.get(key))
    return False


def _extract_lidarr_url_base(payload: Dict[str, Any]) -> str:
    for key in ("lidarr_url_base", "lidarrUrlBase", "url_base", "urlBase"):
        if key in payload:
            value = payload.get(key)
            text = str(value).strip() if value is not None else ""
            if text and not text.startswith("/"):
                text = "/" + text
            return text
    return ""


def _extract_client_ip(req) -> str:
    for header in ("X-Forwarded-For", "X-Real-IP"):
        value = req.headers.get(header)
        if value:
            return value.split(",")[0].strip()
    return req.remote_addr or ""


def _is_localhost_url(value: str) -> bool:
    text = (value or "").strip().lower()
    return text.startswith("http://localhost") or text.startswith("https://localhost") or \
        text.startswith("http://127.0.0.1") or text.startswith("https://127.0.0.1")


def _parse_int_list(values) -> List[int]:
    if values is None:
        return []
    if isinstance(values, str):
        values = [v for v in values.replace(",", " ").split(" ") if v]
    if isinstance(values, (int, float)):
        values = [values]
    out: List[int] = []
    for value in values:
        try:
            out.append(int(value))
        except (TypeError, ValueError):
            continue
    return out


def _parse_mbid_list(values) -> List[str]:
    if values is None:
        return []
    if isinstance(values, str):
        values = [v for v in values.replace(",", " ").split(" ") if v]
    out: List[str] = []
    for value in values:
        text = str(value).strip()
        if text:
            out.append(text)
    return out


def _load_persisted_config() -> None:
    try:
        data = json.loads(_STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return

    enabled = bool(data.get("enabled", True))
    exclude = data.get("exclude_media_formats") or []
    include = data.get("include_media_formats") or []
    keep_only_count = data.get("keep_only_media_count")
    prefer = data.get("prefer")
    if not enabled:
        exclude = []
        include = []
        keep_only_count = None
        prefer = None

    release_filters.set_runtime_media_exclude(exclude)
    release_filters.set_runtime_media_include(include)
    release_filters.set_runtime_media_keep_only(keep_only_count)
    release_filters.set_runtime_media_prefer(prefer)

    lidarr_version = (data.get("lidarr_version") or "").strip()
    if lidarr_version:
        root_patch.set_lidarr_version(lidarr_version)
    plugin_version = (data.get("plugin_version") or "").strip()
    if plugin_version:
        root_patch.set_plugin_version(plugin_version)
    lidarr_base_url = data.get("lidarr_base_url")
    if lidarr_base_url is not None:
        root_patch.set_lidarr_base_url(str(lidarr_base_url))
    lidarr_api_key = data.get("lidarr_api_key")
    if lidarr_api_key is not None:
        root_patch.set_lidarr_api_key(str(lidarr_api_key))
    lidarr_client_ip = data.get("lidarr_client_ip")
    if lidarr_client_ip is not None:
        root_patch.set_lidarr_client_ip(str(lidarr_client_ip))


def _persist_config(data: Dict[str, Any]) -> None:
    try:
        _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "enabled": bool(data.get("enabled", True)),
            "exclude_media_formats": data.get("exclude_media_formats") or [],
            "include_media_formats": data.get("include_media_formats") or [],
            "keep_only_media_count": data.get("keep_only_media_count"),
            "prefer": data.get("prefer"),
        }
        lidarr_version = (data.get("lidarr_version") or "").strip()
        if lidarr_version:
            payload["lidarr_version"] = lidarr_version
            root_patch.set_lidarr_version(lidarr_version)
        plugin_version = (data.get("plugin_version") or "").strip()
        if plugin_version:
            payload["plugin_version"] = plugin_version
            root_patch.set_plugin_version(plugin_version)
        if data.get("lidarr_base_url") is not None:
            payload["lidarr_base_url"] = str(data.get("lidarr_base_url") or "").strip()
            root_patch.set_lidarr_base_url(payload["lidarr_base_url"])
        if data.get("lidarr_api_key") is not None:
            payload["lidarr_api_key"] = str(data.get("lidarr_api_key") or "").strip()
            root_patch.set_lidarr_api_key(payload["lidarr_api_key"])
        if data.get("lidarr_client_ip") is not None:
            payload["lidarr_client_ip"] = str(data.get("lidarr_client_ip") or "").strip()
            root_patch.set_lidarr_client_ip(payload["lidarr_client_ip"])
        _STATE_FILE.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except Exception:
        return
