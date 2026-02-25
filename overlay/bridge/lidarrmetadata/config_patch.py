import json
import os
from pathlib import Path
from typing import Any, Dict, Optional, List, Tuple

import aiohttp

from quart import jsonify, request

from lidarrmetadata import app as upstream_app
from lidarrmetadata import release_filters
from lidarrmetadata import root_patch

_STATE_DIR = Path(os.environ.get("LIMBO_INIT_STATE_DIR", "/metadata/init-state"))
_STATE_FILE = Path(
    os.environ.get(
        "LIMBO_RELEASE_FILTER_STATE_FILE",
        str(_STATE_DIR / "release-filter.json"),
    )
)
_LIDARR_CONFIG_PATH = "/api/v1/config/metadataprovider"


def register_config_routes() -> None:
    existing_rules = {rule.rule for rule in upstream_app.app.url_map.iter_rules()}

    _load_persisted_config()

    if "/config/lidarr-settings" not in existing_rules:
        @upstream_app.app.route("/config/lidarr-settings", methods=["GET", "POST"])
        async def _limbo_lidarr_settings():
            if request.method == "GET":
                return jsonify(
                    {
                        "lidarr_base_url": root_patch.get_lidarr_base_url(),
                        "lidarr_api_key": root_patch.get_lidarr_api_key(),
                    }
                )
            payload = await request.get_json(silent=True) or {}
            if not isinstance(payload, dict):
                payload = {}
            base_url = str(payload.get("lidarr_base_url") or "").strip()
            api_key = str(payload.get("lidarr_api_key") or "").strip()
            connection_ok = True
            connection_error = ""
            lidarr_version = ""
            lidarr_version_label = "Lidarr (Last Seen)"
            metadata_update_ok = True
            metadata_update_error = ""
            if not base_url or not api_key:
                connection_ok = False
                connection_error = "Lidarr URL or API key is missing."
            else:
                try:
                    version = await root_patch._fetch_lidarr_version(base_url, api_key)
                    if version:
                        lidarr_version = version
                        lidarr_version_label = "Lidarr"
                    else:
                        connection_ok = False
                        connection_error = "Connection could not be established."
                except Exception as exc:
                    connection_ok = False
                    connection_error = f"{exc}"
            if connection_ok:
                limbo_url = _resolve_limbo_base_url()
                metadata_update_ok, metadata_update_error = await _update_lidarr_metadata_source(
                    base_url, api_key, limbo_url
                )
            if connection_ok and metadata_update_ok:
                root_patch.set_lidarr_base_url(base_url)
                root_patch.set_lidarr_api_key(api_key)
                if lidarr_version:
                    root_patch.set_lidarr_version(lidarr_version)
            return jsonify(
                {
                    "ok": True,
                    "connection_ok": connection_ok,
                    "error": connection_error,
                    "lidarr_version": lidarr_version,
                    "lidarr_version_label": lidarr_version_label,
                    "metadata_update_ok": metadata_update_ok,
                    "metadata_update_error": metadata_update_error,
                }
            )

    if "/config/release-filter" not in existing_rules:
        @upstream_app.app.route("/config/release-filter", methods=["GET", "POST"])
        async def _limbo_release_filter_config():
            if request.method == "GET":
                prefer_value = _prefer_to_value(release_filters.get_runtime_media_prefer())
                data = {
                    "enabled": bool(_read_enabled_flag()),
                    "exclude_media_formats": release_filters.get_runtime_media_exclude() or [],
                    "include_media_formats": release_filters.get_runtime_media_include() or [],
                    "keep_only_media_count": release_filters.get_runtime_media_keep_only(),
                    "prefer": release_filters.get_runtime_media_prefer(),
                    "prefer_value": prefer_value,
                }
                data.update(
                    {
                        "excludeMediaFormats": data["exclude_media_formats"],
                        "includeMediaFormats": data["include_media_formats"],
                        "keepOnlyMediaCount": data["keep_only_media_count"],
                        "preferValue": data["prefer_value"],
                    }
                )
                return jsonify(data)
            payload = await request.get_json(silent=True) or {}
            enabled = _is_truthy(payload.get("enabled", True))
            lidarr_base_url, base_url_provided = _extract_lidarr_base_url(payload)
            if base_url_provided and _is_localhost_url(lidarr_base_url):
                base_url_provided = False
                lidarr_base_url = None
            lidarr_url_base = _extract_lidarr_url_base(payload)
            lidarr_port = _extract_lidarr_port(payload)
            lidarr_use_ssl = _extract_lidarr_use_ssl(payload)
            lidarr_api_key, api_key_provided = _extract_lidarr_api_key(payload)
            lidarr_client_ip = None
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
            prefer_value = payload.get("prefer_value")
            if prefer_value is None:
                prefer_value = payload.get("preferValue")
            if prefer_value is not None:
                prefer = _prefer_value_to_token(prefer_value)
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


def _resolve_limbo_base_url() -> str:
    host = (request.host or "").strip()
    if not host:
        return ""
    if ":" in host:
        hostname, port = host.rsplit(":", 1)
        host = f"{hostname}:{port}"
    return f"http://{host}"


