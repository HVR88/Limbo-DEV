import os
from pathlib import Path


def _read_version() -> str:
    env_version = os.environ.get("LMBRIDGE_VERSION")
    if env_version:
        return env_version.strip()

    version_path = Path(os.environ.get("LMBRIDGE_VERSION_FILE", "/metadata/VERSION"))
    try:
        return version_path.read_text().strip()
    except OSError:
        return "unknown"


def register_version_route() -> None:
    from lidarrmetadata import app as upstream_app
    from quart import jsonify

    for rule in upstream_app.app.url_map.iter_rules():
        if rule.rule == "/version":
            return

    @upstream_app.app.route("/version", methods=["GET"])
    async def _lmbridge_version_route():
        return jsonify({"version": _read_version()})
