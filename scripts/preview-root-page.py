#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def build_preview_html() -> str:
    root = Path(__file__).resolve().parents[1]
    template_path = (
        root / "overlay" / "bridge" / "lidarrmetadata" / "assets" / "root.html"
    )
    template = template_path.read_text(encoding="utf-8")
    template = template.replace('href="/assets/root.css"', 'href="assets/root.css"')

    config_html = "\n".join(
        [
            '          <div class="config-row"><div class="config-label">Filtering Enabled</div><div class="config-value"><span class="config-value-text">Yes</span><button class="config-action" type="button" aria-label="More" data-config-menu><span class="config-action__inner">&#x25BE;</span></button></div></div>',
            '          <div class="config-row"><div class="config-label">Exclude Media Formats</div><div class="config-value"><span class="config-value-text">vinyl, cassette</span><button class="config-action" type="button" aria-label="More" data-config-menu><span class="config-action__inner">&#x25BE;</span></button></div></div>',
            '          <div class="config-row"><div class="config-label">Include Media Formats</div><div class="config-value"><span class="config-value-text">all</span><button class="config-action" type="button" aria-label="More" data-config-menu><span class="config-action__inner">&#x25BE;</span></button></div></div>',
            '          <div class="config-row"><div class="config-label">Max Media Count</div><div class="config-value"><span class="config-value-text">no limit</span><button class="config-action" type="button" aria-label="More" data-config-menu><span class="config-action__inner">&#x25BE;</span></button></div></div>',
            '          <div class="config-row"><div class="config-label">Prefer Media Type</div><div class="config-value"><span class="config-value-text">digital</span><button class="config-action" type="button" aria-label="More" data-config-menu><span class="config-action__inner">&#x25BE;</span></button></div></div>',
        ]
    )

    mbms_pills = "\n".join(
        [
            '          <div class="pill has-action">',
            '            <div class="label">MBMS PLUS VERSION</div>',
            '            <div class="value">1.2.3</div>',
            '            <a class="pill-button" href="https://github.com/HVR88/MBMS_PLUS" target="_blank" rel="noopener">Git</a>',
            "          </div>",
            '          <div class="pill">',
            '            <div class="label">MBMS Index Schedule</div>',
            '            <div class="value">daily @ 3:00&nbsp;<span class="ampm">AM</span></div>',
            "          </div>",
            '          <div class="pill">',
            '            <div class="label">MBMS Replication Schedule</div>',
            '            <div class="value">hourly @ :15</div>',
            "          </div>",
        ]
    )

    replacements = {
        "__ICON_URL__": "limbo-icon.png",
        "__LM_VERSION__": "1.9.7.10",
        "__LM_PLUGIN_VERSION__": "1.9.7.10",
        "__LM_PLUGIN_LABEL__": "Limbo Plugin",
        "__LM_PILL_CLASS__": "pill has-action",
        "__PLUGIN_PILL_CLASS__": "pill",
        "__LM_VERSION_BUTTON__": (
            '            <a class="pill-button update" href="https://github.com/HVR88/Limbo" target="_blank" rel="noopener">'
            '<span class="pill-button__inner">1.9.7.80</span></a>'
        ),
        "__PLUGIN_VERSION_BUTTON__": (
            '            <a class="pill-button update overlay" href="http://localhost:8686/system/plugins" target="_blank" rel="noopener">'
            '<span class="pill-button__inner">1.9.7.80</span></a>'
        ),
        "__LIDARR_VERSION_LABEL__": "LIDARR VERSION",
        "__LIDARR_VERSION__": "3.1.2.4913",
        "__LIDARR_PILL_CLASS__": "pill has-action",
        "__LIDARR_OPEN__": (
            '            <a class="pill-button" href="http://localhost:8686" target="_blank" rel="noopener">Open</a>'
        ),
        "__MBMS_REPLICATION_SCHEDULE__": "hourly @ :15",
        "__MBMS_INDEX_SCHEDULE__": "daily @ 3:00 AM",
        "__METADATA_VERSION__": "3.0.0",
        "__REPLICATION_DATE__": "2026-02-20 12:23 AM",
        "__REPLICATION_DATE_HTML__": '2026-02-20 12:23&nbsp;<span class="ampm">AM</span>',
        "__UPTIME__": "3h 12m",
        "__VERSION_URL__": "/version",
        "__CACHE_CLEAR_URL__": "/cache/clear",
        "__CACHE_EXPIRE_URL__": "/cache/expire",
        "__REPLICATION_START_URL__": "/replication/start",
        "__REPLICATION_STATUS_URL__": "/replication/status",
        "__THEME__": "dark",
        "__REPLICATION_BUTTON__": (
            '            <button class="pill-button" type="button" data-replication-url="/replication/start">'
            '<span class="pill-button__inner">Start</span></button>'
        ),
        "__REPLICATION_PILL_CLASS__": "pill has-action",
        "__INVALIDATE_APIKEY__": "",
        "__MBMS_URL__": "https://github.com/HVR88/MBMS_PLUS",
        "__CONFIG_HTML__": config_html,
        "__MBMS_PILLS__": mbms_pills,
    }

    for key, value in replacements.items():
        template = template.replace(key, value)

    return template


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    default_output = root / "dist" / "root-preview.html"
    css_source = root / "overlay" / "bridge" / "lidarrmetadata" / "assets" / "root.css"

    parser = argparse.ArgumentParser(
        description="Generate a local preview of Limbo landing page."
    )
    parser.add_argument(
        "output", nargs="?", default=str(default_output), help="Output HTML path"
    )
    parser.add_argument(
        "--open",
        action="store_true",
        help="Open the generated file (macOS: uses 'open').",
    )
    args = parser.parse_args()

    output_path = Path(args.output).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(build_preview_html(), encoding="utf-8")
    if css_source.exists():
        assets_dir = output_path.parent / "assets"
        assets_dir.mkdir(parents=True, exist_ok=True)
        (assets_dir / "root.css").write_text(
            css_source.read_text(encoding="utf-8"), encoding="utf-8"
        )
    print(output_path)
    if args.open:
        try:
            subprocess.run(["open", str(output_path)], check=False)
        except Exception:
            print("Could not open file automatically.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