async def _update_lidarr_metadata_source(
    base_url: str, api_key: str, limbo_url: str
) -> Tuple[bool, str]:
    if not base_url or not api_key:
        return False, "Lidarr URL or API key is missing."
    if not limbo_url:
        return False, "Limbo URL is missing."
    base_url = base_url.rstrip("/")
    headers = {"X-Api-Key": api_key}
    timeout = aiohttp.ClientTimeout(total=8)
    get_url = f"{base_url}{_LIDARR_CONFIG_PATH}"
    put_url = f"{base_url}{_LIDARR_CONFIG_PATH}/1"
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(get_url, headers=headers) as resp:
                if resp.status >= 400:
                    return False, f"GET metadata config failed (status {resp.status})."
                data = await resp.json()
            if isinstance(data, list):
                data = data[0] if data else {}
            if not isinstance(data, dict):
                return False, "Unexpected metadata config response."
            data["metadataSource"] = limbo_url
            data.setdefault("id", 1)
            async with session.put(put_url, headers=headers, json=data) as resp:
                if resp.status >= 400:
                    return False, f"Save metadata config failed (status {resp.status})."
        return True, ""
    except Exception as exc:
        return False, f"{exc}"

    if "/config/refresh-releases" not in existing_rules:
        @upstream_app.app.route("/config/refresh-releases", methods=["POST"])
        async def _limbo_refresh_releases():
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

    if "/config/validate-ids" not in existing_rules:
        @upstream_app.app.route("/config/validate-ids", methods=["POST"])
        async def _limbo_validate_ids():
            payload = await request.get_json(silent=True) or {}
            lidarr_ids = _parse_int_list(payload.get("lidarr_ids") or payload.get("lidarrIds"))
            mbids = _parse_mbid_list(payload.get("mbids") or payload.get("mbid") or payload.get("foreignAlbumIds"))

            base_url = root_patch.get_lidarr_base_url()
            api_key = root_patch.get_lidarr_api_key()
            if not base_url or not api_key:
                return jsonify({"ok": False, "error": "Missing Lidarr base URL or API key."}), 400

            mbid_valid: List[str] = []
            mbid_invalid: List[str] = []
            lidarr_valid: List[int] = []
            lidarr_invalid: List[int] = []
            errors: List[str] = []
            timeout = aiohttp.ClientTimeout(total=4)
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
                        mbid_valid.append(mbid)
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
                    if artist_data:
                        mbid_valid.append(mbid)
                    else:
                        mbid_invalid.append(mbid)

                for lidarr_id in lidarr_ids:
                    try:
                        async with session.get(
                            base_url.rstrip("/") + f"/api/v1/album/{lidarr_id}",
                            headers=headers,
                        ) as resp:
                            if resp.status == 200:
                                lidarr_valid.append(lidarr_id)
                            elif resp.status == 404:
                                lidarr_invalid.append(lidarr_id)
                            else:
                                errors.append(f"Lidarr ID {lidarr_id}: status {resp.status}")
                    except Exception as exc:
                        errors.append(f"Lidarr ID {lidarr_id}: {exc}")

            return jsonify(
                {
                    "ok": True,
                    "mbid_valid": sorted(set(mbid_valid)),
                    "mbid_invalid": sorted(set(mbid_invalid)),
                    "lidarr_valid": sorted(set(lidarr_valid)),
                    "lidarr_invalid": sorted(set(lidarr_invalid)),
                    "errors": errors,
                }
            )


def _is_truthy(value) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _prefer_to_value(value: Optional[str]) -> int:
    if not value:
        return 2
    token = value.strip().lower()
    if token == "digital":
        return 0
    if token == "analog":
        return 1
    if token == "any":
        return 2
    return 2


def _prefer_value_to_token(value: object) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, bool):
        value = int(value)
    if isinstance(value, (int, float)):
        value = int(value)
        if value == 0:
            return "digital"
        if value == 1:
            return "analog"
        if value == 2:
            return None
        return None
    if isinstance(value, str):
        token = value.strip().lower()
        if token in {"0", "digital"}:
            return "digital"
        if token in {"1", "analog"}:
            return "analog"
        if token in {"2", "any"}:
            return None
    return None


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
        value = payload.get("limbo_plugin_version")
    if value is None:
        value = payload.get("limboPluginVersion")
    if value is None:
        value = payload.get("limbo_version")
    if value is None:
        value = payload.get("limboVersion")
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


def _is_localhost_url(value: Optional[str]) -> bool:
    if not value:
        return False
    lowered = value.strip().lower()
    if not lowered.startswith("http://") and not lowered.startswith("https://"):
        lowered = "http://" + lowered
    try:
        from urllib.parse import urlparse

        parsed = urlparse(lowered)
        host = (parsed.hostname or "").lower()
    except Exception:
        return False
    return host in {"localhost", "127.0.0.1", "::1"}


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


def _read_enabled_flag() -> bool:
    try:
        data = json.loads(_STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return True
    return bool(data.get("enabled", True))

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
            root_patch.set_lidarr_base_url_runtime(payload["lidarr_base_url"])
        if data.get("lidarr_api_key") is not None:
            payload["lidarr_api_key"] = str(data.get("lidarr_api_key") or "").strip()
            root_patch.set_lidarr_api_key_runtime(payload["lidarr_api_key"])
        if data.get("lidarr_client_ip") is not None:
            payload["lidarr_client_ip"] = str(data.get("lidarr_client_ip") or "").strip()
            root_patch.set_lidarr_client_ip(payload["lidarr_client_ip"])
        _STATE_FILE.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except Exception:
        return
