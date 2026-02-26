import html
import json
import os
import secrets
from pathlib import Path
import re
import time
import asyncio
import inspect
from datetime import datetime, timezone
from typing import Optional, Tuple, Iterable, Dict

try:
    import aiohttp
except Exception:  # pragma: no cover - runtime dependency may be missing
    aiohttp = None
import subprocess
import socket
from urllib.parse import urlparse
import lidarrmetadata
from lidarrmetadata import provider
from lidarrmetadata.app import no_cache
from lidarrmetadata.version_patch import _read_version

_START_TIME = time.time()
_STATE_DIR = Path(os.environ.get("LIMBO_INIT_STATE_DIR", "/metadata/init-state"))
_LIDARR_VERSION_FILE = Path(
    os.environ.get(
        "LIMBO_LIDARR_VERSION_FILE",
        str(_STATE_DIR / "lidarr_version.txt"),
    )
)
_LAST_LIDARR_VERSION: Optional[str] = None
_PLUGIN_VERSION_FILE = Path(
    os.environ.get(
        "LIMBO_PLUGIN_VERSION_FILE",
        str(_STATE_DIR / "limbo_plugin_version.txt"),
    )
)
_LAST_PLUGIN_VERSION: Optional[str] = None
_MBMS_VERSION_FILE = Path("/mbms/VERSION")
_LIDARR_BASE_URL: Optional[str] = None
_LIDARR_API_KEY: Optional[str] = None
_LIDARR_CLIENT_IP: Optional[str] = None
_LIMBO_URL_MODE: Optional[str] = None
_LIMBO_URL_CUSTOM: Optional[str] = None
_FANART_KEY: Optional[str] = None
_TADB_KEY: Optional[str] = None
_LASTFM_KEY: Optional[str] = None
_LASTFM_SECRET: Optional[str] = None
_TIDAL_CLIENT_ID: Optional[str] = None
_TIDAL_CLIENT_SECRET: Optional[str] = None
_TIDAL_COUNTRY_CODE: Optional[str] = None
_TIDAL_USER: Optional[str] = None
_TIDAL_USER_PASSWORD: Optional[str] = None
_DISCOGS_KEY: Optional[str] = None
_FANART_ENABLED: Optional[bool] = None
_TADB_ENABLED: Optional[bool] = None
_LASTFM_ENABLED: Optional[bool] = None
_TIDAL_ENABLED: Optional[bool] = None
_DISCOGS_ENABLED: Optional[bool] = None
_APPLE_MUSIC_ENABLED: Optional[bool] = None
_APPLE_MUSIC_MAX_IMAGE_SIZE: Optional[str] = None
_APPLE_MUSIC_ALLOW_UPSCALE: Optional[bool] = None
_COVERART_ENABLED: Optional[bool] = None
_COVERART_SIZE: Optional[str] = None
_MUSICBRAINZ_ENABLED: Optional[bool] = None
_REFRESH_RESOLVE_NAMES: Optional[bool] = None
_GITHUB_RELEASE_CACHE: Dict[str, Tuple[float, Optional[str]]] = {}
_GITHUB_RELEASE_CACHE_TTL = 300.0
_REPLICATION_NOTIFY_FILE = Path(
    os.getenv(
        "LIMBO_REPLICATION_NOTIFY_FILE",
        str(_STATE_DIR / "replication_status.json"),
    )
)
_LAST_REPLICATION_NOTIFY: Optional[dict] = None
_THEME_FILE = Path(os.getenv("LIMBO_THEME_FILE", str(_STATE_DIR / "theme.txt")))
_SETTINGS_FILE = Path(
    os.getenv("LIMBO_SETTINGS_FILE", str(_STATE_DIR / "limbo-settings.json"))
)
_LIDARR_FALLBACK_STATE_FILE = Path(
    os.getenv(
        "LIMBO_RELEASE_FILTER_STATE_FILE",
        str(_STATE_DIR / "release-filter.json"),
    )
)


def _normalize_version_string(value: Optional[str]) -> str:
    if not value:
        return ""
    text = str(value).strip()
    match = re.match(r"[vV]?([0-9]+(?:\.[0-9]+)*)", text)
    if not match:
        return text
    return match.group(1)


def _read_inline_svg(name: str) -> str:
    assets_dir = Path(__file__).resolve().parent / "assets"
    svg_path = assets_dir / name
    try:
        content = svg_path.read_text(encoding="utf-8")
    except Exception:
        return ""
    content = re.sub(r"<\\?xml[^>]*\\?>", "", content, flags=re.IGNORECASE).strip()
    content = re.sub(r"<!--.*?-->", "", content, flags=re.DOTALL).strip()
    return content


def _parse_version(value: str) -> Optional[Tuple[int, ...]]:
    normalized = _normalize_version_string(value)
    if not normalized:
        return None
    parts = normalized.split(".")
    if not parts or any(not part.isdigit() for part in parts):
        return None
    return tuple(int(part) for part in parts)


def _is_newer_version(current: str, latest: str) -> bool:
    current_tuple = _parse_version(current)
    latest_tuple = _parse_version(latest)
    if not current_tuple or not latest_tuple:
        return False
    max_len = max(len(current_tuple), len(latest_tuple))
    current_tuple += (0,) * (max_len - len(current_tuple))
    latest_tuple += (0,) * (max_len - len(latest_tuple))
    return latest_tuple > current_tuple


def _resolve_limbo_host_url(_lidarr_base_url: str) -> str:
    gateway_ip, _error = _get_default_gateway_ip()
    if not gateway_ip:
        return ""
    limbo_port = os.getenv("LIMBO_PORT", "").strip() or "5001"
    return f"http://{gateway_ip}:{limbo_port}"


def _get_default_gateway_ip() -> Tuple[str, str]:
    try:
        with open("/proc/net/route", "r", encoding="utf-8") as fh:
            for line in fh:
                fields = line.strip().split()
                if len(fields) < 3:
                    continue
                iface, dest, gateway = fields[0], fields[1], fields[2]
                if iface == "Iface" or dest != "00000000":
                    continue
                try:
                    gateway_ip = socket.inet_ntoa(
                        int(gateway, 16).to_bytes(4, "little")
                    )
                except Exception:
                    continue
                if gateway_ip and gateway_ip != "0.0.0.0":
                    return gateway_ip, ""
    except Exception as exc:
        return "", f"Unable to read gateway: {exc}"
    return "", "Default gateway not found."


async def _fetch_latest_release_version(owner: str, repo: str) -> Optional[str]:
    if aiohttp is None:
        return None
    key = f"{owner}/{repo}"
    now = time.time()
    cached = _GITHUB_RELEASE_CACHE.get(key)
    if cached and (now - cached[0]) < _GITHUB_RELEASE_CACHE_TTL:
        return cached[1]

    version: Optional[str] = None
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "limbo",
    }
    timeout = aiohttp.ClientTimeout(total=3)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            url = f"https://api.github.com/repos/{owner}/{repo}/releases/latest"
            try:
                async with session.get(url, headers=headers) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        tag = data.get("tag_name") or data.get("name")
                        version = _normalize_version_string(tag) or None
                    elif resp.status not in (404, 422):
                        version = None
            except Exception:
                version = None

            if not version:
                url = f"https://api.github.com/repos/{owner}/{repo}/tags?per_page=1"
                try:
                    async with session.get(url, headers=headers) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            if data:
                                tag = data[0].get("name")
                                version = _normalize_version_string(tag) or None
                except Exception:
                    version = None
    finally:
        _GITHUB_RELEASE_CACHE[key] = (now, version)

    return version


def _read_mbms_plus_version() -> str:
    try:
        value = _MBMS_VERSION_FILE.read_text().strip()
    except OSError:
        value = ""
    return value or "not MBMS"


def _read_full_limbo_version() -> str:
    version_path = Path(os.environ.get("LIMBO_VERSION_FILE", "/metadata/VERSION"))
    try:
        value = version_path.read_text().strip()
    except OSError:
        value = ""
    return value or _read_version()


