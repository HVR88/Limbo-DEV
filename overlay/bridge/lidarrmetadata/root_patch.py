import html
import json
import os
from pathlib import Path
import re
import time
import asyncio
from datetime import datetime, timezone
from typing import Optional, Tuple, Iterable

import aiohttp
import subprocess
import lidarrmetadata
from lidarrmetadata import provider
from lidarrmetadata.app import no_cache
from lidarrmetadata.version_patch import _read_version

_START_TIME = time.time()
_STATE_DIR = Path(os.environ.get("LMBRIDGE_INIT_STATE_DIR", "/metadata/init-state"))
_LIDARR_VERSION_FILE = Path(
    os.environ.get(
        "LMBRIDGE_LIDARR_VERSION_FILE",
        str(_STATE_DIR / "lidarr_version.txt"),
    )
)
_LAST_LIDARR_VERSION: Optional[str] = None
_PLUGIN_VERSION_FILE = Path(
    os.environ.get(
        "LMBRIDGE_PLUGIN_VERSION_FILE",
        str(_STATE_DIR / "lmbridge_plugin_version.txt"),
    )
)
_LAST_PLUGIN_VERSION: Optional[str] = None
_MBMS_VERSION_FILE = Path("/mbms/VERSION")
_LIDARR_BASE_URL: Optional[str] = None
_LIDARR_API_KEY: Optional[str] = None
_LIDARR_CLIENT_IP: Optional[str] = None


def _read_mbms_plus_version() -> str:
    try:
        value = _MBMS_VERSION_FILE.read_text().strip()
    except OSError:
        value = ""
    return value or "not MBMS"


def set_lidarr_base_url(value: str) -> None:
    global _LIDARR_BASE_URL
    _LIDARR_BASE_URL = value.strip() if value else ""


def get_lidarr_base_url() -> str:
    return _LIDARR_BASE_URL or ""


def set_lidarr_api_key(value: str) -> None:
    global _LIDARR_API_KEY
    _LIDARR_API_KEY = value.strip() if value else ""


def get_lidarr_api_key() -> str:
    return _LIDARR_API_KEY or ""


def set_lidarr_client_ip(value: str) -> None:
    global _LIDARR_CLIENT_IP
    _LIDARR_CLIENT_IP = value.strip() if value else ""


def get_lidarr_client_ip() -> str:
    return _LIDARR_CLIENT_IP or ""


def _cache_targets() -> Iterable[Tuple[str, object]]:
    from lidarrmetadata import util
    return (
        ("artist", util.ARTIST_CACHE),
        ("album", util.ALBUM_CACHE),
        ("spotify", util.SPOTIFY_CACHE),
        ("fanart", util.FANART_CACHE),
        ("tadb", util.TADB_CACHE),
        ("wikipedia", util.WIKI_CACHE),
    )


def _postgres_cache_targets() -> Iterable[Tuple[str, object]]:
    for name, cache in _cache_targets():
        if hasattr(cache, "_get_pool") and hasattr(cache, "_db_table"):
            yield name, cache


async def _clear_all_cache_tables() -> dict:
    cleared = []
    skipped = []
    tasks = []
    for name, cache in _postgres_cache_targets():
        if hasattr(cache, "clear"):
            tasks.append(cache.clear())
            cleared.append(name)
        else:
            skipped.append(name)
    if tasks:
        await asyncio.gather(*tasks)
    return {"cleared": cleared, "skipped": skipped}


async def _expire_all_cache_tables() -> dict:
    expired = []
    skipped = []
    for name, cache in _postgres_cache_targets():
        try:
            pool = await cache._get_pool()
            async with pool.acquire() as conn:
                await conn.execute(
                    f"UPDATE {cache._db_table} SET expires = current_timestamp;"
                )
            expired.append(name)
        except Exception:
            skipped.append(name)
    return {"expired": expired, "skipped": skipped}


