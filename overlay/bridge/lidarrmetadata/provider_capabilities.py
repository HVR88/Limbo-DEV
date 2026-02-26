from __future__ import annotations

from typing import Dict, Any, List

PROVIDER_CAPABILITIES: Dict[str, Dict[str, Any]] = {
    "musicbrainz": {
        "display_name": "MusicBrainz",
        "capabilities": [
            "artist_metadata",
            "artist_links",
            "discography",
            "album_metadata",
            "album_art",
            "series",
            "id_redirects",
            "spotify_mapping",
        ],
        "auth": {"type": "none", "fields": []},
        "endpoints": {"base_url": "musicbrainz_db", "docs_url": ""},
        "rate_limit": {"requests_per_second": None, "requests_per_minute": None, "notes": "DB-backed"},
        "supports_cache": True,
        "pricing": "unknown",
        "notes": "Cover art via CAA URLs; links parsed into typed sources.",
    },
    "fanart": {
        "display_name": "Fanart.tv",
        "capabilities": ["artist_images"],
        "auth": {"type": "api_key", "fields": ["FANART_KEY"]},
        "endpoints": {"base_url": "https://webservice.fanart.tv/v3.2/music", "docs_url": ""},
        "rate_limit": {"requests_per_second": None, "requests_per_minute": None, "notes": "Best effort"},
        "supports_cache": True,
        "pricing": "free",
        "notes": "Artist artwork only (clearlogo, banner, fanart, poster).",
    },
    "theaudiodb": {
        "display_name": "TheAudioDB",
        "capabilities": ["artist_images"],
        "auth": {"type": "api_key", "fields": ["TADB_KEY"]},
        "endpoints": {"base_url": "https://www.theaudiodb.com/api/v2/json", "docs_url": ""},
        "rate_limit": {"requests_per_second": None, "requests_per_minute": None, "notes": "Best effort"},
        "supports_cache": True,
        "pricing": "paid_required",
        "notes": "Artist artwork only (v2 premium API).",
    },
    "discogs": {
        "display_name": "Discogs",
        "capabilities": ["artist_images"],
        "auth": {"type": "token", "fields": ["DISCOGS_KEY"]},
        "endpoints": {"base_url": "https://api.discogs.com", "docs_url": ""},
        "rate_limit": {"requests_per_second": None, "requests_per_minute": None, "notes": "Best effort"},
        "supports_cache": True,
        "pricing": "free",
        "notes": "Artist imagery and related metadata.",
    },
    "tidal": {
        "display_name": "TIDAL",
        "capabilities": ["artist_images"],
        "auth": {
            "type": "oauth_client",
            "fields": [
                "TIDAL_CLIENT_ID",
                "TIDAL_CLIENT_SECRET",
                "TIDAL_COUNTRY_CODE",
            ],
            "optional_fields": ["TIDAL_USER", "TIDAL_USER_PASSWORD"],
        },
        "endpoints": {"base_url": "https://openapi.tidal.com/v2", "docs_url": ""},
        "rate_limit": {"requests_per_second": None, "requests_per_minute": None, "notes": "Best effort"},
        "supports_cache": True,
        "pricing": "paid_required",
        "notes": "Profile art via official API; user creds used for lookup fallback.",
    },
    "apple_music": {
        "display_name": "Apple Music",
        "capabilities": ["artist_images"],
        "auth": {"type": "none", "fields": []},
        "endpoints": {"base_url": "https://itunes.apple.com/search", "docs_url": ""},
        "rate_limit": {"requests_per_second": None, "requests_per_minute": None, "notes": "Best effort"},
        "supports_cache": True,
        "pricing": "free",
        "notes": "Artist artwork via iTunes Search API.",
    },
    "lastfm": {
        "display_name": "Last.fm",
        "capabilities": ["charts"],
        "auth": {"type": "api_key", "fields": ["LASTFM_KEY", "LASTFM_SECRET"]},
        "endpoints": {"base_url": "https://ws.audioscrobbler.com/2.0/", "docs_url": ""},
        "rate_limit": {"requests_per_second": None, "requests_per_minute": None, "notes": "Best effort"},
        "supports_cache": True,
        "pricing": "free",
        "notes": "Top artists/albums only.",
    },
}


def list_provider_capabilities() -> List[Dict[str, Any]]:
    return [PROVIDER_CAPABILITIES[key] | {"id": key} for key in sorted(PROVIDER_CAPABILITIES)]
