import importlib
import importlib.util
import logging
import os
from typing import Any, Callable, Dict, Optional, Tuple

import asyncio
import asyncpg
import contextvars

logger = logging.getLogger(__name__)

_DEFAULT_HOOK_MODULE = "lidarrmetadata.release_filters"
_BUILTIN_BEFORE: Optional[Callable[[str, Tuple[Any, ...], Dict[str, Any]], Tuple[str, Tuple[Any, ...]]]] = None
_BUILTIN_AFTER: Optional[Callable[[Any, Dict[str, Any]], Any]] = None
_CUSTOM_BEFORE: Optional[Callable[[str, Tuple[Any, ...], Dict[str, Any]], Tuple[str, Tuple[Any, ...]]]] = None
_CUSTOM_AFTER: Optional[Callable[[Any, Dict[str, Any]], Any]] = None
_BUILTIN_LOAD_ATTEMPTED = False
_CUSTOM_LOAD_ATTEMPTED = False
_SQL_FILE = contextvars.ContextVar("lmbridge_sql_file", default=None)


def is_enabled() -> bool:
    return True


def _load_builtin() -> None:
    global _BUILTIN_BEFORE, _BUILTIN_AFTER, _BUILTIN_LOAD_ATTEMPTED
    if _BUILTIN_LOAD_ATTEMPTED:
        return
    _BUILTIN_LOAD_ATTEMPTED = True

    try:
        module = importlib.import_module(_DEFAULT_HOOK_MODULE)
    except Exception:
        logger.exception("LM-Bridge DB hooks: failed to import built-in module %s", _DEFAULT_HOOK_MODULE)
        return

    before = getattr(module, "before_query", None)
    after = getattr(module, "after_query", None)

    if callable(before):
        _BUILTIN_BEFORE = before
    if callable(after):
        _BUILTIN_AFTER = after

    if _BUILTIN_BEFORE is None and _BUILTIN_AFTER is None:
        logger.error(
            "LM-Bridge DB hooks: built-in module must define before_query(sql, args, context) or "
            "after_query(results, context)"
        )


def _load_custom() -> None:
    global _CUSTOM_BEFORE, _CUSTOM_AFTER, _CUSTOM_LOAD_ATTEMPTED
    if _CUSTOM_LOAD_ATTEMPTED:
        return
    _CUSTOM_LOAD_ATTEMPTED = True

    module_name_env = os.environ.get("LMBRIDGE_DB_HOOK_AFTER_MODULE") or os.environ.get("LMBRIDGE_DB_HOOK_MODULE")
    file_path = os.environ.get("LMBRIDGE_DB_HOOK_AFTER_PATH") or os.environ.get("LMBRIDGE_DB_HOOK_PATH")

    if module_name_env == _DEFAULT_HOOK_MODULE and not file_path:
        logger.warning(
            "LM-Bridge DB hooks: %s is built-in and applied automatically; "
            "use LMBRIDGE_DB_HOOK_AFTER_MODULE for custom hooks.",
            _DEFAULT_HOOK_MODULE,
        )
        return

    module = None
    if file_path:
        try:
            spec = importlib.util.spec_from_file_location("lmbridge_db_hooks", file_path)
            if spec is None or spec.loader is None:
                logger.error("LM-Bridge DB hooks: cannot load hook file %s", file_path)
                return
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        except Exception:
            logger.exception("LM-Bridge DB hooks: failed to load hook file %s", file_path)
            return
    elif module_name_env:
        try:
            module = importlib.import_module(module_name_env)
        except Exception:
            logger.exception("LM-Bridge DB hooks: failed to import module %s", module_name_env)
            return

    if module is None:
        return

    before = getattr(module, "before_query", None)
    after = getattr(module, "after_query", None)

    if callable(before):
        _CUSTOM_BEFORE = before
    if callable(after):
        _CUSTOM_AFTER = after

    if _CUSTOM_BEFORE is None and _CUSTOM_AFTER is None:
        logger.error(
            "LM-Bridge DB hooks: module must define before_query(sql, args, context) or "
            "after_query(results, context)"
        )


def set_sql_file(sql_file: Optional[str]):
    return _SQL_FILE.set(sql_file)


