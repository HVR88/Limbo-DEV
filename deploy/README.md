<p align="center">
  <img src="https://raw.githubusercontent.com/HVR88/Limbo_Bridge_DEV/main/assets/limbo-icon.png" alt="Limbo" width="300" />
</p>

# <p align="center">**Limbo**<br><sub>**Lidarr, but _Working_**</sub></p>

# **WORK IN PROGRESS - A BIG SETUP CHANGE IS HAPPENING RIGHT NOW**

**This release may not work for a few days unless you still have the old LM Bridge plugin installed - migration to plugin-free setup is coming soon**

## Introduction

This is a stand-alone _Limbo_ release for existing MusicBrainz mirror installations. It should be installed onto the same host or docker network as the MusicBrainz mirror. Lidarr setup is detailed below.

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
git clone https://github.com/HVR88/Limbo_Bridge.git
cd /opt/docker/Limbo_Bridge
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

## Browser access / status

Visit **http://HOST_IP:5001** to check the status of Limbo, including version and filter settings

## Files:

- `docker-compose.yml` (default: init + external network)
- `example.env` (copy to `.env` if needed, and edit)
  <br>
  <br>

Source code, docs and licenses: https://github.com/HVR88/Limbo_Bridge_DEV

> <br>**_Thanks to blampe and Typnull for inspiration_** : this wouldn't have been possible without leveraging knowledge from their previous work
> <br><br>

## Version

Package version: `1.9.10.201`
