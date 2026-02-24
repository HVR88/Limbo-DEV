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
    template = template.replace(
        'href="/assets/root.css"', 'href="assets/root.css?v=preview"'
    )
    svg_dir = template_path.parent

    def read_svg(name: str) -> str:
        try:
            content = (svg_dir / name).read_text(encoding="utf-8")
        except Exception:
            return ""
        return content.replace(
            '<?xml version="1.0" encoding="UTF-8" standalone="no"?>', ""
        ).strip()

    menu_icon = read_svg("limbo-arrows-updn.svg")
    config_html = "\n".join(
        [
            f'          <div class="config-row"><div class="config-label"><span data-filter-label-enabled>Filtering Enabled</span><span data-filter-label-disabled style="display:none">Filtering Disabled</span></div><div class="config-value"><label class="config-toggle"><input type="checkbox" data-config-enabled checked /><span class="config-toggle__track" aria-hidden="true"><span class="config-toggle__thumb"></span></span></label></div></div>',
            f'          <div class="config-row"><div class="config-label">Max Media Count</div><div class="config-value"><span class="config-value-text">no limit</span><button class="config-action" type="button" aria-label="More" data-config-menu><span class="config-action__inner">{menu_icon}</span></button></div></div>',
            f'          <div class="config-row"><div class="config-label">Prefer Media Type</div><div class="config-value"><span class="config-value-text">digital</span><button class="config-action" type="button" aria-label="More" data-config-menu><span class="config-action__inner">{menu_icon}</span></button></div></div>',
            f'          <div class="config-row"><div class="config-label">Media Types</div><div class="config-value"><span class="config-value-text">vinyl, cassette</span><button class="config-action" type="button" aria-label="More" data-config-menu><span class="config-action__inner">{menu_icon}</span></button></div></div>',
            '          <div class="config-row"><div class="config-label">&nbsp;</div><div class="config-value"><span class="config-value-text">&nbsp;</span></div></div>',
        ]
    )

    mbms_pills = "\n".join(
        [
            '          <button type="button" class="pill has-action" data-pill-href="https://github.com/HVR88/MBMS_PLUS">',
            '            <div class="label">MBMS PLUS VERSION</div>',
            '            <div class="value has-update"><span class="version-current">1.2.3</span><span class="version-update">&rarr; NEW 1.2.4</span></div>',
            "",
            f"            <span class=\"pill-arrow\" aria-hidden=\"true\">{read_svg('limbo-tall-arrow.svg')}</span>",
            "          </button>",
            '          <button type="button" class="pill" data-pill-href="" data-modal-open="schedule-indexer">',
            '            <div class="label">MBMS Index Schedule</div>',
            '            <div class="value">daily @ 3:00&nbsp;<span class="ampm">AM</span></div>',
            f"            <span class=\"pill-arrow\" aria-hidden=\"true\">{read_svg('limbo-tall-arrow.svg')}</span>",
            "          </button>",
            '          <button type="button" class="pill" data-pill-href="" data-modal-open="schedule-replication">',
            '            <div class="label">MBMS Replication Schedule</div>',
            '            <div class="value">hourly @ :15</div>',
            f"            <span class=\"pill-arrow\" aria-hidden=\"true\">{read_svg('limbo-tall-arrow.svg')}</span>",
            "          </button>",
        ]
    )

    replacements = {
        "__ICON_URL__": "limbo-icon.png",
        "__LM_VERSION__": "1.9.7.10",
        "__LM_PLUGIN_VERSION__": "1.9.7.10",
        "__LM_PLUGIN_LABEL__": "Limbo Plugin",
        "__LM_PILL_HTML__": "\n".join(
            [
                '          <button type="button" class="pill has-action" data-pill-href="https://github.com/HVR88/Limbo_Bridge">',
                '            <div class="label">Limbo Version</div>',
                '            <div class="value has-update"><span class="version-current">1.9.7.10</span><span class="version-update">&rarr; NEW 1.9.7.12</span></div>',
                f"            <span class=\"pill-arrow\" aria-hidden=\"true\">{read_svg('limbo-tall-arrow.svg')}</span>",
                "          </button>",
            ]
        ),
        "__LIDARR_PILL_HTML__": "\n".join(
            [
                '          <button type="button" class="pill" disabled>',
                '            <div class="label">LIDARR VERSION (LAST SEEN)</div>',
                '            <div class="value">3.1.2.4913</div>',
                "          </button>",
            ]
        ),
        "__REPLICATION_PILL_HTML__": "\n".join(
            [
                '          <button type="button" class="pill has-action" data-replication-pill data-pill-href="/replication/start">',
                '            <div class="label">Last Replication</div>',
                '            <div class="value replication-date" data-replication-value>2026-02-20 12:23&nbsp;<span class="ampm">AM</span></div>',
                f"            <span class=\"pill-arrow\" aria-hidden=\"true\">{read_svg('limbo-tall-arrow.svg')}</span>",
                "          </button>",
            ]
        ),
        "__PLUGIN_PILL_CLASS__": "pill",
        "__LIDARR_VERSION_LABEL__": "LIDARR VERSION",
        "__LIDARR_VERSION__": "3.1.2.4913",
        "__LIDARR_PILL_CLASS__": "pill has-action",
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
        "__REPLICATION_PILL_CLASS__": "pill has-action",
        "__LIMBO_APIKEY__": "",
        "__SETTINGS_ICON__": read_svg("limbo-settings.svg"),
        "__THEME_ICON_DARK__": read_svg("limbo-dark.svg"),
        "__THEME_ICON_LIGHT__": read_svg("limbo-light.svg"),
        "__TALL_ARROW_ICON__": read_svg("limbo-tall-arrow.svg"),
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
        svg_source_dir = css_source.parent
        for svg_path in svg_source_dir.glob("*.svg"):
            (assets_dir / svg_path.name).write_text(
                svg_path.read_text(encoding="utf-8"), encoding="utf-8"
            )
        icon_path = css_source.parent / "limbo-icon.png"
        if icon_path.exists():
            (assets_dir / icon_path.name).write_bytes(icon_path.read_bytes())
    print(output_path)
    if args.open:
        try:
            subprocess.run(["open", str(output_path)], check=False)
        except Exception:
            print("Could not open file automatically.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