def _load_lidarr_settings() -> None:
    global _LIDARR_BASE_URL, _LIDARR_API_KEY, _LIMBO_URL_MODE, _LIMBO_URL_CUSTOM
    global _FANART_KEY, _TADB_KEY, _LASTFM_KEY, _LASTFM_SECRET
    global _TIDAL_CLIENT_ID, _TIDAL_CLIENT_SECRET, _TIDAL_COUNTRY_CODE
    global _TIDAL_USER, _TIDAL_USER_PASSWORD, _DISCOGS_KEY
    global _FANART_ENABLED, _TADB_ENABLED, _LASTFM_ENABLED
    global _TIDAL_ENABLED, _DISCOGS_ENABLED, _APPLE_MUSIC_ENABLED
    global _APPLE_MUSIC_MAX_IMAGE_SIZE, _APPLE_MUSIC_ALLOW_UPSCALE
    global _COVERART_ENABLED, _COVERART_SIZE, _MUSICBRAINZ_ENABLED
    global _REFRESH_RESOLVE_NAMES
    try:
        data = json.loads(_SETTINGS_FILE.read_text(encoding="utf-8"))
    except Exception:
        _LIDARR_BASE_URL = ""
        _LIDARR_API_KEY = ""
        _LIMBO_URL_MODE = "auto-referrer"
        _LIMBO_URL_CUSTOM = ""
        _FANART_KEY = ""
        _TADB_KEY = ""
        _LASTFM_KEY = ""
        _LASTFM_SECRET = ""
        _TIDAL_CLIENT_ID = ""
        _TIDAL_CLIENT_SECRET = ""
        _TIDAL_COUNTRY_CODE = ""
        _TIDAL_USER = ""
        _TIDAL_USER_PASSWORD = ""
        _DISCOGS_KEY = ""
        _FANART_ENABLED = True
        _TADB_ENABLED = True
        _LASTFM_ENABLED = True
        _TIDAL_ENABLED = True
        _DISCOGS_ENABLED = True
        _APPLE_MUSIC_ENABLED = False
        _APPLE_MUSIC_MAX_IMAGE_SIZE = "2500"
        _APPLE_MUSIC_ALLOW_UPSCALE = False
        _COVERART_ENABLED = True
        _COVERART_SIZE = "original"
        _MUSICBRAINZ_ENABLED = True
        _REFRESH_RESOLVE_NAMES = True
        return
    _LIDARR_BASE_URL = str(data.get("lidarr_base_url") or "").strip()
    _LIDARR_API_KEY = str(data.get("lidarr_api_key") or "").strip()
    mode = str(data.get("limbo_url_mode") or "").strip().lower()
    if mode not in {"auto-referrer", "auto-host", "custom"}:
        mode = "auto-referrer"
    _LIMBO_URL_MODE = mode
    _LIMBO_URL_CUSTOM = str(data.get("limbo_url") or "").strip()
    _FANART_KEY = str(data.get("fanart_key") or "").strip()
    _TADB_KEY = str(data.get("tadb_key") or "").strip()
    _LASTFM_KEY = str(data.get("lastfm_key") or "").strip()
    _LASTFM_SECRET = str(data.get("lastfm_secret") or "").strip()
    _TIDAL_CLIENT_ID = str(data.get("tidal_client_id") or "").strip()
    _TIDAL_CLIENT_SECRET = str(data.get("tidal_client_secret") or "").strip()
    _TIDAL_COUNTRY_CODE = str(data.get("tidal_country_code") or "").strip()
    _TIDAL_USER = str(data.get("tidal_user") or "").strip()
    _TIDAL_USER_PASSWORD = str(data.get("tidal_user_password") or "").strip()
    _DISCOGS_KEY = str(data.get("discogs_key") or "").strip()
    _COVERART_SIZE = str(data.get("coverart_size") or "").strip()
    _APPLE_MUSIC_MAX_IMAGE_SIZE = str(
        data.get("apple_music_max_image_size") or ""
    ).strip()
    _APPLE_MUSIC_ALLOW_UPSCALE = _read_enabled_flag(
        data.get("apple_music_allow_upscale"), False
    )
    _REFRESH_RESOLVE_NAMES = _read_enabled_flag(
        data.get("refresh_resolve_names"), True
    )
    fanart_env = str(os.getenv("FANART_KEY") or "").strip()
    tadb_env = str(os.getenv("TADB_KEY") or "").strip()
    lastfm_env = str(os.getenv("LASTFM_KEY") or "").strip()
    lastfm_secret_env = str(os.getenv("LASTFM_SECRET") or "").strip()
    tidal_client_id_env = str(os.getenv("TIDAL_CLIENT_ID") or "").strip()
    tidal_client_secret_env = str(os.getenv("TIDAL_CLIENT_SECRET") or "").strip()
    tidal_country_code_env = str(os.getenv("TIDAL_COUNTRY_CODE") or "").strip()
    tidal_user_env = str(os.getenv("TIDAL_USER") or "").strip()
    tidal_user_password_env = str(os.getenv("TIDAL_USER_PASSWORD") or "").strip()
    discogs_env = str(os.getenv("DISCOGS_KEY") or "").strip()
    _FANART_ENABLED = _read_enabled_flag(
        data.get("fanart_enabled"), bool(fanart_env)
    )
    _TADB_ENABLED = _read_enabled_flag(data.get("tadb_enabled"), bool(tadb_env))
    _LASTFM_ENABLED = _read_enabled_flag(
        data.get("lastfm_enabled"), bool(lastfm_env or lastfm_secret_env)
    )
    _TIDAL_ENABLED = _read_enabled_flag(
        data.get("tidal_enabled"),
        bool(
            tidal_client_id_env
            or tidal_client_secret_env
            or tidal_country_code_env
            or tidal_user_env
            or tidal_user_password_env
        ),
    )
    _DISCOGS_ENABLED = _read_enabled_flag(
        data.get("discogs_enabled"), bool(discogs_env)
    )
    _APPLE_MUSIC_ENABLED = _read_enabled_flag(data.get("apple_music_enabled"), False)
    _COVERART_ENABLED = _read_enabled_flag(data.get("coverart_enabled"), True)
    _MUSICBRAINZ_ENABLED = _read_enabled_flag(data.get("musicbrainz_enabled"), True)
    if _APPLE_MUSIC_ENABLED and not _APPLE_MUSIC_MAX_IMAGE_SIZE:
        _APPLE_MUSIC_MAX_IMAGE_SIZE = "2500"
    if _COVERART_ENABLED and not _COVERART_SIZE:
        _COVERART_SIZE = "original"
    if _FANART_ENABLED and not _FANART_KEY:
        _FANART_KEY = fanart_env
    if _TADB_ENABLED and not _TADB_KEY:
        _TADB_KEY = tadb_env
    if _LASTFM_ENABLED and not _LASTFM_KEY:
        _LASTFM_KEY = lastfm_env
    if _LASTFM_ENABLED and not _LASTFM_SECRET:
        _LASTFM_SECRET = lastfm_secret_env
    if _TIDAL_ENABLED and not _TIDAL_CLIENT_ID:
        _TIDAL_CLIENT_ID = tidal_client_id_env
    if _TIDAL_ENABLED and not _TIDAL_CLIENT_SECRET:
        _TIDAL_CLIENT_SECRET = tidal_client_secret_env
    if _TIDAL_ENABLED and not _TIDAL_COUNTRY_CODE:
        _TIDAL_COUNTRY_CODE = tidal_country_code_env
    if _TIDAL_ENABLED and not _TIDAL_USER:
        _TIDAL_USER = tidal_user_env
    if _TIDAL_ENABLED and not _TIDAL_USER_PASSWORD:
        _TIDAL_USER_PASSWORD = tidal_user_password_env
    if _DISCOGS_ENABLED and not _DISCOGS_KEY:
        _DISCOGS_KEY = discogs_env
    return


