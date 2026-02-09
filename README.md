<p align="center">
  <img src="https://raw.githubusercontent.com/HVR88/LM-Bridge/main/assets/lmbridge-icon.png" alt="LM Bridge" width="500" />
</p>

# Lidarr/MusicBrainz Bridge

This repo Contains two complimentary parts that run 100% locally:

1. A Lidarr Metadata Server image that bridges to a MusicBrainz mirror
2. A Plugin to set the URL of this bridge container in Lidarr

**_Thanks to blampe and Typnull for inspiration_** : this wouldn't have been possible without leveraging their previous work

**_If you just want to run the LM Bridge, don't use this repo - it's for building from source_**

_You'll want only the **Compose** file above plus the **Docker Container** below:_

> [!NOTE]
>
> ## **[espressomatic/LMBridge_docker](https://hub.docker.com/r/espressomatic/lmbridge_docker)**

Likewise, you should already be running a [Lidarr](https://hub.docker.com/r/linuxserver/lidarr) plugins-enabled release plus [MusicBrainz Mirror](https://github.com/metabrainz/musicbrainz-docker) server _(with materialized tables AND fully indexed db)_

> [!IMPORTANT]
>
> _Only follow the above MirrorBrainz Mirror Server instructions_<br>
> AGAIN: do not follow anyone else's instructions to locally set up MusicBrainz
> <br><br>

## Repo Summary

**What This Repo Does**

1. Builds an amd64 container image with Lidarr Metadata Server
2. Adds a bridge config so you can point at your MusicBrainz mirror
3. Builds a Lidarr Plugin to point Lidarr at this self-hosted API

**What This Repo Doesn't Do**

1. **It's not a ready-to-deploy container image**
2. It doesn't build or run the MusicBrainz mirror stack
3. It doesn't build or run Lidarr

**Requirements**

1. Running Lidarr _nightly_ or _plugins_ branch
2. Running MusicBrainz mirror server
3. Building requires the lidarr source tree (submodule in plugin folder)

**Key Defaults**

1. MusicBrainz DB defaults to `musicbrainz:musicbrainz` unless you override
2. LMBRIDGE cache DB defaults to `lm_cache_db` with user `abc` / password `abc`

## Lidarr API Plugin (Required)

This repo includes a plugin that will appear in Lidarr's Metadata settings page after being installed. Lidarr must have this plugin installed to talk to the bridge on your network.

**Install the Plugin**

1. In Lidarr, open **System → Plugins**
2. Paste this repo URL (`https://github.com/HVR88/LM-Bridge`) into the GitHub URL box and click **Install**.
3. Restart Lidarr when prompted.

If you don't see a System → Plugins page in your Lidarr, switch to the `nightly` branch, such as **[LinuxServer.io's](https://hub.docker.com/r/linuxserver/lidarr)**

**Enable the Plugin**

1. In Lidarr, open **Settings → Metadata**
2. Click **Lidarr/MusicBrainz Bridge API**.
3. Make sure the Enable check-box is checked
4. Enter the URL of the LM Bridge container : 5001
5. Click Save

Lidarr is now using the Bridge API and you should see lightning-fast queries to your MusicBrainz mirror.

## Configuration of the LM Bridge Container

Edit `overlay/deploy/lm-bridge-settings.yml` to match your environment. This file is a standalone Compose file for the LM-Bridge container.

Important fields:

- `PROVIDERS__MUSICBRAINZDBPROVIDER__1__DB_HOST` should point to your MusicBrainz DB host or service name.
- `PROVIDERS__SOLRSEARCHPROVIDER__1__SEARCH_SERVER` should point to your Solr endpoint.
- `POSTGRES_CACHE_HOST` should point to the Postgres host that will hold `lm_cache_db`.

If you want to use Docker service names like `db`, `search`, or `redis`, run this container on the same Docker network as your MusicBrainz mirror.

For best metadata enrichment, set API keys for TheAudioDB and Fanart.tv via `TADB_KEY` and `FANART_KEY` (in `overlay/deploy/lm-bridge-settings.yml` or via environment variables).

## Initialize LMBRIDGE Cache DB and MusicBrainz Indexes

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

## Technical - Build And Run

## Clone

Recommended (pulls the upstream submodule automatically):

```bash
git clone --recurse-submodules https://github.com/HVR88/LM-Bridge.git
```

If you already cloned without submodules:

```bash
cd lm-bridge
git submodule update --init --recursive
```

Use the helper script (defaults to `linux/amd64` and tag `lm-bridge:latest`):

```bash
scripts/build-image.sh
```

Override defaults:

```bash
PLATFORMS=linux/amd64 LMBRIDGE_IMAGE=lm-bridge:latest scripts/build-image.sh
```

Multi-arch build (push required):

```bash
PLATFORMS=linux/amd64,linux/arm64 PUSH=1 LMBRIDGE_IMAGE=lm-bridge:latest scripts/build-image.sh
```

Start the container using the provided settings file (Compose will build the image if it doesn't exist locally):

```bash
docker compose -f overlay/deploy/lm-bridge-settings.yml up -d
```

Note: Compose defaults to `lm-bridge:latest`. Build locally first, or set `LMBRIDGE_IMAGE` to a tag you’ve already built or pushed.

If you want to run it on the **same Docker network** as your MusicBrainz mirror and auto-run the **init container**, use the repo’s root `docker-compose.yml` (it’s already there if you cloned the repo). Then run:

```bash
MB_NETWORK=musicbrainz_default docker compose -f docker-compose.yml up -d
```

The `init` container will exit after completing setup. That is expected.

If you use custom image tags, set them via environment:

```bash
LMBRIDGE_IMAGE=lm-bridge:latest \
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
