# Use official Python 3.9 slim image as base
FROM --platform=linux/amd64 python:3.9-bullseye

# Set working directory inside the container
WORKDIR /metadata

# Copy the bridge_launcher.py directly
COPY overlay/bridge/bridge_launcher.py /metadata/lidarrmetadata/
RUN chmod +x /metadata/lidarrmetadata/bridge_launcher.py

# Copy upstream source (submodule)
COPY upstream/lidarr-metadata /metadata

# Copy overlay bridge (patches, config)
COPY overlay/bridge/lidarrmetadata /metadata/lidarrmetadata

# Upgrade pip and install dependencies from requirements.txt
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Ensure bridge launcher is executable
RUN chmod +x /metadata/lidarrmetadata/bridge_launcher.py

# Set entrypoint to bridge launcher
ENTRYPOINT ["/metadata/lidarrmetadata/bridge_launcher.py"]