def _persist_lidarr_settings() -> None:
    try:
        _SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "lidarr_base_url": _LIDARR_BASE_URL or "",
            "lidarr_api_key": _LIDARR_API_KEY or "",
            "limbo_url_mode": _LIMBO_URL_MODE or "auto-referrer",
            "limbo_url": _LIMBO_URL_CUSTOM or "",
            "fanart_key": _FANART_KEY or "",
            "tadb_key": _TADB_KEY or "",
            "lastfm_key": _LASTFM_KEY or "",
            "lastfm_secret": _LASTFM_SECRET or "",
            "tidal_client_id": _TIDAL_CLIENT_ID or "",
            "tidal_client_secret": _TIDAL_CLIENT_SECRET or "",
            "tidal_country_code": _TIDAL_COUNTRY_CODE or "",
            "tidal_user": _TIDAL_USER or "",
            "tidal_user_password": _TIDAL_USER_PASSWORD or "",
            "discogs_key": _DISCOGS_KEY or "",
            "coverart_enabled": bool(_COVERART_ENABLED),
            "coverart_size": _COVERART_SIZE or "",
            "musicbrainz_enabled": bool(_MUSICBRAINZ_ENABLED),
            "refresh_resolve_names": bool(_REFRESH_RESOLVE_NAMES),
            "fanart_enabled": bool(_FANART_ENABLED),
            "tadb_enabled": bool(_TADB_ENABLED),
            "lastfm_enabled": bool(_LASTFM_ENABLED),
            "tidal_enabled": bool(_TIDAL_ENABLED),
            "discogs_enabled": bool(_DISCOGS_ENABLED),
            "apple_music_enabled": bool(_APPLE_MUSIC_ENABLED),
            "apple_music_max_image_size": _APPLE_MUSIC_MAX_IMAGE_SIZE or "",
            "apple_music_allow_upscale": bool(_APPLE_MUSIC_ALLOW_UPSCALE),
        }
        _SETTINGS_FILE.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except Exception:
        return


def set_lidarr_base_url(value: str) -> None:
    _set_lidarr_base_url(value, persist=True)


def set_lidarr_base_url_runtime(value: str) -> None:
    _set_lidarr_base_url(value, persist=False)


def _set_lidarr_base_url(value: str, *, persist: bool) -> None:
    global _LIDARR_BASE_URL
    _LIDARR_BASE_URL = value.strip() if value else ""
    if persist:
        _persist_lidarr_settings()


def get_lidarr_base_url() -> str:
    return _LIDARR_BASE_URL or ""


def set_lidarr_api_key(value: str) -> None:
    _set_lidarr_api_key(value, persist=True)


def set_lidarr_api_key_runtime(value: str) -> None:
    _set_lidarr_api_key(value, persist=False)


def _set_lidarr_api_key(value: str, *, persist: bool) -> None:
    global _LIDARR_API_KEY
    _LIDARR_API_KEY = value.strip() if value else ""
    if persist:
        _persist_lidarr_settings()


def get_lidarr_api_key() -> str:
    return _LIDARR_API_KEY or ""


def set_limbo_url_mode(value: str) -> None:
    _set_limbo_url_mode(value, persist=True)


def set_limbo_url_mode_runtime(value: str) -> None:
    _set_limbo_url_mode(value, persist=False)


def _set_limbo_url_mode(value: str, *, persist: bool) -> None:
    global _LIMBO_URL_MODE
    mode = str(value or "").strip().lower()
    if mode not in {"auto-referrer", "auto-host", "custom"}:
        mode = "auto-referrer"
    _LIMBO_URL_MODE = mode
    if persist:
        _persist_lidarr_settings()


def get_limbo_url_mode() -> str:
    return _LIMBO_URL_MODE or "auto-referrer"


def set_limbo_url_custom(value: str) -> None:
    _set_limbo_url_custom(value, persist=True)


def set_limbo_url_custom_runtime(value: str) -> None:
    _set_limbo_url_custom(value, persist=False)


def _set_limbo_url_custom(value: str, *, persist: bool) -> None:
    global _LIMBO_URL_CUSTOM
    _LIMBO_URL_CUSTOM = value.strip() if value else ""
    if persist:
        _persist_lidarr_settings()


def get_limbo_url_custom() -> str:
    return _LIMBO_URL_CUSTOM or ""


def set_fanart_key(value: str) -> None:
    _set_fanart_key(value, persist=True)


def set_fanart_key_runtime(value: str) -> None:
    _set_fanart_key(value, persist=False)


def _set_fanart_key(value: str, *, persist: bool) -> None:
    global _FANART_KEY
    _FANART_KEY = value.strip() if value else ""
    if persist:
        _persist_lidarr_settings()


def get_fanart_key() -> str:
    return _FANART_KEY or ""


def set_tadb_key(value: str) -> None:
    _set_tadb_key(value, persist=True)


def set_tadb_key_runtime(value: str) -> None:
    _set_tadb_key(value, persist=False)


def _set_tadb_key(value: str, *, persist: bool) -> None:
    global _TADB_KEY
    _TADB_KEY = value.strip() if value else ""
    if persist:
        _persist_lidarr_settings()


def get_tadb_key() -> str:
    return _TADB_KEY or ""


def set_lastfm_key(value: str) -> None:
    _set_lastfm_key(value, persist=True)


def set_lastfm_key_runtime(value: str) -> None:
    _set_lastfm_key(value, persist=False)


def _set_lastfm_key(value: str, *, persist: bool) -> None:
    global _LASTFM_KEY
    _LASTFM_KEY = value.strip() if value else ""
    if persist:
        _persist_lidarr_settings()


def get_lastfm_key() -> str:
    return _LASTFM_KEY or ""


def set_lastfm_secret(value: str) -> None:
    _set_lastfm_secret(value, persist=True)


def set_lastfm_secret_runtime(value: str) -> None:
    _set_lastfm_secret(value, persist=False)


def _set_lastfm_secret(value: str, *, persist: bool) -> None:
    global _LASTFM_SECRET
    _LASTFM_SECRET = value.strip() if value else ""
    if persist:
        _persist_lidarr_settings()


def get_lastfm_secret() -> str:
    return _LASTFM_SECRET or ""


def set_tidal_client_id(value: str) -> None:
    _set_tidal_client_id(value, persist=True)


def set_tidal_client_id_runtime(value: str) -> None:
    _set_tidal_client_id(value, persist=False)


def _set_tidal_client_id(value: str, *, persist: bool) -> None:
    global _TIDAL_CLIENT_ID
    _TIDAL_CLIENT_ID = value.strip() if value else ""
    if persist:
        _persist_lidarr_settings()


def get_tidal_client_id() -> str:
    return _TIDAL_CLIENT_ID or ""


def set_tidal_client_secret(value: str) -> None:
    _set_tidal_client_secret(value, persist=True)


def set_tidal_client_secret_runtime(value: str) -> None:
    _set_tidal_client_secret(value, persist=False)


def _set_tidal_client_secret(value: str, *, persist: bool) -> None:
    global _TIDAL_CLIENT_SECRET
    _TIDAL_CLIENT_SECRET = value.strip() if value else ""
    if persist:
        _persist_lidarr_settings()


def get_tidal_client_secret() -> str:
    return _TIDAL_CLIENT_SECRET or ""


def set_tidal_country_code(value: str) -> None:
    _set_tidal_country_code(value, persist=True)


def set_tidal_country_code_runtime(value: str) -> None:
    _set_tidal_country_code(value, persist=False)


def _set_tidal_country_code(value: str, *, persist: bool) -> None:
    global _TIDAL_COUNTRY_CODE
    _TIDAL_COUNTRY_CODE = value.strip() if value else ""
    if persist:
        _persist_lidarr_settings()


def get_tidal_country_code() -> str:
    return _TIDAL_COUNTRY_CODE or ""


def set_tidal_user(value: str) -> None:
    _set_tidal_user(value, persist=True)


def set_tidal_user_runtime(value: str) -> None:
    _set_tidal_user(value, persist=False)


def _set_tidal_user(value: str, *, persist: bool) -> None:
    global _TIDAL_USER
    _TIDAL_USER = value.strip() if value else ""
    if persist:
        _persist_lidarr_settings()


def get_tidal_user() -> str:
    return _TIDAL_USER or ""


def set_tidal_user_password(value: str) -> None:
    _set_tidal_user_password(value, persist=True)


def set_tidal_user_password_runtime(value: str) -> None:
    _set_tidal_user_password(value, persist=False)


