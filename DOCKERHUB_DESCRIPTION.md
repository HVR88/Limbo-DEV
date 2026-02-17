<p align="center">
  <img src="https://raw.githubusercontent.com/HVR88/LM-Bridge/main/assets/lmbridge-icon.png" alt="LM Bridge" width="500" />
</p>

# Lidarr/MusicBrainz Bridge

**A Local API Bridge - _FAST_ queries, no remote server issues**

**_Thanks to blampe and Typnull for inspiration_** : this wouldn't have been possible without leveraging their previous work

_Download the **Deploy** files from GitHub (`deploy/`) or use the root `docker-compose.yml` if you cloned the repo._

You should already be running a plugins-enabled [Lidarr](https://hub.docker.com/r/linuxserver/lidarr) release plus [MusicBrainz Mirror](https://github.com/metabrainz/musicbrainz-docker) server _(with materialized tables AND fully indexed db)_

> [!IMPORTANT]
>
> _Follow **the above linked** MusicBrainz Mirror Server instructions_<br>

## Container Summary

**Included**

1. amd64 image with Lidarr Metadata Server
2. Includes a bridge config so you can point at your MusicBrainz mirror

**Requirements**

1. Running MusicBrainz mirror server container
2. Running Lidarr _plugins-enabled_ container
3. LM-Bridge Plugin

**Key Defaults**

1. MusicBrainz DB defaults to user `musicbrainz` and password `musicbrainz`
2. LM-BRIDGE cache DB defaults user `lidarr` and password `lidarr`

## Required Lidarr Plugin

**Install the LM-Bridge Plugin**

1. In Lidarr, open **System → Plugins**
2. Paste the GitHub repo URL `https://github.com/HVR88/LM-Bridge` into the GitHub URL box and click **Install**.
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

The script also creates the cache tables (`fanart`, `tadb`, `wikipedia`, `artist`, `album`, `spotify`) inside `lm_cache_db` to avoid runtime errors like `relation "tadb" does not exist`.

If you want to run it on the **same Docker network** as your MusicBrainz mirror and auto-run the **init container**, use the repo’s root `docker-compose.yml` (it’s already there if you cloned the repo). Then run:

```bash
MB_NETWORK=musicbrainz_default docker compose -f docker-compose.yml up -d
```

The `init` container will exit after completing setup. That is expected.

If you use custom image tags, set them via environment:

```bash
LMBRIDGE_IMAGE=espressomatic/lm-bridge:latest \
MB_NETWORK=musicbrainz_default \
docker compose -f docker-compose.yml up -d
```

Note: `MB_DB_USER` must have permission to create roles and databases (the mirror's primary Postgres user usually does).

If your Docker Compose version does not support `include` (used by `docker-compose.yml`), you can still run the underlying file directly:

```bash
MB_NETWORK=musicbrainz_default docker compose -f deploy/compose/lm-bridge-docker-network.yml up -d
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

# ⚠️ Disclaimer

THE SOFTWARE IS PROVIDED “AS IS”, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
THE SOFTWARE IS FOR EDUCATIONAL AND INFORMATIONAL PURPOSES ONLY. THE USER ASSUMES ALL RESPONSIBILITY FOR ITS USE OR MISUSE.
THE USER IS FREE TO USE, MODIFY, AND DISTRIBUTE THE SOFTWARE FOR ANY PURPOSE, SUBJECT TO THE ABOVE DISCLAIMERS AND CONDITIONS.
