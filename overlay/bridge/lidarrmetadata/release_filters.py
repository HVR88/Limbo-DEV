import json
from typing import Any, Dict, Iterable, List, Optional

from lidarrmetadata.media_formats_meta import (
    ALIAS_MAP,
    PRIORITY_ANALOG_FIRST,
    PRIORITY_DIGITAL_FIRST,
)

_RUNTIME_MEDIA_EXCLUDE: Optional[List[str]] = None
_RUNTIME_MEDIA_INCLUDE: Optional[List[str]] = None
_RUNTIME_MEDIA_KEEP_ONLY: Optional[int] = None
_RUNTIME_MEDIA_PREFER: Optional[str] = None
_ALIAS_MAP = ALIAS_MAP


def _parse_list(value: Optional[str]) -> List[str]:
    if not value:
        return []
    return [item.strip().lower() for item in value.split(",") if item.strip()]


def _normalize_tokens(values: Iterable[str]) -> List[str]:
    if not values:
        return []
    tokens = []
    for value in values:
        token = str(value).strip().lower()
        if token:
            tokens.append(token)
    return tokens


def _expand_aliases(tokens: List[str]) -> List[str]:
    expanded = []
    for token in tokens:
        mapped = _ALIAS_MAP.get(token)
        if mapped:
            expanded.extend(mapped)
        else:
            expanded.append(token)

    seen = set()
    deduped = []
    for token in expanded:
        if token in seen:
            continue
        seen.add(token)
        deduped.append(token)
    return deduped


def set_runtime_media_exclude(values: Optional[Iterable[str]]) -> None:
    global _RUNTIME_MEDIA_EXCLUDE
    if values is None:
        _RUNTIME_MEDIA_EXCLUDE = None
        return
    if isinstance(values, str):
        tokens = _parse_list(values)
    else:
        tokens = _normalize_tokens(values)
    _RUNTIME_MEDIA_EXCLUDE = _expand_aliases(tokens)


def get_runtime_media_exclude() -> Optional[List[str]]:
    if _RUNTIME_MEDIA_EXCLUDE is None:
        return None
    return list(_RUNTIME_MEDIA_EXCLUDE)


def set_runtime_media_include(values: Optional[Iterable[str]]) -> None:
    global _RUNTIME_MEDIA_INCLUDE
    if values is None:
        _RUNTIME_MEDIA_INCLUDE = None
        return
    if isinstance(values, str):
        tokens = _parse_list(values)
    else:
        tokens = _normalize_tokens(values)
    _RUNTIME_MEDIA_INCLUDE = _expand_aliases(tokens)


def get_runtime_media_include() -> Optional[List[str]]:
    if _RUNTIME_MEDIA_INCLUDE is None:
        return None
    return list(_RUNTIME_MEDIA_INCLUDE)


def set_runtime_media_keep_only(value: Optional[object]) -> None:
    global _RUNTIME_MEDIA_KEEP_ONLY
    count = _parse_int(value)
    if count is None or count <= 0:
        _RUNTIME_MEDIA_KEEP_ONLY = None
        return
    _RUNTIME_MEDIA_KEEP_ONLY = count


def get_runtime_media_keep_only() -> Optional[int]:
    return _RUNTIME_MEDIA_KEEP_ONLY


def set_runtime_media_prefer(value: Optional[object]) -> None:
    global _RUNTIME_MEDIA_PREFER
    if value is None:
        _RUNTIME_MEDIA_PREFER = None
        return
    if isinstance(value, str):
        token = value.strip().lower()
        if token in {"digital", "analog"}:
            _RUNTIME_MEDIA_PREFER = token
            return
    _RUNTIME_MEDIA_PREFER = None


def get_runtime_media_prefer() -> Optional[str]:
    return _RUNTIME_MEDIA_PREFER


def _parse_int(value: Optional[object]) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
        try:
            return int(value)
        except ValueError:
            return None
    return None


def _release_formats(release: Dict[str, Any]) -> Iterable[str]:
    media_list = release.get("Media")
    if media_list is None:
        media_list = release.get("media")
    for medium in media_list or []:
        fmt = medium.get("Format") if isinstance(medium, dict) else None
        if fmt:
            yield str(fmt).lower()


def _has_excluded_format(release: Dict[str, Any], excluded_tokens: List[str]) -> bool:
    if not excluded_tokens:
        return False
    for fmt in _release_formats(release):
        for token in excluded_tokens:
            if token in fmt:
                return True
    return False


def _has_included_format(release: Dict[str, Any], include_tokens: List[str]) -> bool:
    if not include_tokens:
        return False
    for fmt in _release_formats(release):
        for token in include_tokens:
            if token in fmt:
                return True
    return False


def _priority_tokens() -> List[str]:
    prefer = get_runtime_media_prefer()
    if prefer == "analog":
        return list(PRIORITY_ANALOG_FIRST)
    return list(PRIORITY_DIGITAL_FIRST)


def _release_priority(release: Dict[str, Any], tokens: List[str]) -> int:
    if not tokens:
        return 0
    best = len(tokens) + 1
    for fmt in _release_formats(release):
        for idx, token in enumerate(tokens):
            if token in fmt:
                if idx < best:
                    best = idx
    return best


def after_query(results: Any, context: Dict[str, Any]) -> Any:
    if context.get("sql_file") != "release_group_by_id.sql":
        return None

    include_tokens = get_runtime_media_include() or []
    excluded_tokens = get_runtime_media_exclude() or []
    keep_only_count = get_runtime_media_keep_only()

    if not include_tokens and not excluded_tokens and not keep_only_count:
        return None

    updated = []
    for row in results or []:
        album_json = row.get("album") if isinstance(row, dict) else None
        if not album_json:
            updated.append(row)
            continue

        try:
            album = json.loads(album_json) if isinstance(album_json, str) else album_json
        except Exception:
            updated.append(row)
            continue

        releases = album.get("Releases") if isinstance(album, dict) else None
        if releases is None and isinstance(album, dict):
            releases = album.get("releases")
        if isinstance(releases, list):
            if include_tokens:
                filtered = [
                    release for release in releases
                    if _has_included_format(release, include_tokens)
                ]
                if "Releases" in album:
                    album["Releases"] = filtered
                else:
                    album["releases"] = filtered
            elif excluded_tokens:
                filtered = [
                    release for release in releases
                    if not _has_excluded_format(release, excluded_tokens)
                ]
                if filtered:
                    if "Releases" in album:
                        album["Releases"] = filtered
                    else:
                        album["releases"] = filtered

            if keep_only_count and keep_only_count > 0:
                current = album.get("Releases") if isinstance(album, dict) else None
                if current is None and isinstance(album, dict):
                    current = album.get("releases")
                if isinstance(current, list) and len(current) > keep_only_count:
                    priority_tokens = _priority_tokens()
                    trimmed = sorted(
                        current,
                        key=lambda release: (
                            _release_priority(release, priority_tokens),
                            ",".join(sorted(_release_formats(release)))
                        )
                    )[:keep_only_count]
                    if "Releases" in album:
                        album["Releases"] = trimmed
                    else:
                        album["releases"] = trimmed

        try:
            row["album"] = json.dumps(album, separators=(",", ":"))
        except Exception:
            updated.append(row)
            continue

        updated.append(row)

    return updated
