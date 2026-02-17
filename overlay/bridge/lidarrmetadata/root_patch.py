import html
import json
import os
from pathlib import Path
import re
import time

import lidarrmetadata
from lidarrmetadata import provider
from lidarrmetadata.app import no_cache
from lidarrmetadata.version_patch import _read_version

_START_TIME = time.time()
_LIDARR_VERSION_FILE = Path(os.environ.get("LMBRIDGE_LIDARR_VERSION_FILE", "/metadata/lidarr_version.txt"))
_LAST_LIDARR_VERSION: str | None = None


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

def _env_first(*names: str) -> str | None:
    for name in names:
        value = os.getenv(name)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None

def _read_last_lidarr_version() -> str | None:
    global _LAST_LIDARR_VERSION
    if _LAST_LIDARR_VERSION is not None:
        return _LAST_LIDARR_VERSION
    try:
        value = _LIDARR_VERSION_FILE.read_text().strip()
    except OSError:
        value = ""
    _LAST_LIDARR_VERSION = value or None
    return _LAST_LIDARR_VERSION


def _capture_lidarr_version(user_agent: str | None) -> None:
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
            "mbms_replication_schedule": fmt(
                _env_first(
                    "MBMS_REPLICATION_SCHEDULE",
                    "MUSICBRAINZ_REPLICATION_SCHEDULE",
                    "MUSICBRAINZ_REPLICATION_CRON",
                )
            ),
            "mbms_index_schedule": fmt(
                _env_first(
                    "MBMS_INDEX_SCHEDULE",
                    "MUSICBRAINZ_INDEXING_SCHEDULE",
                    "MUSICBRAINZ_INDEXING_CRON",
                )
            ),
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
        config_json = html.escape(json.dumps(config, indent=2, sort_keys=True))

        page = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>LM Bridge</title>
  <style>
    :root {{
      --bg1: #f6f1e9;
      --bg2: #e6f2f3;
      --ink: #1f2c33;
      --muted: #55666f;
      --accent: #0b7d6d;
      --accent-2: #e2b159;
      --card: rgba(255, 255, 255, 0.88);
      --border: rgba(31, 44, 51, 0.08);
      --shadow: 0 12px 30px rgba(26, 38, 45, 0.14);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      color: var(--ink);
      font-family: "Space Grotesk", "IBM Plex Sans", "Source Sans 3", sans-serif;
      background:
        radial-gradient(1200px 700px at 10% 0%, var(--bg2), transparent 60%),
        radial-gradient(900px 600px at 100% 0%, #f8e8d4, transparent 55%),
        linear-gradient(180deg, var(--bg1), #fbfbfb 65%);
      min-height: 100vh;
    }}
    .wrap {{
      max-width: 900px;
      margin: 0 auto;
      padding: 48px 24px 64px;
    }}
    .card {{
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 18px;
      padding: 28px 28px 24px;
      box-shadow: var(--shadow);
      backdrop-filter: blur(6px);
    }}
    .hero {{
      text-align: center;
      margin-bottom: 12px;
    }}
    .hero img {{
      max-width: 100%;
      height: auto;
    }}
    .hero-title {{
      margin: 12px 0 6px 0;
      font-size: clamp(26px, 4vw, 40px);
      letter-spacing: -0.02em;
    }}
    .hero-sub {{
      display: block;
      font-size: 14px;
      font-weight: 700;
      color: var(--muted);
      letter-spacing: 0.08em;
    }}
    h1 {{
      margin: 0 0 8px 0;
      font-size: clamp(28px, 4vw, 40px);
      letter-spacing: -0.02em;
    }}
    .subtitle {{
      margin: 0 0 22px 0;
      color: var(--muted);
      font-size: 16px;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 14px;
    }}
    .pill {{
      border: 1px solid var(--border);
      border-radius: 14px;
      padding: 12px 14px;
      background: #ffffff;
    }}
    .label {{
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: var(--muted);
      margin-bottom: 6px;
    }}
    .value {{
      font-size: 16px;
      font-weight: 600;
    }}
    .links {{
      margin-top: 20px;
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
    }}
    .config {{
      margin-top: 20px;
      border: 1px solid var(--border);
      background: #fff;
      border-radius: 12px;
      padding: 14px 16px;
      font-family: "JetBrains Mono", "SFMono-Regular", "Consolas", "Liberation Mono", monospace;
      font-size: 12px;
      line-height: 1.6;
      white-space: pre-wrap;
      max-height: 260px;
      overflow: auto;
    }}
    .link {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 10px 14px;
      border-radius: 999px;
      border: 1px solid var(--border);
      background: #fff;
      color: var(--ink);
      text-decoration: none;
      font-weight: 600;
      transition: transform 120ms ease, box-shadow 120ms ease;
    }}
    .link:hover {{
      transform: translateY(-1px);
      box-shadow: 0 8px 18px rgba(17, 27, 32, 0.12);
    }}
    .badge {{
      display: inline-block;
      font-size: 12px;
      font-weight: 700;
      color: #fff;
      background: var(--accent);
      padding: 4px 10px;
      border-radius: 999px;
    }}
    .foot {{
      margin-top: 18px;
      font-size: 13px;
      color: var(--muted);
    }}
    .accent {{
      color: var(--accent);
    }}
  </style>
</head>
<body>
  <main class="wrap">
    <section class="card">
      <div class="hero">
        <img src="{html.escape(icon_url)}" alt="LM Bridge" width="500" />
        <h1 class="hero-title">LM Bridge - Metadata Handler for Lidarr</h1>
        <span class="hero-sub"><em>FAST • Local • Private</em></span>
      </div>

        <div class="grid">
          <div class="pill">
            <div class="label">LM Bridge Version</div>
            <div class="value">{safe["version"]}</div>
          </div>
          <div class="pill">
            <div class="label">MBMS PLUS VERSION</div>
            <div class="value">{safe["mbms_plus_version"]}</div>
          </div>
          <div class="pill">
            <div class="label">Lidarr Version (Last Seen)</div>
            <div class="value">{safe["lidarr_version"]}</div>
          </div>
          <div class="pill">
            <div class="label">MBMS Replication Schedule</div>
            <div class="value">{safe["mbms_replication_schedule"]}</div>
          </div>
          <div class="pill">
            <div class="label">MBMS Index Schedule</div>
            <div class="value">{safe["mbms_index_schedule"]}</div>
          </div>
          <div class="pill">
            <div class="label">Metadata Version</div>
            <div class="value">{safe["metadata_version"]}</div>
          </div>
          <div class="pill">
            <div class="label">Replication Date</div>
            <div class="value">{safe["replication_date"]}</div>
          </div>
          <div class="pill">
            <div class="label">Uptime</div>
            <div class="value">{safe["uptime"]}</div>
          </div>
      </div>
      <div class="links">
        <a class="link" href="{html.escape(version_url)}">Version JSON</a>
        <a class="link" href="{html.escape(mbms_url)}">MBMS PLUS Repo</a>
      </div>
      <pre class="config">{config_json}</pre>
      <div class="foot">Tip: Use <span class="accent">/album/&lt;mbid&gt;</span> to fetch release group JSON | <span class="accent">/artist/&lt;mbid&gt;</span> to fetch artist JSON.</div>
    </section>
  </main>
</body>
</html>
"""
        return Response(page, mimetype="text/html")

    wrapped = no_cache(_lmbridge_root_route)

    for rule in upstream_app.app.url_map.iter_rules():
        if rule.rule == "/":
            upstream_app.app.view_functions[rule.endpoint] = wrapped
            return

    upstream_app.app.route("/", methods=["GET"])(wrapped)