def reset_sql_file(token) -> None:
    _SQL_FILE.reset(token)


def get_sql_file() -> Optional[str]:
    return _SQL_FILE.get()


def _apply_before_hook(
    hook: Optional[Callable[[str, Tuple[Any, ...], Dict[str, Any]], Tuple[str, Tuple[Any, ...]]]],
    sql: str,
    args: Tuple[Any, ...],
    context: Dict[str, Any],
    pool_key: str,
) -> Tuple[str, Tuple[Any, ...], str]:
    if hook is None:
        return sql, args, pool_key

    try:
        result = hook(sql, args, context)
    except Exception:
        logger.exception("LM-Bridge DB hooks: before_query failed")
        return sql, args, pool_key

    if result is None:
        return sql, args, pool_key

    try:
        new_sql, new_args, *rest = result
    except Exception:
        logger.error("LM-Bridge DB hooks: before_query must return (sql, args) or None")
        return sql, args, pool_key

    if not isinstance(new_args, tuple):
        new_args = tuple(new_args)

    new_pool_key = pool_key
    if rest:
        extra = rest[0]
        if isinstance(extra, str):
            new_pool_key = extra
        elif isinstance(extra, dict):
            new_pool_key = str(extra.get("pool", pool_key))

    return new_sql, new_args, new_pool_key


def apply_before(
    sql: str, args: Tuple[Any, ...], context: Dict[str, Any]
) -> Tuple[str, Tuple[Any, ...], str]:
    if not is_enabled():
        return sql, args, "default"
    _load_builtin()
    _load_custom()

    current_sql, current_args, pool_key = _apply_before_hook(
        _BUILTIN_BEFORE, sql, args, context, "default"
    )
    current_sql, current_args, pool_key = _apply_before_hook(
        _CUSTOM_BEFORE, current_sql, current_args, context, pool_key
    )

    return current_sql, current_args, pool_key


def apply_after(results: Any, context: Dict[str, Any]) -> Any:
    if not is_enabled():
        return results
    _load_builtin()
    _load_custom()

    current = results
    for hook in (_BUILTIN_AFTER, _CUSTOM_AFTER):
        if hook is None:
            continue
        try:
            updated = hook(current, context)
        except Exception:
            logger.exception("LM-Bridge DB hooks: after_query failed")
            continue
        if updated is not None:
            current = updated

    return current


def _pool_env(pool_key: str, suffix: str) -> Optional[str]:
    key = pool_key.upper()
    return os.environ.get(f"LMBRIDGE_DB_POOL_{key}_{suffix}")


async def get_pool(provider, pool_key: str):
    if pool_key == "default":
        return await provider._get_pool()

    pools = getattr(provider, "_lmbridge_pools", None)
    if pools is None:
        pools = {}
        provider._lmbridge_pools = pools

    locks = getattr(provider, "_lmbridge_pool_locks", None)
    if locks is None:
        locks = {}
        provider._lmbridge_pool_locks = locks

    if pool_key in pools:
        return pools[pool_key]

    lock = locks.get(pool_key)
    if lock is None:
        lock = asyncio.Lock()
        locks[pool_key] = lock

    async with lock:
        if pool_key in pools:
            return pools[pool_key]

        host = _pool_env(pool_key, "HOST")
        port = _pool_env(pool_key, "PORT")
        user = _pool_env(pool_key, "USER")
        password = _pool_env(pool_key, "PASSWORD")
        db_name = _pool_env(pool_key, "DB_NAME")

        if not host or not db_name:
            logger.error(
                "LM-Bridge DB hooks: pool %s missing HOST or DB_NAME; falling back to default",
                pool_key,
            )
            return await provider._get_pool()

        try:
            port_value = int(port) if port else provider._db_port
            pool = await asyncpg.create_pool(
                host=host,
                port=port_value,
                user=user or provider._db_user,
                password=password or provider._db_password,
                database=db_name,
                init=provider.uuid_as_str,
                statement_cache_size=0,
            )
        except Exception:
            logger.exception("LM-Bridge DB hooks: failed to create pool %s", pool_key)
            return await provider._get_pool()

        pools[pool_key] = pool
        return pool
