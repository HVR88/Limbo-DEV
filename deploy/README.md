<p align="center">
  <img src="https://raw.githubusercontent.com/HVR88/Limbo-DEV/main/assets/limbo-icon.png" alt="Limbo" width="500" />
</p>

# <p align="center">**Limbo - Metadata Handler**<br><sub>**_FAST • Local • Private_**</sub></p>

## Introduction

This is a stand-alone _Limbo_ release for existing MusicBrainz mirror installations. It should be installed onto the same host or docker network as the MusicBrainz mirror. Lidarr setup is detailed below. **WORK IN PROGRESS - A BIG SETUP CHANGE IS HAPPENING RIGHT NOW**

**Limbo Features**

- Directly access a local MusicBrainz server instead of remote Lidarr server
  - No more broken connections, and failed searches
- Caching database
- [Media Format](https://github.com/HVR88/Docs-Extras/blob/master/docs/Media-Formats.md) filtering - remove media issues you don't want listed in Lidarr
  - Vinyl? Cassette? Remove them if you want, right at the data layer
- Extendable hook mechanism allows others to add functionality - including additional databases beyond MusicBrainz

> [!IMPORTANT]
>
> I highly recommend [**MBMS PLUS**](https://github.com/HVR88/MBMS_PLUS), our automated MusicBrainz installation with Limbo built-in instead of a manual mirror setup.

## Quick start

### 1. Lidarr and MusicBrainz

You should already be running a _nightly_ branch [Lidarr](https://hub.docker.com/r/linuxserver/lidarr) release plus [MusicBrainz Mirror](https://github.com/metabrainz/musicbrainz-docker) server _(with materialized tables AND fully indexed db)_

### 2. Download Limbo project

**Limbo needs to be installed on the same host as MusicBrainz, whether that be a physical machine, VM or LXC.**

```
mkdir -p /opt/docker/
cd /opt/docker/
git clone https://github.com/HVR88/Limbo.git
cd /opt/docker/Limbo
```

### 3. Optionally Configure .env file

Edit `.env` (top section) before first run:

- Ensure `MB_NETWORK` points at the MusicBrainz mirror network (example: `musicbrainz_default`).
- `LIMBO_PORT` ('5001' default, edit as needed)
- Optional provider keys/tokens for Fanart, The AudioDB, Last.FM, etc.

### 4. Download containers, build & startup

```
docker compose up -d
```

> [!NOTE]
>
> The compose files are not meant to be edited. Put all overrides in `.env`.

## Limbo Plugin for Lidarr

Deprecated. This repo no longer publishes a plugin.
once it is available.

If you already have the plugin installed, remove it:

1. In Lidarr, open **System → Plugins**
2. Click the Trash Can icon at the far right of the **Limbo** plugin row
3. Restart Lidarr when prompted

## Browser access / status

Visit **http://HOST_IP:5001** to check the status of Limbo, including version and filter settings

## Files:

- `docker-compose.yml` (default: init + external network)
- `compose/limbo-hosted-services.yml` (standalone single-container)
- `compose/limbo-docker-network.yml` (full compose with init container + external network)
- `.env.example` (copy to `.env` if needed, and edit)
  <br>
  <br>

Source code, docs and licenses: https://github.com/HVR88/Limbo-DEV

> <br>**_Thanks to blampe and Typnull for inspiration_** : this wouldn't have been possible without leveraging knowledge from their previous work
> <br><br>

## Version

Deploy version: `1.9.9.51`
