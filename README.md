# Lidarr Metadata Distro

This repo builds a standalone Lidarr Metadata Server image that bridges to a separately-run MusicBrainz mirror. It overlays upstream `LidarrAPI.Metadata` without modifying upstream code.

**What This Repo Does**
1. Builds an AMD64-focused container image for Lidarr Metadata Server.
2. Adds a bridge config layer so you can point at your MusicBrainz mirror and Solr.
3. Keeps the project outside the MusicBrainz mirror stack.
4. Provides an **init container** that prepares the cache DB and indexes on first start.

**What This Repo Does Not Do**
1. It does not build or run the MusicBrainz mirror stack.
2. It does not change MusicBrainz mirror defaults unless you explicitly configure overrides.

**Key Defaults**
1. MusicBrainz DB defaults to `musicbrainz:musicbrainz` unless you override.
2. LMD cache DB defaults to `lm_cache_db` with user `abc` / password `abc`.

## Configuration

Edit `overlay/deploy/lmd-settings.yml` to match your environment. This file is a standalone Compose file for the LMD container.

Important fields:
- `PROVIDERS__MUSICBRAINZDBPROVIDER__1__DB_HOST` should point to your MusicBrainz DB host or service name.
- `PROVIDERS__SOLRSEARCHPROVIDER__1__SEARCH_SERVER` should point to your Solr endpoint.
- `POSTGRES_CACHE_HOST` should point to the Postgres host that will hold `lm_cache_db`.

If you want to use Docker service names like `db`, `search`, or `redis`, run this container on the same Docker network as your MusicBrainz mirror.

## Step 8: Initialize LMD Cache DB and MusicBrainz Indexes

This repo includes `scripts/init-mbdb.sh` to handle the database prep that used to be done inside the mirror stack.

Run it once after your MusicBrainz mirror is up:

```bash
MB_DB_HOST=your-mb-host \
MB_DB_USER=musicbrainz \
MB_DB_PASSWORD=musicbrainz \
scripts/init-mbdb.sh
```

If you do not have `psql` installed locally, the script will use a temporary `postgres` container. In that case, provide the MusicBrainz Docker network so it can resolve service names like `db`:

```bash
MB_DB_HOST=db \
MB_DB_NETWORK=musicbrainz_default \
scripts/init-mbdb.sh
```

You can change cache DB settings if needed:

```bash
LMD_CACHE_DB=lm_cache_db \
LMD_CACHE_USER=abc \
LMD_CACHE_PASSWORD=abc \
scripts/init-mbdb.sh
```

The script also creates the cache tables (`fanart`, `tadb`, `wikipedia`, `artist`, `album`, `spotify`) inside `lm_cache_db` to avoid runtime errors like `relation "tadb" does not exist`.

## Build And Run

Use the helper script (defaults to `linux/amd64`):

```bash
scripts/build-image.sh
```

Override defaults:

```bash
PLATFORMS=linux/amd64 IMAGE=hvr88/lidarr.metadata:dev scripts/build-image.sh
```

Multi-arch build (push required):

```bash
PLATFORMS=linux/amd64,linux/arm64 PUSH=1 IMAGE=hvr88/lidarr.metadata:dev scripts/build-image.sh
```

Start the container using the provided settings file:

```bash
docker compose -f overlay/deploy/lmd-settings.yml up -d
```

If you want to run it on the **same Docker network** as your MusicBrainz mirror, use the compose file with an external network reference. This also runs the **init container** automatically on startup:

```bash
MB_NETWORK=musicbrainz_default docker compose -f overlay/deploy/lmd-compose.yml up -d
```

The `lmd-init` container will exit after completing setup. That is expected.

If you use custom image tags, set them via environment:

```bash
LMD_IMAGE=hvr88/lidarr.metadata:dev \
LMD_INIT_IMAGE=hvr88/lidarr.metadata-init:dev \
MB_NETWORK=musicbrainz_default \
docker compose -f overlay/deploy/lmd-compose.yml up -d
```

Note: `MB_DB_USER` must have permission to create roles and databases (the mirror's primary Postgres user usually does).

## Verify

Once running, test a known artist endpoint:

```bash
curl http://host-ip:5001/artist/1921c28c-ec61-4725-8e35-38dd656f7923
```

If the bridge is configured correctly, you should see JSON metadata from your mirror.

If it fails, check logs:

```bash
docker logs -f lmd
```
