import html
import os
from pathlib import Path

import lidarrmetadata
from lidarrmetadata import provider
from lidarrmetadata.app import no_cache
from lidarrmetadata.version_patch import _read_version


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
            return await send_file(assets_dir / "lmbridge-icon.png", mimetype="image/png")

    async def _lmbridge_root_route():
        replication_date = None
        try:
            vintage_providers = provider.get_providers_implementing(provider.DataVintageMixin)
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
            "metadata_version": fmt(lidarrmetadata.__version__),
            "branch": fmt(os.getenv("GIT_BRANCH")),
            "commit": fmt(os.getenv("COMMIT_HASH")),
            "replication_date": fmt(replication_date),
        }
        safe = {key: html.escape(val) for key, val in info.items()}
        base_path = (request.script_root or "").rstrip("/")
        version_url = f"{base_path}/version" if base_path else "/version"
        config_url = f"{base_path}/config/release-filter" if base_path else "/config/release-filter"
        icon_url = f"{base_path}/assets/lmbridge-icon.png" if base_path else "/assets/lmbridge-icon.png"

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
        <h1 class="hero-title">LM Bridge - Metadata Handler for Lidarr_</h1>
        <span class="hero-sub"><em>FAST • Local • Private</em></span>
      </div>
      <p class="subtitle">Bridge + metadata service details in one place.</p>
      <div class="grid">
        <div class="pill">
          <div class="label">LM Bridge Version</div>
          <div class="value">{safe["version"]}</div>
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
          <div class="label">Commit</div>
          <div class="value">{safe["commit"]}</div>
        </div>
        <div class="pill">
          <div class="label">Branch</div>
          <div class="value">{safe["branch"]}</div>
        </div>
      </div>
      <div class="links">
        <a class="link" href="{html.escape(version_url)}">Version JSON</a>
        <a class="link" href="{html.escape(config_url)}">Release Filter Config</a>
      </div>
      <div class="foot">Tip: Use <span class="accent">/album/&lt;mbid&gt;</span> to fetch release group JSON.</div>
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