def _set_tidal_user_password(value: str, *, persist: bool) -> None:
    global _TIDAL_USER_PASSWORD
    _TIDAL_USER_PASSWORD = value.strip() if value else ""
    if persist:
        _persist_lidarr_settings()


def get_tidal_user_password() -> str:
    return _TIDAL_USER_PASSWORD or ""


def set_discogs_key(value: str) -> None:
    _set_discogs_key(value, persist=True)


def set_discogs_key_runtime(value: str) -> None:
    _set_discogs_key(value, persist=False)


def _set_discogs_key(value: str, *, persist: bool) -> None:
    global _DISCOGS_KEY
    _DISCOGS_KEY = value.strip() if value else ""
    if persist:
        _persist_lidarr_settings()


def get_discogs_key() -> str:
    return _DISCOGS_KEY or ""


def _read_enabled_flag(value: object, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def set_fanart_enabled(value: bool) -> None:
    _set_fanart_enabled(value, persist=True)


def _set_fanart_enabled(value: bool, *, persist: bool) -> None:
    global _FANART_ENABLED
    _FANART_ENABLED = bool(value)
    if persist:
        _persist_lidarr_settings()


def get_fanart_enabled() -> bool:
    return bool(_FANART_ENABLED)


def set_tadb_enabled(value: bool) -> None:
    _set_tadb_enabled(value, persist=True)


def _set_tadb_enabled(value: bool, *, persist: bool) -> None:
    global _TADB_ENABLED
    _TADB_ENABLED = bool(value)
    if persist:
        _persist_lidarr_settings()


def get_tadb_enabled() -> bool:
    return bool(_TADB_ENABLED)


def set_lastfm_enabled(value: bool) -> None:
    _set_lastfm_enabled(value, persist=True)


def _set_lastfm_enabled(value: bool, *, persist: bool) -> None:
    global _LASTFM_ENABLED
    _LASTFM_ENABLED = bool(value)
    if persist:
        _persist_lidarr_settings()


def get_lastfm_enabled() -> bool:
    return bool(_LASTFM_ENABLED)


def set_tidal_enabled(value: bool) -> None:
    _set_tidal_enabled(value, persist=True)


def _set_tidal_enabled(value: bool, *, persist: bool) -> None:
    global _TIDAL_ENABLED
    _TIDAL_ENABLED = bool(value)
    if persist:
        _persist_lidarr_settings()


def get_tidal_enabled() -> bool:
    return bool(_TIDAL_ENABLED)


def set_discogs_enabled(value: bool) -> None:
    _set_discogs_enabled(value, persist=True)


def _set_discogs_enabled(value: bool, *, persist: bool) -> None:
    global _DISCOGS_ENABLED
    _DISCOGS_ENABLED = bool(value)
    if persist:
        _persist_lidarr_settings()


def get_discogs_enabled() -> bool:
    return bool(_DISCOGS_ENABLED)


def set_apple_music_enabled(value: bool) -> None:
    _set_apple_music_enabled(value, persist=True)


def _set_apple_music_enabled(value: bool, *, persist: bool) -> None:
    global _APPLE_MUSIC_ENABLED
    _APPLE_MUSIC_ENABLED = bool(value)
    if persist:
        _persist_lidarr_settings()


def get_apple_music_enabled() -> bool:
    return bool(_APPLE_MUSIC_ENABLED)


def set_apple_music_max_image_size(value: str) -> None:
    _set_apple_music_max_image_size(value, persist=True)


def _set_apple_music_max_image_size(value: str, *, persist: bool) -> None:
    global _APPLE_MUSIC_MAX_IMAGE_SIZE
    _APPLE_MUSIC_MAX_IMAGE_SIZE = value.strip() if value else ""
    if persist:
        _persist_lidarr_settings()


def get_apple_music_max_image_size() -> str:
    return _APPLE_MUSIC_MAX_IMAGE_SIZE or ""


def set_apple_music_allow_upscale(value: bool) -> None:
    _set_apple_music_allow_upscale(value, persist=True)


def _set_apple_music_allow_upscale(value: bool, *, persist: bool) -> None:
    global _APPLE_MUSIC_ALLOW_UPSCALE
    _APPLE_MUSIC_ALLOW_UPSCALE = bool(value)
    if persist:
        _persist_lidarr_settings()


def get_apple_music_allow_upscale() -> bool:
    return bool(_APPLE_MUSIC_ALLOW_UPSCALE)


def set_coverart_enabled(value: bool) -> None:
    _set_coverart_enabled(value, persist=True)


def _set_coverart_enabled(value: bool, *, persist: bool) -> None:
    global _COVERART_ENABLED
    _COVERART_ENABLED = bool(value)
    if persist:
        _persist_lidarr_settings()


def get_coverart_enabled() -> bool:
    return bool(_COVERART_ENABLED)


def set_coverart_size(value: str) -> None:
    _set_coverart_size(value, persist=True)


def _set_coverart_size(value: str, *, persist: bool) -> None:
    global _COVERART_SIZE
    _COVERART_SIZE = value.strip().lower() if value else ""
    if persist:
        _persist_lidarr_settings()


def get_coverart_size() -> str:
    return _COVERART_SIZE or ""


def set_refresh_resolve_names(value: bool) -> None:
    _set_refresh_resolve_names(value, persist=True)


def _set_refresh_resolve_names(value: bool, *, persist: bool) -> None:
    global _REFRESH_RESOLVE_NAMES
    _REFRESH_RESOLVE_NAMES = bool(value)
    if persist:
        _persist_lidarr_settings()


def get_refresh_resolve_names() -> bool:
    return bool(_REFRESH_RESOLVE_NAMES)


def set_musicbrainz_enabled(value: bool) -> None:
    _set_musicbrainz_enabled(value, persist=True)


def _set_musicbrainz_enabled(value: bool, *, persist: bool) -> None:
    global _MUSICBRAINZ_ENABLED
    _MUSICBRAINZ_ENABLED = bool(value)
    if persist:
        _persist_lidarr_settings()


def get_musicbrainz_enabled() -> bool:
    return bool(_MUSICBRAINZ_ENABLED)


def _is_localhost_url(value: str) -> bool:
    lowered = value.strip().lower()
    if not lowered:
        return False
    if not lowered.startswith("http://") and not lowered.startswith("https://"):
        lowered = "http://" + lowered
    try:
        from urllib.parse import urlparse

        parsed = urlparse(lowered)
        host = (parsed.hostname or "").lower()
    except Exception:
        return False
    return host in {"localhost", "127.0.0.1", "::1"}


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


async def _maybe_await(value: object) -> object:
    if inspect.isawaitable(value):
        return await value
    return value


async def _clear_all_cache_tables() -> dict:
    cleared = []
    skipped = []
    tasks = []
    for name, cache in _postgres_cache_targets():
        if hasattr(cache, "clear"):
            tasks.append(_maybe_await(cache.clear()))
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
            pool = await _maybe_await(cache._get_pool())
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


def _format_replication_date_html(value: object) -> str:
    label = _format_replication_date(value)
    if not label:
        return html.escape(label)
    if label.lower() == "unknown":
        return html.escape(label)
    parts = label.rsplit(" ", 1)
    if len(parts) != 2 or parts[1] not in {"AM", "PM"}:
        return html.escape(label)
    base = html.escape(parts[0])
    ampm = html.escape(parts[1])
    return f'{base}&nbsp;<span class="ampm">{ampm}</span>'


def _format_schedule_html(value: Optional[str]) -> str:
    if value is None:
        return html.escape("unknown")
    text = str(value).strip()
    if not text:
        return html.escape("unknown")
    pattern = re.compile(r"\b([01]?\d|2[0-3]):([0-5]\d)(?:\s*([APap][Mm]))?\b")
    parts = []
    last = 0
    for match in pattern.finditer(text):
        parts.append(html.escape(text[last : match.start()]))
        hour = int(match.group(1))
        minute = match.group(2)
        ampm = (match.group(3) or ("AM" if hour < 12 else "PM")).upper()
        hour12 = hour % 12 or 12
        parts.append(f'{hour12}:{minute}&nbsp;<span class="ampm">{ampm}</span>')
        last = match.end()
    parts.append(html.escape(text[last:]))
    return "".join(parts)


def _read_replication_status() -> Tuple[bool, str]:
    status_path = Path(
        os.getenv(
            "LIMBO_REPLICATION_STATUS_FILE",
            "/metadata/init-state/replication.pid",
        )
    )
    if not status_path.exists():
        return False, ""
    started = ""
    try:
        mtime = status_path.stat().st_mtime
        started = _format_replication_date(
            datetime.fromtimestamp(mtime, tz=timezone.utc)
        )
    except Exception:
        started = ""
    return True, started


def _read_replication_notify_state() -> Optional[dict]:
    global _LAST_REPLICATION_NOTIFY
    if _LAST_REPLICATION_NOTIFY is not None:
        return _LAST_REPLICATION_NOTIFY
    try:
        data = json.loads(_REPLICATION_NOTIFY_FILE.read_text())
        if isinstance(data, dict):
            _LAST_REPLICATION_NOTIFY = data
            return data
    except Exception:
        return None
    return None


def _write_replication_notify_state(payload: dict) -> None:
    global _LAST_REPLICATION_NOTIFY
    try:
        _REPLICATION_NOTIFY_FILE.parent.mkdir(parents=True, exist_ok=True)
        _REPLICATION_NOTIFY_FILE.write_text(json.dumps(payload))
        _LAST_REPLICATION_NOTIFY = payload
    except Exception:
        return


def _read_theme() -> str:
    try:
        theme = _THEME_FILE.read_text().strip().lower()
    except Exception:
        return ""
    return theme if theme in {"dark", "light", "auto"} else ""


def _write_theme(theme: str) -> None:
    if theme not in {"dark", "light", "auto"}:
        return
    try:
        _THEME_FILE.parent.mkdir(parents=True, exist_ok=True)
        _THEME_FILE.write_text(theme)
    except Exception:
        return


def _replication_remote_config() -> Tuple[bool, str, str, str]:
    use_remote = False
    base_url = os.getenv("LIMBO_REPLICATION_BASE_URL") or ""
    start_url = os.getenv("LIMBO_REPLICATION_URL") or ""
    status_url = os.getenv("LIMBO_REPLICATION_STATUS_URL") or ""

    if base_url or start_url or status_url:
        use_remote = True
    elif os.getenv("LIMBO_REPLICATION_REMOTE", "").lower() in {"1", "true", "yes"}:
        use_remote = True
    elif os.getenv("MBMS_ADMIN_ENABLED", "").lower() in {"1", "true", "yes"}:
        use_remote = True

    if not base_url:
        base_url = os.getenv("MBMS_ADMIN_BASE_URL", "") or "http://musicbrainz:8099"
    if not start_url:
        start_url = base_url.rstrip("/") + "/replication/start"
    if not status_url:
        status_url = base_url.rstrip("/") + "/replication/status"

    header = os.getenv("LIMBO_REPLICATION_HEADER", "") or "X-MBMS-Key"
    key = (
        os.getenv("LIMBO_REPLICATION_KEY")
        or os.getenv("MBMS_ADMIN_KEY")
        or os.getenv("LIMBO_APIKEY")
        or ""
    )
    return use_remote, start_url, status_url, (header + ":" + key if key else "")


def _replication_auth_config(app_config: dict) -> Tuple[str, str]:
    header = os.getenv("LIMBO_REPLICATION_HEADER", "") or "X-MBMS-Key"
    key = (
        os.getenv("LIMBO_REPLICATION_KEY")
        or os.getenv("MBMS_ADMIN_KEY")
        or app_config.get("LIMBO_APIKEY")
        or ""
    )
    return header, key


async def _fetch_replication_status_remote(
    status_url: str, header_pair: str
) -> Optional[dict]:
    if aiohttp is None:
        return None
    headers = {}
    if header_pair and ":" in header_pair:
        name, value = header_pair.split(":", 1)
        headers[name] = value
    try:
        timeout = aiohttp.ClientTimeout(total=2)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(status_url, headers=headers) as resp:
                if resp.status != 200:
                    return None
                return await resp.json()
    except Exception:
        return None


async def _fetch_lidarr_version(base_url: str, api_key: str) -> Optional[str]:
    if not base_url or not api_key:
        return None
    if aiohttp is None:
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
    _load_lidarr_settings()
    limbo_api_key = (
        os.getenv("LIMBO_APIKEY")
        or upstream_app.app.config.get("LIMBO_APIKEY")
        or upstream_app.app.config.get("INVALIDATE_APIKEY")
    )
    if limbo_api_key:
        upstream_app.app.config["LIMBO_APIKEY"] = limbo_api_key
        upstream_app.app.config["INVALIDATE_APIKEY"] = limbo_api_key

    for rule in upstream_app.app.url_map.iter_rules():
        if rule.rule == "/assets/limbo-icon.png":
            break
    else:

        @upstream_app.app.route("/assets/limbo-icon.png", methods=["GET"])
        async def _limbo_icon():
            return await send_file(assets_dir / "limbo-icon.png", mimetype="image/png")

    for rule in upstream_app.app.url_map.iter_rules():
        if rule.rule == "/assets/limbo-settings.svg":
            break
    else:

        @upstream_app.app.route("/assets/limbo-settings.svg", methods=["GET"])
        async def _limbo_settings_icon():
            return await send_file(
                assets_dir / "limbo-settings.svg", mimetype="image/svg+xml"
            )

    for rule in upstream_app.app.url_map.iter_rules():
        if rule.rule == "/assets/limbo-dark.svg":
            break
    else:

        @upstream_app.app.route("/assets/limbo-dark.svg", methods=["GET"])
        async def _limbo_dark_icon():
            return await send_file(
                assets_dir / "limbo-dark.svg", mimetype="image/svg+xml"
            )

    for rule in upstream_app.app.url_map.iter_rules():
        if rule.rule == "/assets/limbo-light.svg":
            break
    else:

        @upstream_app.app.route("/assets/limbo-light.svg", methods=["GET"])
        async def _limbo_light_icon():
            return await send_file(
                assets_dir / "limbo-light.svg", mimetype="image/svg+xml"
            )

    for rule in upstream_app.app.url_map.iter_rules():
        if rule.rule == "/assets/limbo-tall-arrow.svg":
            break
    else:

        @upstream_app.app.route("/assets/limbo-tall-arrow.svg", methods=["GET"])
        async def _limbo_tall_arrow():
            return await send_file(
                assets_dir / "limbo-tall-arrow.svg", mimetype="image/svg+xml"
            )

    for rule in upstream_app.app.url_map.iter_rules():
        if rule.rule == "/assets/root.css":
            break
    else:

        @upstream_app.app.route("/assets/root.css", methods=["GET"])
        async def _limbo_root_css():
            return await send_file(assets_dir / "root.css", mimetype="text/css")

    if not upstream_app.app.config.get("LIMBO_CAPTURE_LIDARR_VERSION"):
        upstream_app.app.config["LIMBO_CAPTURE_LIDARR_VERSION"] = True

        @upstream_app.app.before_request
        async def _limbo_capture_lidarr_version():
            _capture_lidarr_version(request.headers.get("User-Agent"))

    for rule in upstream_app.app.url_map.iter_rules():
        if rule.rule == "/cache/clear":
            break
    else:

        @upstream_app.app.route("/cache/clear", methods=["POST"])
        async def _limbo_cache_clear():
            if request.headers.get("authorization") != upstream_app.app.config.get(
                "LIMBO_APIKEY"
            ):
                return jsonify("Unauthorized"), 401
            result = await _clear_all_cache_tables()
            return jsonify(result)

    for rule in upstream_app.app.url_map.iter_rules():
        if rule.rule == "/cache/expire":
            break
    else:

        @upstream_app.app.route("/cache/expire", methods=["POST"])
        async def _limbo_cache_expire():
            if request.headers.get("authorization") != upstream_app.app.config.get(
                "LIMBO_APIKEY"
            ):
                return jsonify("Unauthorized"), 401
            result = await _expire_all_cache_tables()
            return jsonify(result)

    for rule in upstream_app.app.url_map.iter_rules():
        if rule.rule == "/replication/start":
            break
    else:

        @upstream_app.app.route("/replication/start", methods=["POST"])
        async def _limbo_replication_start():
            header_name, auth_key = _replication_auth_config(upstream_app.app.config)
            if auth_key and (
                request.headers.get(header_name) != auth_key
                and request.headers.get("authorization") != auth_key
            ):
                return jsonify("Unauthorized"), 401
            use_remote, start_url, _status_url, header_pair = (
                _replication_remote_config()
            )
            upstream_app.app.logger.info(
                "Replication start requested (remote=%s, url=%s)",
                "true" if use_remote else "false",
                start_url,
            )
            if use_remote:
                if aiohttp is None:
                    return jsonify({"ok": False, "error": "aiohttp not installed"}), 500
                headers = {}
                if header_pair and ":" in header_pair:
                    name, value = header_pair.split(":", 1)
                    headers[name] = value
                try:
                    timeout = aiohttp.ClientTimeout(total=4)
                    async with aiohttp.ClientSession(timeout=timeout) as session:
                        async with session.post(start_url, headers=headers) as resp:
                            data = await resp.text()
                            if resp.status >= 400:
                                return (
                                    jsonify({"ok": False, "error": data}),
                                    resp.status,
                                )
                            return jsonify({"ok": True, "remote": True})
                except Exception as exc:
                    return jsonify({"ok": False, "error": str(exc)}), 500

            script_path = os.getenv("LIMBO_REPLICATION_SCRIPT", "/admin/replicate-now")
            script = Path(script_path)
            if not script.exists() and not script_path.endswith(".sh"):
                candidate = Path(script_path + ".sh")
                if candidate.exists():
                    script = candidate
            if not script.exists():
                return (
                    jsonify({"ok": False, "error": "Replication script not found."}),
                    404,
                )
            if not script.is_file():
                return (
                    jsonify(
                        {"ok": False, "error": "Replication script is not a file."}
                    ),
                    400,
                )

            try:
                subprocess.Popen(["/bin/bash", str(script)], cwd=str(script.parent))
            except Exception as exc:
                return jsonify({"ok": False, "error": str(exc)}), 500

            return jsonify({"ok": True, "script": str(script)})

    for rule in upstream_app.app.url_map.iter_rules():
        if rule.rule == "/replication/status":
            break
    else:

        @upstream_app.app.route("/replication/status", methods=["GET"])
        async def _limbo_replication_status():
            use_remote, _start_url, status_url, header_pair = (
                _replication_remote_config()
            )
            if use_remote:
                data = await _fetch_replication_status_remote(status_url, header_pair)
                if data is not None:
                    notify = _read_replication_notify_state()
                    if notify:
                        data = dict(data)
                        data["last"] = notify
                    return jsonify(data)
            running, started = _read_replication_status()
            payload = {"running": running}
            if started:
                payload["started"] = started
            notify = _read_replication_notify_state()
            if notify:
                payload["last"] = notify
            return jsonify(payload)

    for rule in upstream_app.app.url_map.iter_rules():
        if rule.rule == "/replication/notify":
            break
    else:

        @upstream_app.app.route("/replication/notify", methods=["POST"])
        async def _limbo_replication_notify():
            header_name, auth_key = _replication_auth_config(upstream_app.app.config)
            if auth_key and (
                request.headers.get(header_name) != auth_key
                and request.headers.get("authorization") != auth_key
            ):
                return jsonify("Unauthorized"), 401

            payload = await request.get_json(silent=True) or {}
            if not isinstance(payload, dict):
                payload = {}
            if not payload.get("finished_at"):
                payload["finished_at"] = datetime.now(timezone.utc).isoformat()
            payload["finished_label"] = _format_replication_date(payload["finished_at"])
            _write_replication_notify_state(payload)
            upstream_app.app.logger.info("Replication notify received: %s", payload)
            return jsonify({"ok": True})

    for rule in upstream_app.app.url_map.iter_rules():
        if rule.rule == "/theme":
            break
    else:

        @upstream_app.app.route("/theme", methods=["GET", "POST"])
        async def _limbo_theme():
            if request.method == "GET":
                return jsonify({"theme": _read_theme()})
            auth_key = upstream_app.app.config.get("LIMBO_APIKEY")
            if auth_key and request.headers.get("authorization") != auth_key:
                return jsonify("Unauthorized"), 401
            payload = await request.get_json(silent=True) or {}
            if not isinstance(payload, dict):
                payload = {}
            theme = str(payload.get("theme") or "").strip().lower()
            if theme not in {"dark", "light", "auto"}:
                return jsonify({"error": "invalid theme"}), 400
            _write_theme(theme)
            return jsonify({"ok": True, "theme": theme})

    async def _limbo_root_route():
        replication_date = None
        try:
            vintage_providers = provider.get_providers_implementing(
                provider.DataVintageMixin
            )
            if vintage_providers:
                replication_date = await _maybe_await(
                    vintage_providers[0].data_vintage()
                )
        except Exception:
            replication_date = None

        lidarr_version_label = "Lidarr (Last Seen)"
        lidarr_version = _read_last_lidarr_version()
        lidarr_base_url = get_lidarr_base_url()
        lidarr_api_key = get_lidarr_api_key()
        if lidarr_base_url and lidarr_api_key:
            fetched_version = await _fetch_lidarr_version(
                lidarr_base_url, lidarr_api_key
            )
            if fetched_version:
                lidarr_version_label = "Lidarr"
                lidarr_version = fetched_version
                set_lidarr_version(fetched_version)

        def fmt(value: object) -> str:
            if value is None:
                return "unknown"
            value = str(value).strip()
            return value if value else "unknown"

        replication_schedule = _format_replication_schedule()
        index_schedule = _format_index_schedule()
        info = {
            "version": fmt(_read_full_limbo_version()),
            "plugin_version": fmt(_read_last_plugin_version()),
            "mbms_plus_version": fmt(_read_mbms_plus_version()),
            "mbms_replication_schedule": fmt(replication_schedule),
            "mbms_index_schedule": fmt(index_schedule),
            "lidarr_version": fmt(lidarr_version),
            "lidarr_version_label": lidarr_version_label,
            "metadata_version": fmt(lidarrmetadata.__version__),
            "branch": fmt(os.getenv("GIT_BRANCH")),
            "commit": fmt(os.getenv("COMMIT_HASH")),
            "replication_date": _format_replication_date(replication_date),
            "uptime": _format_uptime(time.time() - _START_TIME),
        }
        replication_date_html = _format_replication_date_html(replication_date)
        replication_schedule_html = _format_schedule_html(
            info["mbms_replication_schedule"]
        )
        index_schedule_html = _format_schedule_html(info["mbms_index_schedule"])
        theme_value = _read_theme()
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
        forwarded_proto = (request.headers.get("X-Forwarded-Proto") or "").strip()
        scheme = forwarded_proto or (request.scheme or "").strip()
        host = (request.host or "").strip()
        limbo_url = ""
        if scheme and host:
            limbo_url = f"{scheme}://{host}{base_path}"
        limbo_referrer_url = limbo_url
        limbo_host_url = _resolve_limbo_host_url(lidarr_base_url)
        limbo_referrer_effective = limbo_referrer_url or limbo_host_url
        limbo_mode = get_limbo_url_mode()
        limbo_custom_url = get_limbo_url_custom()
        if limbo_mode == "custom" and limbo_custom_url:
            limbo_url = limbo_custom_url
        elif limbo_mode == "auto-host" and limbo_host_url:
            limbo_url = limbo_host_url
        elif limbo_mode == "auto-referrer":
            limbo_url = limbo_referrer_effective
        version_url = f"{base_path}/version" if base_path else "/version"
        cache_clear_url = f"{base_path}/cache/clear" if base_path else "/cache/clear"
        cache_expire_url = f"{base_path}/cache/expire" if base_path else "/cache/expire"
        replication_start_url = (
            f"{base_path}/replication/start" if base_path else "/replication/start"
        )
        replication_status_url = (
            f"{base_path}/replication/status" if base_path else "/replication/status"
        )
        icon_url = (
            f"{base_path}/assets/limbo-icon.png"
            if base_path
            else "/assets/limbo-icon.png"
        )
        lm_repo_url = "https://github.com/HVR88/Limbo_Bridge"
        mbms_url = "https://github.com/HVR88/MBMS_PLUS"
        musicbrainz_ui_url = (
            f"{base_path}/musicbrainz" if base_path else "/musicbrainz"
        )

        def fmt_config_value(value: object, *, empty_label: str = "none") -> str:
            if value is None:
                return empty_label
            if isinstance(value, bool):
                return "ENABLED" if value else "DISABLED"
            if isinstance(value, (list, tuple)):
                if not value:
                    return empty_label
                return ", ".join(str(item) for item in value)
            text = str(value).strip()
            return text if text else empty_label

        media_formats_url = (
            "https://github.com/HVR88/Docs-Extras/blob/master/docs/Media-Formats.md"
        )
        exclude_label = "Filtered"
        include_label = "Include Filtered"
        media_type_link = '<a class="config-link" href="{}" target="_blank" rel="noopener">Media type</a>'.format(
            html.escape(media_formats_url)
        )
        config_menu_svg = _read_inline_svg("limbo-arrows-updn.svg")
        enabled_value = fmt_config_value(config.get("enabled")).upper()
        enabled_checked = "true" if config.get("enabled") else "false"
        config_rows = [
            (
                f"<span data-filter-label-enabled>{media_type_link} filtering enabled</span>"
                f'<span data-filter-label-disabled style="display:none">{media_type_link} filtering disabled</span>',
                f'<label class="config-toggle">'
                f'<input type="checkbox" data-config-enabled {"checked" if enabled_checked == "true" else ""} />'
                '<span class="config-toggle__track" aria-hidden="true">'
                '<span class="config-toggle__thumb"></span>'
                "</span>"
                "</label>",
            ),
            (
                "Limit the number of releases",
                f'<span class="config-value-text">{html.escape(fmt_config_value(config.get("keep_only_media_count"), empty_label="no limit"))}</span>'
                '<button class="config-action" type="button" aria-label="More" data-config-menu>'
                f'<span class="config-action__inner">{config_menu_svg}</span>'
                "</button>",
            ),
            (
                "(Optional) Preferred media type when limiting",
                f'<span class="config-value-text">{html.escape(fmt_config_value(config.get("prefer"), empty_label="any"))}</span>'
                '<button class="config-action" type="button" aria-label="More" data-config-menu>'
                f'<span class="config-action__inner">{config_menu_svg}</span>'
                "</button>",
            ),
            (
                exclude_label,
                f'<span class="config-value-text">{html.escape(fmt_config_value(config.get("exclude_media_formats")))}</span>'
                '<button class="config-action" type="button" aria-label="More" data-config-menu>'
                f'<span class="config-action__inner">{config_menu_svg}</span>'
                "</button>",
            ),
            (
                "&nbsp;",
                '<span class="config-value-text">&nbsp;</span>',
            ),
        ]
        config_html = "\n".join(
            [
                '          <div class="config-row">'
                f'<div class="config-label">{label}</div>'
                '<div class="config-value">'
                f"{value}"
                "</div>"
                "</div>"
                for label, value in config_rows
            ]
        )

        template_path = assets_dir / "root.html"
        template = template_path.read_text(encoding="utf-8")
        css_version = html.escape(info["version"])
        css_nonce = secrets.token_hex(3)
        template = template.replace(
            'href="/assets/root.css"',
            f'href="/assets/root.css?v={css_version}-{css_nonce}"',
        )
        use_remote, _start_url, status_url, header_pair = _replication_remote_config()
        replication_running = False
        replication_started = ""
        if use_remote:
            status_data = await _fetch_replication_status_remote(
                status_url, header_pair
            )
            if status_data and isinstance(status_data, dict):
                replication_running = bool(status_data.get("running"))
                replication_started = str(status_data.get("started") or "")
        if not use_remote:
            replication_running, replication_started = _read_replication_status()
        replication_button_label = "Running" if replication_running else "Start"
        replication_pill_class = (
            "pill has-action wide-action" if replication_running else "pill has-action"
        )
        replication_button_attrs = []
        if replication_running:
            replication_button_attrs.append('data-replication-running="true"')
        if replication_started:
            replication_button_attrs.append(
                f'data-replication-started="{html.escape(replication_started)}"'
            )
        replication_button_attr_text = (
            " " + " ".join(replication_button_attrs) if replication_button_attrs else ""
        )

        settings_svg = _read_inline_svg("limbo-settings.svg")
        theme_dark_svg = _read_inline_svg("limbo-dark.svg")
        theme_light_svg = _read_inline_svg("limbo-light.svg")
        theme_auto_svg = _read_inline_svg("limbo-auto.svg")
        tall_arrow_svg = _read_inline_svg("limbo-tall-arrow.svg")
        thick_arrow_rt_svg = _read_inline_svg("limbo-arrow-thick-rt.svg")

        replacements = {
            "__ICON_URL__": html.escape(icon_url),
            "__LM_VERSION__": safe["version"],
            "__LM_PLUGIN_VERSION__": safe["plugin_version"],
            "__MBMS_PLUS_VERSION__": safe["mbms_plus_version"],
            "__LIDARR_VERSION__": safe["lidarr_version"],
            "__LIDARR_VERSION_LABEL__": safe["lidarr_version_label"],
            "__LIDARR_BASE_URL__": html.escape(get_lidarr_base_url()),
            "__LIDARR_API_KEY__": html.escape(get_lidarr_api_key()),
            "__LIMBO_URL__": html.escape(limbo_url),
            "__LIMBO_URL_REFERRER__": html.escape(limbo_referrer_effective),
            "__LIMBO_URL_HOST__": html.escape(limbo_host_url),
            "__LIMBO_URL_MODE__": html.escape(limbo_mode),
            "__LIMBO_URL_CUSTOM__": html.escape(limbo_custom_url),
            "__FANART_KEY__": html.escape(get_fanart_key()),
            "__TADB_KEY__": html.escape(get_tadb_key()),
            "__LASTFM_KEY__": html.escape(get_lastfm_key()),
            "__LASTFM_SECRET__": html.escape(get_lastfm_secret()),
            "__TIDAL_CLIENT_ID__": html.escape(get_tidal_client_id()),
            "__TIDAL_CLIENT_SECRET__": html.escape(get_tidal_client_secret()),
            "__TIDAL_COUNTRY_CODE__": html.escape(get_tidal_country_code()),
            "__TIDAL_USER__": html.escape(get_tidal_user()),
            "__TIDAL_USER_PASSWORD__": html.escape(get_tidal_user_password()),
            "__DISCOGS_KEY__": html.escape(get_discogs_key()),
            "__FANART_ENABLED__": "true" if get_fanart_enabled() else "false",
            "__TADB_ENABLED__": "true" if get_tadb_enabled() else "false",
            "__LASTFM_ENABLED__": "true" if get_lastfm_enabled() else "false",
            "__TIDAL_ENABLED__": "true" if get_tidal_enabled() else "false",
            "__DISCOGS_ENABLED__": "true" if get_discogs_enabled() else "false",
            "__APPLE_MUSIC_ENABLED__": "true" if get_apple_music_enabled() else "false",
            "__COVERART_ENABLED__": "true" if get_coverart_enabled() else "false",
            "__COVERART_SIZE__": html.escape(get_coverart_size()),
            "__MUSICBRAINZ_ENABLED__": "true" if get_musicbrainz_enabled() else "false",
            "__MBMS_REPLICATION_SCHEDULE__": safe["mbms_replication_schedule"],
            "__MBMS_INDEX_SCHEDULE__": safe["mbms_index_schedule"],
            "__METADATA_VERSION__": safe["metadata_version"],
            "__REFRESH_RESOLVE_NAMES__": "checked" if get_refresh_resolve_names() else "",
            "__REPLICATION_DATE__": safe["replication_date"],
            "__REPLICATION_DATE_HTML__": replication_date_html,
            "__THEME__": html.escape(theme_value),
            "__UPTIME__": safe["uptime"],
            "__VERSION_URL__": html.escape(version_url),
            "__CACHE_CLEAR_URL__": html.escape(cache_clear_url),
            "__CACHE_EXPIRE_URL__": html.escape(cache_expire_url),
            "__REPLICATION_START_URL__": html.escape(replication_start_url),
            "__REPLICATION_STATUS_URL__": html.escape(replication_status_url),
            "__MUSICBRAINZ_UI_URL__": html.escape(musicbrainz_ui_url),
            "__REPLICATION_PILL_CLASS__": replication_pill_class,
            "__LIMBO_APIKEY__": html.escape(
                upstream_app.app.config.get("LIMBO_APIKEY") or ""
            ),
            "__MBMS_URL__": html.escape(mbms_url),
            "__SETTINGS_ICON__": settings_svg,
            "__THEME_ICON_DARK__": theme_dark_svg,
            "__THEME_ICON_LIGHT__": theme_light_svg,
            "__THEME_ICON_AUTO__": theme_auto_svg,
            "__TALL_ARROW_ICON__": tall_arrow_svg,
            "__THICK_ARROW_RT_ICON__": json.dumps(thick_arrow_rt_svg),
            "__CONFIG_MENU_ICON__": config_menu_svg,
            "__CONFIG_HTML__": config_html,
        }
        lidarr_ui_url = get_lidarr_base_url()
        if "last seen" in lidarr_version_label.lower():
            lidarr_pill_class = "pill"
            lidarr_pill_href = ""
            lidarr_arrow = ""
        elif not lidarr_ui_url:
            lidarr_pill_class = "pill"
            lidarr_pill_href = ""
            lidarr_arrow = ""
        else:
            lidarr_pill_class = "pill has-action"
            lidarr_pill_href = html.escape(lidarr_ui_url)
            lidarr_arrow = (
                f'<span class="pill-arrow" aria-hidden="true">{tall_arrow_svg}</span>'
            )
        lidarr_plugins_url = (
            f"{lidarr_ui_url.rstrip('/')}/system/plugins" if lidarr_ui_url else ""
        )

        lm_latest, mbms_latest = await asyncio.gather(
            _fetch_latest_release_version("HVR88", "Limbo_Bridge"),
            _fetch_latest_release_version("HVR88", "MBMS_PLUS"),
        )

        lm_update = (
            lm_latest
            if lm_latest and _is_newer_version(info["version"], lm_latest)
            else None
        )
        plugin_update = (
            lm_latest
            if lm_latest and _is_newer_version(info["plugin_version"], lm_latest)
            else None
        )
        mbms_update = (
            mbms_latest
            if mbms_latest and _is_newer_version(info["mbms_plus_version"], mbms_latest)
            else None
        )

        def _format_version_value(
            current: str, update: Optional[str]
        ) -> Tuple[str, bool]:
            if not update:
                return current, False
            return (
                f'<span class="version-current">{current}</span>'
                f'<span class="version-update">&rarr; NEW {html.escape(update)}</span>',
                True,
            )

        lm_pill_class = "pill has-action"
        lm_pill_href = html.escape(lm_repo_url)

        if plugin_update:
            replacements["__PLUGIN_PILL_CLASS__"] = "pill"
            replacements["__LM_PLUGIN_LABEL__"] = "Limbo Plugin"
        else:
            replacements["__PLUGIN_PILL_CLASS__"] = "pill"
            replacements["__LM_PLUGIN_LABEL__"] = "Limbo Plugin Version"

        mbms_version_value, mbms_has_update = _format_version_value(
            safe["mbms_plus_version"], mbms_update
        )
        mbms_value_class = "value has-update" if mbms_has_update else "value"
        mbms_pills = "\n".join(
            [
                '          <button type="button" class="pill" data-pill-href="" data-modal-open="schedule-indexer">',
                '            <div class="label">DB Indexing Schedule</div>',
                f'            <div class="value">{index_schedule_html}</div>',
                f'            <span class="pill-arrow" aria-hidden="true">{tall_arrow_svg}</span>',
                "          </button>",
                '          <button type="button" class="pill" data-pill-href="" data-modal-open="schedule-replication">',
                '            <div class="label">DB Replication Schedule</div>',
                f'            <div class="value">{replication_schedule_html}</div>',
                f"            {lidarr_arrow}",
                "          </button>",
            ]
        )
        replacements["__MBMS_PILLS__"] = mbms_pills

        if lm_pill_href:
            lm_pill_tag_open = '<button type="button" class="{}"'.format(lm_pill_class)
            lm_pill_tag_open += ' data-pill-href="{}">'.format(lm_pill_href)
        else:
            lm_pill_tag_open = '<button type="button" class="{}" disabled>'.format(
                lm_pill_class
            )
        mbms_version_label = html.escape(safe["mbms_plus_version"])
        bridge_version_label = html.escape(safe["version"])
        mbms_title = (
            f"New: {html.escape(mbms_update)}" if mbms_update else ""
        )
        bridge_title = (
            f"New: {html.escape(lm_update)}" if lm_update else ""
        )
        mbms_class = "version-part"
        if mbms_update:
            mbms_class += " version-part--update"
        bridge_class = "version-part"
        if lm_update:
            bridge_class += " version-part--update"
        mbms_title_attr = f' title="{mbms_title}"' if mbms_title else ""
        bridge_title_attr = f' title="{bridge_title}"' if bridge_title else ""
        lm_version_value = (
            f'<span class="{mbms_class}"'
            f"{mbms_title_attr}>"
            f"{mbms_version_label}</span> "
            f'(<span class="{bridge_class}"'
            f"{bridge_title_attr}>"
            f"{bridge_version_label}</span>)"
        )
        lm_value_class = "value"
        lm_pill_html = "\n".join(
            [
                f"          {lm_pill_tag_open}",
                '            <div class="label">LIMBO (BRIDGE/WEBUI)</div>',
                f'            <div class="{lm_value_class}">{lm_version_value}</div>',
                f'            <span class="pill-arrow" aria-hidden="true">{tall_arrow_svg}</span>',
                "          </button>",
            ]
        )
        replacements["__LM_PILL_HTML__"] = lm_pill_html

        if lidarr_pill_href:
            lidarr_pill_tag_open = '<button type="button" class="{}"'.format(
                lidarr_pill_class
            )
            lidarr_pill_tag_open += ' data-pill-href="{}">'.format(lidarr_pill_href)
        else:
            lidarr_pill_tag_open = '<button type="button" class="{}" disabled>'.format(
                lidarr_pill_class
            )
        lidarr_pill_html = "\n".join(
            [
                f"          {lidarr_pill_tag_open}",
                f'            <div class="label" data-lidarr-pill-label>{safe["lidarr_version_label"]}</div>',
                f'            <div class="value" data-lidarr-pill-value>{safe["lidarr_version"]}</div>',
                f'            <span class="pill-arrow" aria-hidden="true">{tall_arrow_svg}</span>',
                "          </button>",
            ]
        )
        replacements["__LIDARR_PILL_HTML__"] = lidarr_pill_html

        replication_pill_html = "\n".join(
            [
                '          <button type="button" class="{}" data-replication-pill data-pill-href="{}">'.format(
                    replication_pill_class, html.escape(replication_start_url)
                ),
                '            <div class="label">Last Replication</div>',
                f'            <div class="value replication-date" data-replication-value>{replication_date_html}</div>',
                f'            <span class="pill-arrow" aria-hidden="true">{tall_arrow_svg}</span>',
                "          </button>",
            ]
        )
        replacements["__REPLICATION_PILL_HTML__"] = replication_pill_html
        page = template
        for key, value in replacements.items():
            page = page.replace(key, value)
        return Response(page, mimetype="text/html")

    wrapped = no_cache(_limbo_root_route)

    for rule in upstream_app.app.url_map.iter_rules():
        if rule.rule == "/":
            upstream_app.app.view_functions[rule.endpoint] = wrapped
            return

    upstream_app.app.route("/", methods=["GET"])(wrapped)
