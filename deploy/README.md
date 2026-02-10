<p align="center">
  <img src="https://raw.githubusercontent.com/HVR88/LM-Bridge-DEV/main/assets/lmbridge-icon.png" alt="LM Bridge" width="500" />
</p>

# Lidarr/MusicBrainz Bridge

**A Local API Bridge - _FAST_ queries, no remote server issues**

This folder contains the minimal files needed to run LM-Bridge in production without cloning the full source repo.

Files:

- `docker-compose.yml` (default: init + external network)
- `compose/lm-bridge-hosted-services.yml` (standalone single-container)
- `compose/lm-bridge-docker-network.yml` (full compose with init container + external network)
- `.env.example` (copy to `.env` and edit)
- `License/` (LICENSE + THIRD_PARTY_NOTICES)

The compose files are not meant to be edited. Put all overrides in `.env`.

## Which Mode Should I Use?

Use **Mirror-Network + Init** when you want LM-Bridge to join the same Docker network as your MusicBrainz mirror. This is the default `docker-compose.yml` at the repo root.

Use **Standalone** when your MusicBrainz Postgres, Solr, and Redis can only be reached by hostname/IP. This runs only the `api` container and is a more advanced setup because it requires exposing those services.

## Quick Start (Same Docker Network as MusicBrainz Mirror)

1. Copy `.env.example` to `.env` and edit values.
2. Ensure `MB_NETWORK` points at the MusicBrainz mirror network (example: `musicbrainz_default`).
3. Run:

```bash
docker compose up -d
```

## Quick Start (Standalone)

1. Copy `.env.example` to `.env` and edit values.
2. Run:

```bash
docker compose -f compose/lm-bridge-hosted-services.yml up -d
```

Use this when your MusicBrainz DB, Solr, and Redis are only reachable by hostname or IP from the LM-Bridge container.
