# LM-Bridge Hooks (After Built-In Processing)

This file documents the hook system you can enable via environment variables to run *after* LM-Bridge’s built-in processing.

## What Hooks Are For
Hooks let you add small, isolated transformations without modifying LM-Bridge core code. Typical uses include:
- Filtering or reshaping release data before it reaches Lidarr.
- Adding or removing fields in JSON responses.
- Routing specific SQL queries to a separate database.
- Logging or auditing query or response payloads.

There are two hook points:
1. **DB hooks** (run during MusicBrainz DB queries).
2. **MITM hooks** (run on JSON HTTP responses to Lidarr).

## Execution Order
- Built-in logic runs first.
- Custom hooks run second (your code is always *after* LM-Bridge’s built-in transforms).

## DB Hook
**Entry points**
- `LMBRIDGE_DB_HOOK_AFTER_MODULE`
- `LMBRIDGE_DB_HOOK_AFTER_PATH`

**Hook functions**
Your module should implement either (or both):
- `before_query(sql, args, context) -> (sql, args) | (sql, args, pool_key) | None`
- `after_query(results, context) -> results | None`

**Context fields**
- `provider`: provider class name
- `sql`: SQL string (may be modified by earlier hooks)
- `args`: SQL args tuple (may be modified by earlier hooks)
- `sql_file`: SQL filename when known
- `pool_key`: pool used for the primary query

**Pool routing**
`before_query` can return a `pool_key` to route a query to another DB pool configured via:
- `LMBRIDGE_DB_POOL_<KEY>_HOST`
- `LMBRIDGE_DB_POOL_<KEY>_PORT`
- `LMBRIDGE_DB_POOL_<KEY>_USER`
- `LMBRIDGE_DB_POOL_<KEY>_PASSWORD`
- `LMBRIDGE_DB_POOL_<KEY>_DB_NAME`

If a hook raises an exception, LM-Bridge logs the error and continues with the unmodified data.

### DB Hook Example 1: Filter out a format in release data
```python
# /config/hooks/db_filter.py

def after_query(results, context):
    if context.get("sql_file") != "release_group_by_id.sql":
        return None

    updated = []
    for row in results or []:
        album = row.get("album")
        if not album:
            updated.append(row)
            continue
        releases = album.get("Releases") or album.get("releases")
        if isinstance(releases, list):
            filtered = [r for r in releases if "vinyl" not in str(r).lower()]
            if "Releases" in album:
                album["Releases"] = filtered
            else:
                album["releases"] = filtered
        updated.append(row)

    return updated
```
Env:
```
LMBRIDGE_DB_HOOK_AFTER_PATH=/config/hooks/db_filter.py
```

### DB Hook Example 2: Route a query to a separate DB pool
```python
# /config/hooks/db_route.py

def before_query(sql, args, context):
    if context.get("sql_file") == "artist_by_id.sql":
        return sql, args, "discogs"
    return None
```
Env:
```
LMBRIDGE_DB_HOOK_AFTER_PATH=/config/hooks/db_route.py
LMBRIDGE_DB_POOL_DISCOGS_HOST=discogs-db
LMBRIDGE_DB_POOL_DISCOGS_PORT=5432
LMBRIDGE_DB_POOL_DISCOGS_USER=discogs
LMBRIDGE_DB_POOL_DISCOGS_PASSWORD=secret
LMBRIDGE_DB_POOL_DISCOGS_DB_NAME=discogs_db
```

## MITM Hook (Response Transform)
**Entry points**
- `LMBRIDGE_MITM_AFTER_MODULE`
- `LMBRIDGE_MITM_AFTER_PATH`

**Hook function**
- `transform_payload(payload, context) -> payload | None`

**Context fields**
- `path`: request path
- `method`: HTTP method
- `query`: request query params
- `headers`: request headers

This hook only runs for JSON responses. If your function returns `None`, LM-Bridge keeps the original payload.

### MITM Hook Example: Remove a field from all responses
```python
# /config/hooks/mitm_strip.py

def transform_payload(payload, context):
    if isinstance(payload, dict) and "debug" in payload:
        payload = dict(payload)
        payload.pop("debug", None)
    return payload
```
Env:
```
LMBRIDGE_MITM_AFTER_PATH=/config/hooks/mitm_strip.py
```

## Notes
- Custom hooks always run after built-in transformations.
- Use the “AFTER” environment variables shown above for custom hooks.
- If you want to disable custom hooks, simply leave those env vars unset.
