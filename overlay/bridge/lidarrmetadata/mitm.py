import importlib
import importlib.util
import json
import logging
import os
from typing import Any, Callable, Dict, Optional

from quart import request

logger = logging.getLogger(__name__)

_BUILTIN_TRANSFORM: Optional[Callable[[Any, Dict[str, Any]], Any]] = None
_CUSTOM_TRANSFORM: Optional[Callable[[Any, Dict[str, Any]], Any]] = None
_CUSTOM_LOAD_ATTEMPTED = False


def is_enabled() -> bool:
    return bool(
        _BUILTIN_TRANSFORM
        or os.environ.get("LMBRIDGE_MITM_AFTER_MODULE")
        or os.environ.get("LMBRIDGE_MITM_AFTER_PATH")
        or os.environ.get("LMBRIDGE_MITM_MODULE")
        or os.environ.get("LMBRIDGE_MITM_PATH")
    )


def _load_custom_transform() -> Optional[Callable[[Any, Dict[str, Any]], Any]]:
    global _CUSTOM_TRANSFORM, _CUSTOM_LOAD_ATTEMPTED
    if _CUSTOM_LOAD_ATTEMPTED:
        return _CUSTOM_TRANSFORM
    _CUSTOM_LOAD_ATTEMPTED = True

    module_name = os.environ.get("LMBRIDGE_MITM_AFTER_MODULE") or os.environ.get("LMBRIDGE_MITM_MODULE")
    file_path = os.environ.get("LMBRIDGE_MITM_AFTER_PATH") or os.environ.get("LMBRIDGE_MITM_PATH")

    if module_name:
        try:
            module = importlib.import_module(module_name)
        except Exception:
            logger.exception("LM-Bridge MITM: failed to import module %s", module_name)
            return None

        transform = getattr(module, "transform_payload", None)
        if callable(transform):
            _CUSTOM_TRANSFORM = transform
            return _CUSTOM_TRANSFORM
        logger.error("LM-Bridge MITM: module %s missing transform_payload(payload, context)", module_name)
        return None

    if file_path:
        try:
            spec = importlib.util.spec_from_file_location("lmbridge_mitm_hook", file_path)
            if spec is None or spec.loader is None:
                logger.error("LM-Bridge MITM: cannot load hook file %s", file_path)
                return None
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        except Exception:
            logger.exception("LM-Bridge MITM: failed to load hook file %s", file_path)
            return None

        transform = getattr(module, "transform_payload", None)
        if callable(transform):
            _CUSTOM_TRANSFORM = transform
            return _CUSTOM_TRANSFORM
        logger.error("LM-Bridge MITM: hook file %s missing transform_payload(payload, context)", file_path)
        return None

    return None


async def apply_response(response):
    if not is_enabled():
        return response

    custom_transform = _load_custom_transform()
    if _BUILTIN_TRANSFORM is None and custom_transform is None:
        return response

    content_type = response.content_type or ""
    if "application/json" not in content_type:
        return response

    try:
        raw = await response.get_data()
    except Exception:
        logger.exception("LM-Bridge MITM: failed reading response body")
        return response

    if not raw:
        return response

    try:
        payload = json.loads(raw)
    except Exception:
        return response

    context = {
        "path": request.path,
        "method": request.method,
        "query": dict(request.args),
        "headers": {k: v for k, v in request.headers.items()},
    }

    current = payload
    for transform in (_BUILTIN_TRANSFORM, custom_transform):
        if transform is None:
            continue
        try:
            updated = transform(current, context)
        except Exception:
            logger.exception("LM-Bridge MITM: transform_payload failed")
            continue
        if updated is not None:
            current = updated

    if current is payload:
        return response

    try:
        response.set_data(json.dumps(current, separators=(",", ":")))
    except Exception:
        logger.exception("LM-Bridge MITM: failed to update response body")
        return response

    return response
