<p align="center">
  <img src="https://raw.githubusercontent.com/HVR88/Limbo_Bridge_DEV/main/assets/limbo-icon.png" alt="Limbo" width="300" />
</p>

# <p align="center">**Limbo Bridge**<br><sub>**_Tools and Data Bridge for Lidarr_**</sub></p>

## Introduction

This is a stand-alone _Limbo Bridge_ release, part of the full [Limbo project](https://github.com/HVR88/Limbo). This stand-alone bridge component is for people with an existing MusicBrainz mirror installation only. It should be installed onto the same host or docker network as the MusicBrainz mirror. Lidarr setup is detailed below. If you don't yet host your own MusicBrainz mirror, [get the full Limbo release](https://github.com/HVR88/Limbo).

**Limbo Features**

- Directly access a local MusicBrainz server instead of remote Lidarr server
  - No more broken connections, and failed searches
- Caching database
- [Media Format](https://github.com/HVR88/Docs-Extras/blob/master/docs/Media-Formats.md) filtering - remove media issues you don't want listed in Lidarr
  - Vinyl? Cassette? Remove them if you want, right at the data layer
- Extendable hook mechanism allows others to add functionality - including additional databases beyond MusicBrainz

> [!IMPORTANT]
>
> I highly recommend the full [**Limbo**](https://github.com/HVR88/Limbo) release, our automated MusicBrainz installation with Limbo Bridge built-in. It's the fastest, easiest and cleanest way to deploy MusicBrainz.

## Quick start

### 1. Lidarr and MusicBrainz

You should already be running a _nightly_ branch [Lidarr](https://hub.docker.com/r/linuxserver/lidarr) release plus [MusicBrainz Mirror](https://github.com/metabrainz/musicbrainz-docker) server _(with materialized tables AND fully indexed db)_

### 2. Download Limbo Bridge

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
- `LIMBO_INIT_STATE_VOLUME` should be `limbo_bridge_init_state` (default) for init-state/settings volume.

### 4. Download containers, build & startup

```
docker compose up -d
```

> [!NOTE]
>
> The compose files are not meant to be edited. Put all overrides in `.env`.

## Set up and use

Visit **http://LIMBO_HOST_IP:5001** for the Limbo WebUI. The first thing to do is click the Settings button in the top right of the window and set Lidarr's address and API Key, which can be obtained from its Settings -> General screen.

## Files:

- `docker-compose.yml` (default: init + external network)
- `example.env` (copy to `.env` if needed, and edit)
  <br>
  <br>

Source code, docs and licenses: https://github.com/HVR88/Limbo_Bridge_DEV

> <br>**_Thanks to blampe and Typnull for inspiration_** : this wouldn't have been possible without leveraging knowledge from their previous work
> <br><br>

## Version

Package version: `1.9.308.562`
