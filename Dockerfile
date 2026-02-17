# Use official Python 3.9 image (platform set at build/run time)
FROM python:3.9-bullseye

# Set working directory
WORKDIR /metadata

ARG APP_VERSION=dev
LABEL org.opencontainers.image.version=$APP_VERSION
ENV LMBRIDGE_VERSION=$APP_VERSION

# Runtime hygiene
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Install psql client (for init container mode)
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl gnupg \
    && curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc | gpg --dearmor -o /usr/share/keyrings/postgresql.gpg \
    && echo "deb [signed-by=/usr/share/keyrings/postgresql.gpg] http://apt.postgresql.org/pub/repos/apt bullseye-pgdg main" > /etc/apt/sources.list.d/pgdg.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends postgresql-client-16 \
    && rm -rf /var/lib/apt/lists/*

# Copy upstream source (submodule)
COPY upstream/lidarr-metadata /metadata

# Copy overlay bridge (patches, config)
COPY overlay/bridge/lidarrmetadata /metadata/lidarrmetadata

# Copy bridge launcher
COPY overlay/bridge/bridge_launcher.py /metadata/bridge_launcher.py
RUN chmod +x /metadata/bridge_launcher.py

# Init assets (used by lm-bridge-init service)
COPY scripts/init-mbdb.sh /metadata/init/init-mbdb.sh
COPY upstream/lidarr-metadata/lidarrmetadata/sql/CreateIndices.sql /metadata/init/CreateIndices.sql
RUN chmod +x /metadata/init/init-mbdb.sh
ENV SQL_FILE=/metadata/init/CreateIndices.sql
RUN echo "$APP_VERSION" > /metadata/VERSION

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Set entrypoint to Python bridge launcher
ENTRYPOINT ["python3", "/metadata/bridge_launcher.py"]
