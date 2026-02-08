<p align="center">
  <img src="https://raw.githubusercontent.com/HVR88/lm-bridge/main/assets/lmbridge-icon.png" alt="LM Bridge" width="500" />
</p>

# Lidarr/MusiBrainz Bridge

This repo builds a standalone Lidarr Metadata Server image that bridges to a separately-run MusicBrainz mirror. It overlays the fork `HVR88/LidarrAPI.Metadata` without modifying the upstream code.

**What This Repo Does**

1. Builds an AMD64-focused container image for Lidarr Metadata Server.
2. Adds a bridge config layer so you can point at your MusicBrainz mirror and Solr.
3. Keeps the project outside the MusicBrainz mirror stack.
4. Provides an **init service** that prepares the cache DB and indexes on first start (using the same image).

**What This Repo Does Not Do**

1. It does not build or run the MusicBrainz mirror stack.
2. It does not change MusicBrainz mirror defaults unless you explicitly configure overrides.

**Key Defaults**

1. MusicBrainz DB defaults to `musicbrainz:musicbrainz` unless you override.
2. LMBRIDGE cache DB defaults to `lm_cache_db` with user `abc` / password `abc`.

## Configuration

Edit `overlay/deploy/lm-bridge-settings.yml` to match your environment. This file is a standalone Compose file for the LM-Bridge container.

Important fields:

- `PROVIDERS__MUSICBRAINZDBPROVIDER__1__DB_HOST` should point to your MusicBrainz DB host or service name.
- `PROVIDERS__SOLRSEARCHPROVIDER__1__SEARCH_SERVER` should point to your Solr endpoint.
- `POSTGRES_CACHE_HOST` should point to the Postgres host that will hold `lm_cache_db`.

If you want to use Docker service names like `db`, `search`, or `redis`, run this container on the same Docker network as your MusicBrainz mirror.

## Step 8: Initialize LMBRIDGE Cache DB and MusicBrainz Indexes

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
LMBRIDGE_CACHE_DB=lm_cache_db \
LMBRIDGE_CACHE_USER=abc \
LMBRIDGE_CACHE_PASSWORD=abc \
scripts/init-mbdb.sh
```

The script also creates the cache tables (`fanart`, `tadb`, `wikipedia`, `artist`, `album`, `spotify`) inside `lm_cache_db` to avoid runtime errors like `relation "tadb" does not exist`.

## Build And Run

## Clone

Recommended (pulls the upstream submodule automatically):

```bash
git clone --recurse-submodules https://github.com/HVR88/lm-bridge.git
```

If you already cloned without submodules:

```bash
cd lm-bridge
git submodule update --init --recursive
```

Use the helper script (defaults to `linux/amd64` and tag `lm-bridge:dev`):

```bash
scripts/build-image.sh
```

Override defaults:

```bash
PLATFORMS=linux/amd64 LMBRIDGE_IMAGE=lm-bridge:dev scripts/build-image.sh
```

Multi-arch build (push required):

```bash
PLATFORMS=linux/amd64,linux/arm64 PUSH=1 LMBRIDGE_IMAGE=lm-bridge:dev scripts/build-image.sh
```

Start the container using the provided settings file (Compose will build the image if it doesn't exist locally):

```bash
docker compose -f overlay/deploy/lm-bridge-settings.yml up -d
```

Note: Compose defaults to `lm-bridge:dev`. Build locally first, or set `LMBRIDGE_IMAGE` to a tag you’ve already built or pushed.

If you want to run it on the **same Docker network** as your MusicBrainz mirror and auto-run the **init container**, use the repo’s root `docker-compose.yml` (it’s already there if you cloned the repo). Then run:

```bash
MB_NETWORK=musicbrainz_default docker compose -f docker-compose.yml up -d
```

The `init` container will exit after completing setup. That is expected.

If you use custom image tags, set them via environment:

```bash
LMBRIDGE_IMAGE=lm-bridge:dev \
MB_NETWORK=musicbrainz_default \
docker compose -f docker-compose.yml up -d
```

Note: `MB_DB_USER` must have permission to create roles and databases (the mirror's primary Postgres user usually does).

If your Docker Compose version does not support `include` (used by `docker-compose.yml`), you can still run the underlying file directly:

```bash
MB_NETWORK=musicbrainz_default docker compose -f overlay/deploy/lm-bridge-compose.yml up -d
```

## Verify

Once running, test a known artist endpoint:

```bash
curl http://host-ip:5001/artist/1921c28c-ec61-4725-8e35-38dd656f7923
```

If the bridge is configured correctly, you should see JSON metadata from your mirror.

If it fails, check logs:

```bash
docker compose logs -f api
```

## Docker Hub Release (Manual)

This repo includes a GitHub Actions workflow that can build and push the image to Docker Hub on demand.

Required secrets:

- `DOCKERHUB_USERNAME`
- `DOCKERHUB_TOKEN`

In GitHub: **Actions → Docker Hub Release → Run workflow**.
