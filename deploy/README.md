<p align="center">
  <img src="https://raw.githubusercontent.com/HVR88/LM-Bridge-DEV/main/assets/lmbridge-icon.png" alt="LM Bridge" width="500" />
</p>

# <p align="center">**LM Bridge - Metadata Handler**<br><sub>**_FAST • Local • Private_**</sub></p>

## Introduction

This is a stand-alone _LM Bridge_ release for existing MusicBrainz mirror installations. It should be installed onto the same host or docker network as the MusicBrainz mirror. Lidarr setup is detailed below. **WORK IN PROGRESS - A BIG SETUP CHANGE IS HAPPENING RIGHT NOW**

**LM Bridge Features**

- Directly access a local MusicBrainz server instead of remote Lidarr server
  - No more broken connections, and failed searches
- Caching database
- [Media Format](https://github.com/HVR88/Docs-Extras/blob/master/docs/Media-Formats.md) filtering - remove media issues you don't want listed in Lidarr
  - Vinyl? Cassette? Remove them if you want, right at the data layer
- Extendable hook mechanism allows others to add functionality - including additional databases beyond MusicBrainz

> [!IMPORTANT]
>
> I highly recommend [**MBMS PLUS**](https://github.com/HVR88/MBMS_PLUS), our automated MusicBrainz installation with LM Bridge built-in instead of a manual mirror setup.

## Quick start

### 1. Lidarr and MusicBrainz

You should already be running a _nightly_ branch [Lidarr](https://hub.docker.com/r/linuxserver/lidarr) release plus [MusicBrainz Mirror](https://github.com/metabrainz/musicbrainz-docker) server _(with materialized tables AND fully indexed db)_

### 2. Download the LM Bridge project

**LM Bridge needs to be installed on the same host as MusicBrainz, whether that be a physical machine, VM or LXC.**

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

## LM Bridge Plugin for Lidarr

Deprecated. This repo no longer publishes a plugin.
once it is available.

If you already have the plugin installed, remove it:

1. In Lidarr, open **System → Plugins**
2. Click the Trash Can icon at the far right of the **LM Bridge** plugin row
3. Restart Lidarr when prompted

## Browser access / status

Visit **http://HOST_IP:5001** to check the status of LM bridge, including version and filter settings

## Files:

- `docker-compose.yml` (default: init + external network)
- `compose/lm-bridge-hosted-services.yml` (standalone single-container)
- `compose/lm-bridge-docker-network.yml` (full compose with init container + external network)
- `.env.example` (copy to `.env` if needed, and edit)
  <br>
  <br>

Source code, docs and licenses: https://github.com/HVR88/LM-Bridge-DEV

> <br>**_Thanks to blampe and Typnull for inspiration_** : this wouldn't have been possible without leveraging knowledge from their previous work
> <br><br>

## Version

Deploy version: `1.9.9.41`
