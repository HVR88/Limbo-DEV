import html
import json
import os
from pathlib import Path
import re
import time
from typing import Optional

import lidarrmetadata
from lidarrmetadata import provider
from lidarrmetadata.app import no_cache
from lidarrmetadata.version_patch import _read_version

_START_TIME = time.time()
_LIDARR_VERSION_FILE = Path(os.environ.get("LMBRIDGE_LIDARR_VERSION_FILE", "/metadata/lidarr_version.txt"))
_LAST_LIDARR_VERSION: Optional[str] = None


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
    _LAST_LIDARR_VERSION = version
    try:
        _LIDARR_VERSION_FILE.parent.mkdir(parents=True, exist_ok=True)
        _LIDARR_VERSION_FILE.write_text(version + "\n")
    except OSError:
        return


def register_root_route() -> None:
    from lidarrmetadata import app as upstream_app
    from quart import Response, request, send_file

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

        def fmt(value: object) -> str:
            if value is None:
                return "unknown"
            value = str(value).strip()
            return value if value else "unknown"

        info = {
            "version": fmt(_read_version()),
            "mbms_plus_version": fmt(os.getenv("MBMS_PLUS_VERSION")),
            "mbms_replication_schedule": fmt(_format_replication_schedule()),
            "mbms_index_schedule": fmt(_format_index_schedule()),
            "lidarr_version": fmt(_read_last_lidarr_version()),
            "metadata_version": fmt(lidarrmetadata.__version__),
            "branch": fmt(os.getenv("GIT_BRANCH")),
            "commit": fmt(os.getenv("COMMIT_HASH")),
            "replication_date": fmt(replication_date),
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
        icon_url = (
            f"{base_path}/assets/lmbridge-icon.png"
            if base_path
            else "/assets/lmbridge-icon.png"
        )
        mbms_url = "https://github.com/HVR88/MBMS_PLUS"
        def fmt_config_value(value: object) -> str:
            if value is None:
                return "none"
            if isinstance(value, bool):
                return "Yes" if value else "No"
            if isinstance(value, (list, tuple)):
                return ", ".join(str(item) for item in value) or "none"
            text = str(value).strip()
            return text if text else "none"

        config_rows = [
            ("Filtering Enabled", fmt_config_value(config.get("enabled"))),
            (
                "Exclude Media Formats",
                fmt_config_value(config.get("exclude_media_formats")),
            ),
            (
                "Include Media Formats",
                fmt_config_value(config.get("include_media_formats")),
            ),
            ("Max Media Count", fmt_config_value(config.get("keep_only_media_count"))),
            ("Prefer Media Type", fmt_config_value(config.get("prefer"))),
        ]
        config_html = "\n".join(
            [
                '          <div class="config-row">'
                f'<div class="config-label">{html.escape(label)}</div>'
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
            "__MBMS_PLUS_VERSION__": safe["mbms_plus_version"],
            "__LIDARR_VERSION__": safe["lidarr_version"],
            "__MBMS_REPLICATION_SCHEDULE__": safe["mbms_replication_schedule"],
            "__MBMS_INDEX_SCHEDULE__": safe["mbms_index_schedule"],
            "__METADATA_VERSION__": safe["metadata_version"],
            "__REPLICATION_DATE__": safe["replication_date"],
            "__UPTIME__": safe["uptime"],
            "__VERSION_URL__": html.escape(version_url),
            "__MBMS_URL__": html.escape(mbms_url),
            "__CONFIG_HTML__": config_html,
        }
        mbms_pills = "\n".join(
            [
                '          <div class="pill">',
                '            <div class="label">MBMS PLUS VERSION</div>',
                f'            <div class="value">{safe["mbms_plus_version"]}</div>',
                "          </div>",
                '          <div class="pill">',
                '            <div class="label">MBMS Replication Schedule</div>',
                f'            <div class="value">{safe["mbms_replication_schedule"]}</div>',
                "          </div>",
                '          <div class="pill">',
                '            <div class="label">MBMS Index Schedule</div>',
                f'            <div class="value">{safe["mbms_index_schedule"]}</div>',
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
