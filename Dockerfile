# Use official Python 3.9 image for AMD64 (override with --build-arg TARGETPLATFORM=...)
ARG TARGETPLATFORM=linux/amd64
FROM --platform=$TARGETPLATFORM python:3.9-bullseye

# Set working directory
WORKDIR /metadata

# Runtime hygiene
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Copy upstream source (submodule)
COPY upstream/lidarr-metadata /metadata

# Copy overlay bridge (patches, config)
COPY overlay/bridge/lidarrmetadata /metadata/lidarrmetadata

# Copy bridge launcher
COPY overlay/bridge/bridge_launcher.py /metadata/bridge_launcher.py
RUN chmod +x /metadata/bridge_launcher.py

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Set entrypoint to Python bridge launcher
ENTRYPOINT ["python3", "/metadata/bridge_launcher.py"]
