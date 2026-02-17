<p align="center">
  <img src="https://raw.githubusercontent.com/HVR88/LM-Bridge-DEV/main/assets/lmbridge-icon.png" alt="LM Bridge" width="250" />
</p>

# LM Bridge Development Source

**A Local API Bridge - _FAST_ queries, no remote server issues**

**_This is the source repo to build the LM-Bridge project_**
and contains two complimentary parts that run 100% locally:

1. A Lidarr Metadata Server image that bridges to a MusicBrainz mirror
2. A Plugin to set the URL of this bridge container in Lidarr
3. ???? - revealing soon
4. ???? - and next?

**_Thanks to blampe and Typnull for inspiration_** : this wouldn't have been possible without leveraging their previous work

> [!IMPORTANT]
>
> **_For the premade Docker container, visit the Deployment Repo instead: https://github.com/HVR88/LM-Bridge_**

Deploy-only files live in `deploy/` (`docker-compose.yml`, `compose/`, `.env.example`). You can copy that folder as-is, or run `scripts/export-deploy.sh` to create a bundle or sync it to a separate deploy repo (the export excludes `.env` by default).

Hook documentation is in `hooks_readme.md` (custom DB/MITM transforms that run after built-in processing).

## Source Repo Summary

**What This Repo Does**

1. Builds an amd64 container image with Lidarr Metadata Server
2. Adds a bridge config so you can point at your MusicBrainz mirror
3. Builds a Lidarr Plugin to point Lidarr at this self-hosted API
4. Hosts the completed plugin distribution zip as a versioned release

**What This Repo Doesn't Do**

1. **It's not a ready-to-deploy container image**
2. It doesn't build or run the MusicBrainz mirror stack
3. It doesn't build or run Lidarr

**Requirements**

1. Running Lidarr _plugins-enabled_ branch
2. Running MusicBrainz mirror server
3. Building requires the lidarr source tree (submodule in plugin folder)

**Key Defaults**

1. MusicBrainz DB defaults to user `musicbrainz` and password `musicbrainz`
2. LM-BRIDGE cache DB defaults user `lmbridge` and password `lmbridge`

## Configuration of the LM Bridge Container

Edit `deploy/compose/lm-bridge-hosted-services.yml` to match your environment. This file is a standalone Compose file for the LM-Bridge container.

Important fields:

- `PROVIDERS__MUSICBRAINZDBPROVIDER__1__DB_HOST` should point to your MusicBrainz DB host or service name.
- `PROVIDERS__SOLRSEARCHPROVIDER__1__SEARCH_SERVER` should point to your Solr endpoint.
- `POSTGRES_CACHE_HOST` should point to the Postgres host that will hold `lm_cache_db`.

If you want to use Docker service names like `db`, `search`, or `redis`, run this container on the same Docker network as your MusicBrainz mirror.

For best metadata enrichment, set API keys for TheAudioDB and Fanart.tv via `TADB_KEY` and `FANART_KEY` (in `deploy/compose/lm-bridge-hosted-services.yml` or via environment variables).

## Initialize LMBRIDGE Cache DB and MusicBrainz Indexes

This repo includes `scripts/init-mbdb.sh` to handle the database prep that used to be done inside the mirror stack.
If you are upgrading from the legacy cache user `lidarr` or `abc`, the script will automatically migrate ownership to the new cache user and update the password.

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
LMBRIDGE_CACHE_USER=lmbridge \
LMBRIDGE_CACHE_PASSWORD=lmbridge \
scripts/init-mbdb.sh
```

Optional cache schema and fail-open:

```bash
LMBRIDGE_CACHE_SCHEMA=lm_cache \
LMBRIDGE_CACHE_FAIL_OPEN=true \
scripts/init-mbdb.sh
```

The script also creates the cache tables (`fanart`, `tadb`, `wikipedia`, `artist`, `album`, `spotify`) inside `lm_cache_db` to avoid runtime errors like `relation "tadb" does not exist`.

## Technical - Build And Run

### Clone

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

Start the container using the provided settings file (Compose will pull the image if it doesn't exist locally):

```bash
docker compose -f deploy/compose/lm-bridge-hosted-services.yml up -d
```

Note: Deploy files default to `espressomatic/lm-bridge:latest`. If you build locally, set `LMBRIDGE_IMAGE` to your tag.

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
MB_NETWORK=musicbrainz_default docker compose -f deploy/compose/lm-bridge-docker-network.yml up -d
```

If you are building from source, add the dev override:

```bash
MB_NETWORK=musicbrainz_default docker compose -f deploy/compose/lm-bridge-docker-network.yml -f docker-compose.dev.yml up -d
```

### Verify

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

# ⚠️ Disclaimer

THE SOFTWARE IS PROVIDED “AS IS”, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
THE SOFTWARE IS FOR EDUCATIONAL AND INFORMATIONAL PURPOSES ONLY. THE USER ASSUMES ALL RESPONSIBILITY FOR ITS USE OR MISUSE.
THE USER IS FREE TO USE, MODIFY, AND DISTRIBUTE THE SOFTWARE FOR ANY PURPOSE, SUBJECT TO THE ABOVE DISCLAIMERS AND CONDITIONS.
