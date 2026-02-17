<p align="center">
  <img src="https://raw.githubusercontent.com/HVR88/LM-Bridge-DEV/main/assets/lmbridge-icon.png" alt="LM Bridge" width="500" />
</p>

# <p align="center">**_Lidarr Metadata Bridge_**<br><sub>**_FAST Local, Private Queries_**</sub></p>

## Introduction

This is a stand-alone _LM-Bridge_ release for existing MusicBrainz mirror installations.

If you don't have a MusicBrainz mirror yet, then use our [**MBNMS PLUS**](https://github.com/HVR88/MBMS_PLUS). It includes _LM-Bridge_ and a fully automated MusicBrainz installation.

> [!IMPORTANT]
>
> _Follow **the below linked** MusicBrainz Mirror Server instructions_<br>

## Quick start

### 1. Lidarr and MusicBrainz

You should already be running a plugins-enabled [Lidarr](https://hub.docker.com/r/linuxserver/lidarr) release plus [MusicBrainz Mirror](https://github.com/metabrainz/musicbrainz-docker) server _(with materialized tables AND fully indexed db)_

### 2. Download the LM-Bridge project

```
mkdir -p /opt/docker/
cd /opt/docker/
git clone https://github.com/HVR88/LM-Bridge.git
cd /opt/docker/LM-Bridge
```

### 3. Optionally Configure .env file

Edit `.env` (top section) before first run:

- Ensure `MB_NETWORK` points at the MusicBrainz mirror network (example: `musicbrainz_default`).
- `LMBRIDGE_PORT` ('5001' default, edit as needed)
- Optional provider keys/tokens for Fanart, The AudioDB, Last.FM, etc.

### 4. Download containers, build & startup

```
docker compose up -d
```

> [!NOTE]
>
> The compose files are not meant to be edited. Put all overrides in `.env`.

## Version

Deploy version: `1.5.0.00`
Deploy version: `1.5.0.00`

Optional cache settings (in `.env`):

- `LMBRIDGE_CACHE_SCHEMA` to use a dedicated schema (default: `public`).
- `LMBRIDGE_CACHE_FAIL_OPEN=true` to start the API with cache disabled if init cannot create cache tables.

## LM Bridge API Plugin (Required)

This repo includes a plugin that will appear in Lidarr's Metadata settings page after being installed. Lidarr must have this plugin installed to talk to the bridge on your network.

**Install the Plugin**

1. In Lidarr, open **System → Plugins**
2. Paste the GitHub repo URL into the GitHub URL box and click **Install**.
3. Restart Lidarr when prompted.

Example: URL for this repo: `https://github.com/HVR88/LM-Bridge`

If you don't see a System → Plugins page in your Lidarr, switch to the `nightly` branch, such as **[LinuxServer.io's](https://hub.docker.com/r/linuxserver/lidarr)**

**Enable the Plugin**

1. In Lidarr, open **Settings → Metadata**
2. Click **LM Bridge API**.
3. Make sure the Enable check-box is checked
4. Enter the URL of the LM Bridge container : 5001
5. Click Save

Lidarr is now using the Bridge API and you should see lightning-fast queries to your MusicBrainz mirror.

### Files:

- `docker-compose.yml` (default: init + external network)
- `compose/lm-bridge-hosted-services.yml` (standalone single-container)
- `compose/lm-bridge-docker-network.yml` (full compose with init container + external network)
- `.env.example` (copy to `.env` if needed, and edit)
- `License/` (LICENSE + THIRD_PARTY_NOTICES)
  <br>
  <br>

> <br>**_Thanks to blampe and Typnull for inspiration_** : this wouldn't have been possible without leveraging their previous work
> <br><br>