def _format_uptime(seconds: float) -> str:
    total = max(0, int(seconds))
    days, rem = divmod(total, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, secs = divmod(rem, 60)
    if days:
        return f"{days}d {hours}h {minutes}m"
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


def _format_replication_date(value: object) -> str:
    if value is None:
        return "unknown"
    if isinstance(value, datetime):
        dt = value
    else:
        raw = str(value).strip()
        if not raw:
            return "unknown"
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except Exception:
            return raw
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt_local = dt.astimezone()
    date_part = dt_local.strftime("%Y-%m-%d")
    time_part = dt_local.strftime("%I:%M %p").lstrip("0")
    return f"{date_part} {time_part}"


async def _fetch_lidarr_version(base_url: str, api_key: str) -> Optional[str]:
    if not base_url or not api_key:
        return None
    url = base_url.rstrip("/") + "/api/v1/system/status"
    headers = {"X-Api-Key": api_key}
    try:
        timeout = aiohttp.ClientTimeout(total=2)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
    except Exception:
        return None
    for key in ("version", "appVersion", "packageVersion", "buildVersion"):
        value = data.get(key)
        if value:
            return str(value).strip()
    return None

def _env_first(*names: str) -> Optional[str]:
    for name in names:
        value = os.getenv(name)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def _env_any(*names: str) -> bool:
    for name in names:
        value = os.getenv(name)
        if value is not None and str(value).strip():
            return True
    return False


def _format_replication_schedule() -> Optional[str]:
    enabled = _env_first("MUSICBRAINZ_REPLICATION_ENABLED")
    if enabled is not None and enabled.lower() in {"0", "false", "no", "off"}:
        return "disabled"

    schedule = _env_first(
        "MBMS_REPLICATION_SCHEDULE",
        "MUSICBRAINZ_REPLICATION_SCHEDULE",
        "MUSICBRAINZ_REPLICATION_CRON",
    )
    time_of_day = _env_first("MUSICBRAINZ_REPLICATION_TIME")

    if schedule:
        if time_of_day and time_of_day not in schedule:
            return f"{schedule} @ {time_of_day}"
        return schedule

    if time_of_day:
        return f"daily @ {time_of_day}"

    return None


def _format_index_schedule() -> Optional[str]:
    enabled = _env_first("MUSICBRAINZ_INDEXING_ENABLED")
    if enabled is not None and enabled.lower() in {"0", "false", "no", "off"}:
        return "disabled"

    schedule = _env_first(
        "MBMS_INDEX_SCHEDULE",
        "MUSICBRAINZ_INDEXING_SCHEDULE",
        "MUSICBRAINZ_INDEXING_CRON",
    )
    frequency = _env_first("MUSICBRAINZ_INDEXING_FREQUENCY")
    day = _env_first("MUSICBRAINZ_INDEXING_DAY")
    time_of_day = _env_first("MUSICBRAINZ_INDEXING_TIME")

    if schedule:
        if time_of_day and time_of_day not in schedule:
            return f"{schedule} @ {time_of_day}"
        return schedule

    parts = []
    if frequency:
        parts.append(frequency)
    if day:
        parts.append(day)
    if time_of_day:
        parts.append(f"@ {time_of_day}")

    if parts:
        return " ".join(parts)

    return None

def _read_last_lidarr_version() -> Optional[str]:
    global _LAST_LIDARR_VERSION
    if _LAST_LIDARR_VERSION is not None:
        return _LAST_LIDARR_VERSION
    try:
        value = _LIDARR_VERSION_FILE.read_text().strip()
    except OSError:
        value = ""
    _LAST_LIDARR_VERSION = value or None
    return _LAST_LIDARR_VERSION


def set_lidarr_version(value: Optional[str]) -> None:
    value = (value or "").strip()
    version = value or None
    global _LAST_LIDARR_VERSION
    _LAST_LIDARR_VERSION = version
    if not version:
        return
    try:
        _LIDARR_VERSION_FILE.parent.mkdir(parents=True, exist_ok=True)
        _LIDARR_VERSION_FILE.write_text(version + "\n")
    except OSError:
        return


def _read_last_plugin_version() -> Optional[str]:
    global _LAST_PLUGIN_VERSION
    if _LAST_PLUGIN_VERSION is not None:
        return _LAST_PLUGIN_VERSION
    try:
        value = _PLUGIN_VERSION_FILE.read_text().strip()
    except OSError:
        value = ""
    _LAST_PLUGIN_VERSION = value or None
    return _LAST_PLUGIN_VERSION


def set_plugin_version(value: Optional[str]) -> None:
    value = (value or "").strip()
    version = value or None
    global _LAST_PLUGIN_VERSION
    _LAST_PLUGIN_VERSION = version
    if not version:
        return
    try:
        _PLUGIN_VERSION_FILE.parent.mkdir(parents=True, exist_ok=True)
        _PLUGIN_VERSION_FILE.write_text(version + "\n")
    except OSError:
        return


def _capture_lidarr_version(user_agent: Optional[str]) -> None:
    if not user_agent:
        return
    match = re.search(r"\bLidarr/([0-9A-Za-z.\-]+)", user_agent)
    if not match:
        return
    version = match.group(1)
    global _LAST_LIDARR_VERSION
    if _LAST_LIDARR_VERSION == version:
        return
    set_lidarr_version(version)


def register_root_route() -> None:
    from lidarrmetadata import app as upstream_app
    from quart import Response, request, send_file, jsonify

    assets_dir = Path(__file__).resolve().parent / "assets"

    for rule in upstream_app.app.url_map.iter_rules():
        if rule.rule == "/assets/lmbridge-icon.png":
            break
    else:

        @upstream_app.app.route("/assets/lmbridge-icon.png", methods=["GET"])
        async def _lmbridge_icon():
            return await send_file(
                assets_dir / "lmbridge-icon.png", mimetype="image/png"
            )

    if not upstream_app.app.config.get("LMBRIDGE_CAPTURE_LIDARR_VERSION"):
        upstream_app.app.config["LMBRIDGE_CAPTURE_LIDARR_VERSION"] = True

        @upstream_app.app.before_request
        async def _lmbridge_capture_lidarr_version():
            _capture_lidarr_version(request.headers.get("User-Agent"))

    for rule in upstream_app.app.url_map.iter_rules():
        if rule.rule == "/cache/clear":
            break
    else:

        @upstream_app.app.route("/cache/clear", methods=["POST"])
        async def _lmbridge_cache_clear():
            if request.headers.get("authorization") != upstream_app.app.config.get(
                "INVALIDATE_APIKEY"
            ):
                return jsonify("Unauthorized"), 401
            result = await _clear_all_cache_tables()
            return jsonify(result)

    for rule in upstream_app.app.url_map.iter_rules():
        if rule.rule == "/cache/expire":
            break
    else:

        @upstream_app.app.route("/cache/expire", methods=["POST"])
        async def _lmbridge_cache_expire():
            if request.headers.get("authorization") != upstream_app.app.config.get(
                "INVALIDATE_APIKEY"
            ):
                return jsonify("Unauthorized"), 401
            result = await _expire_all_cache_tables()
            return jsonify(result)

    for rule in upstream_app.app.url_map.iter_rules():
        if rule.rule == "/replication/start":
            break
    else:

        @upstream_app.app.route("/replication/start", methods=["POST"])
        async def _lmbridge_replication_start():
            if request.headers.get("authorization") != upstream_app.app.config.get(
                "INVALIDATE_APIKEY"
            ):
                return jsonify("Unauthorized"), 401

            script_path = os.getenv(
                "LMBRIDGE_REPLICATION_SCRIPT", "/admin/replicate-now-bg"
            )
            script = Path(script_path)
            if not script.exists() and not script_path.endswith(".sh"):
                candidate = Path(script_path + ".sh")
                if candidate.exists():
                    script = candidate
            if not script.exists():
                return jsonify({"ok": False, "error": "Replication script not found."}), 404
            if not script.is_file():
                return jsonify({"ok": False, "error": "Replication script is not a file."}), 400

            try:
                subprocess.Popen(["/bin/bash", str(script)], cwd=str(script.parent))
            except Exception as exc:
                return jsonify({"ok": False, "error": str(exc)}), 500

            return jsonify({"ok": True, "script": str(script)})

    async def _lmbridge_root_route():
        replication_date = None
        try:
            vintage_providers = provider.get_providers_implementing(
                provider.DataVintageMixin
            )
            if vintage_providers:
                replication_date = await vintage_providers[0].data_vintage()
        except Exception:
            replication_date = None

        lidarr_version_label = "Lidarr Version (Last Seen)"
        lidarr_version = _read_last_lidarr_version()
        lidarr_base_url = get_lidarr_base_url()
        lidarr_api_key = get_lidarr_api_key()
        if lidarr_base_url and lidarr_api_key:
            fetched_version = await _fetch_lidarr_version(lidarr_base_url, lidarr_api_key)
            if fetched_version:
                lidarr_version_label = "Lidarr Version"
                lidarr_version = fetched_version
                set_lidarr_version(fetched_version)

        def fmt(value: object) -> str:
            if value is None:
                return "unknown"
            value = str(value).strip()
            return value if value else "unknown"

        info = {
            "version": fmt(_read_version()),
            "plugin_version": fmt(_read_last_plugin_version()),
            "mbms_plus_version": fmt(_read_mbms_plus_version()),
            "mbms_replication_schedule": fmt(_format_replication_schedule()),
            "mbms_index_schedule": fmt(_format_index_schedule()),
            "lidarr_version": fmt(lidarr_version),
            "lidarr_version_label": lidarr_version_label,
            "metadata_version": fmt(lidarrmetadata.__version__),
            "branch": fmt(os.getenv("GIT_BRANCH")),
            "commit": fmt(os.getenv("COMMIT_HASH")),
            "replication_date": _format_replication_date(replication_date),
            "uptime": _format_uptime(time.time() - _START_TIME),
        }
        try:
            from lidarrmetadata import release_filters

            exclude = release_filters.get_runtime_media_exclude() or []
            include = release_filters.get_runtime_media_include() or []
            keep_only = release_filters.get_runtime_media_keep_only()
            prefer = release_filters.get_runtime_media_prefer()
            enabled = bool(exclude or include or keep_only or prefer)
            config = {
                "enabled": enabled,
                "exclude_media_formats": exclude,
                "include_media_formats": include,
                "keep_only_media_count": keep_only,
                "prefer": prefer,
            }
        except Exception:
            config = {"enabled": False}
        safe = {key: html.escape(val) for key, val in info.items()}
        base_path = (upstream_app.app.config.get("ROOT_PATH") or "").rstrip("/")
        if base_path and not base_path.startswith("/"):
            base_path = "/" + base_path
        version_url = f"{base_path}/version" if base_path else "/version"
        cache_clear_url = f"{base_path}/cache/clear" if base_path else "/cache/clear"
        cache_expire_url = f"{base_path}/cache/expire" if base_path else "/cache/expire"
        replication_start_url = (
            f"{base_path}/replication/start" if base_path else "/replication/start"
        )
        icon_url = (
            f"{base_path}/assets/lmbridge-icon.png"
            if base_path
            else "/assets/lmbridge-icon.png"
        )
        mbms_url = "https://github.com/HVR88/MBMS_PLUS"
        def fmt_config_value(value: object, *, empty_label: str = "none") -> str:
            if value is None:
                return empty_label
            if isinstance(value, bool):
                return "Yes" if value else "No"
            if isinstance(value, (list, tuple)):
                if not value:
                    return empty_label
                return ", ".join(str(item) for item in value)
            text = str(value).strip()
            return text if text else empty_label

        media_formats_url = "https://github.com/HVR88/Docs-Extras/blob/master/docs/Media-Formats.md"
        exclude_label = (
            'Exclude <a class="config-link" href="{}" target="_blank" rel="noopener">Media Formats</a>'.format(
                html.escape(media_formats_url)
            )
        )
        include_label = (
            'Include <a class="config-link" href="{}" target="_blank" rel="noopener">Media Formats</a>'.format(
                html.escape(media_formats_url)
            )
        )
        config_rows = [
            ("Filtering Enabled", fmt_config_value(config.get("enabled"))),
            (
                exclude_label,
                fmt_config_value(config.get("exclude_media_formats")),
            ),
            (
                include_label,
                fmt_config_value(config.get("include_media_formats"), empty_label="all"),
            ),
            (
                "Max Media Count",
                fmt_config_value(config.get("keep_only_media_count"), empty_label="no limit"),
            ),
            (
                "Prefer Media Type",
                fmt_config_value(config.get("prefer"), empty_label="any"),
            ),
        ]
        config_html = "\n".join(
            [
                '          <div class="config-row">'
                f'<div class="config-label">{label}</div>'
                f'<div class="config-value">{html.escape(value)}</div>'
                "</div>"
                for label, value in config_rows
            ]
        )

        template_path = assets_dir / "root.html"
        template = template_path.read_text(encoding="utf-8")
        replacements = {
            "__ICON_URL__": html.escape(icon_url),
            "__LM_VERSION__": safe["version"],
            "__LM_PLUGIN_VERSION__": safe["plugin_version"],
            "__MBMS_PLUS_VERSION__": safe["mbms_plus_version"],
            "__LIDARR_VERSION__": safe["lidarr_version"],
            "__LIDARR_VERSION_LABEL__": safe["lidarr_version_label"],
            "__MBMS_REPLICATION_SCHEDULE__": safe["mbms_replication_schedule"],
            "__MBMS_INDEX_SCHEDULE__": safe["mbms_index_schedule"],
            "__METADATA_VERSION__": safe["metadata_version"],
            "__REPLICATION_DATE__": safe["replication_date"],
            "__UPTIME__": safe["uptime"],
            "__VERSION_URL__": html.escape(version_url),
            "__CACHE_CLEAR_URL__": html.escape(cache_clear_url),
            "__CACHE_EXPIRE_URL__": html.escape(cache_expire_url),
            "__REPLICATION_START_URL__": html.escape(replication_start_url),
            "__INVALIDATE_APIKEY__": html.escape(
                upstream_app.app.config.get("INVALIDATE_APIKEY") or ""
            ),
            "__MBMS_URL__": html.escape(mbms_url),
            "__CONFIG_HTML__": config_html,
        }
        lidarr_ui_url = get_lidarr_base_url()
        if not lidarr_ui_url:
            replacements["__LIDARR_OPEN__"] = ""
            replacements["__LIDARR_PILL_CLASS__"] = "pill"
        else:
            replacements["__LIDARR_OPEN__"] = (
                '            <a class="pill-button" href="{}" target="_blank" rel="noopener">Open</a>'
            ).format(html.escape(lidarr_ui_url))
            replacements["__LIDARR_PILL_CLASS__"] = "pill has-action"
        mbms_pills = "\n".join(
            [
                '          <div class="pill has-action">',
                '            <div class="label">MBMS PLUS VERSION</div>',
                f'            <div class="value">{safe["mbms_plus_version"]}</div>',
                f'            <a class="pill-button" href="{html.escape(mbms_url)}" target="_blank" rel="noopener">Git</a>',
                "          </div>",
                '          <div class="pill">',
                '            <div class="label">MBMS Index Schedule</div>',
                f'            <div class="value">{safe["mbms_index_schedule"]}</div>',
                "          </div>",
                '          <div class="pill">',
                '            <div class="label">MBMS Replication Schedule</div>',
                f'            <div class="value">{safe["mbms_replication_schedule"]}</div>',
                "          </div>",
            ]
        )
        replacements["__MBMS_PILLS__"] = mbms_pills
        page = template
        for key, value in replacements.items():
            page = page.replace(key, value)
        return Response(page, mimetype="text/html")

    wrapped = no_cache(_lmbridge_root_route)

    for rule in upstream_app.app.url_map.iter_rules():
        if rule.rule == "/":
            upstream_app.app.view_functions[rule.endpoint] = wrapped
            return

    upstream_app.app.route("/", methods=["GET"])(wrapped)
