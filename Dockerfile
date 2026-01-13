# Dockerfile for Meshtastic Monitor Collector
# Multi-arch: amd64, arm64 (Raspberry Pi)

FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY pyproject.toml .
COPY mesh_monitor/ mesh_monitor/
COPY web/ web/

# Install the package
RUN pip install --no-cache-dir -e .

# Create non-root user
RUN useradd --create-home --uid 1000 meshtastic
RUN mkdir -p /data && chown meshtastic:meshtastic /data
USER meshtastic

# Data volume for SQLite database
VOLUME /data

# Default environment variables
ENV MESHTASTIC_DB_PATH=/data/mesh.db
ENV MESHTASTIC_HOST=""
ENV MESHTASTIC_PORT=4403

# Expose web UI port
EXPOSE 8080

# Default command: start collector with web UI
CMD ["sh", "-c", "mesh-monitor --db ${MESHTASTIC_DB_PATH} start --host ${MESHTASTIC_HOST} --port ${MESHTASTIC_PORT} --web --web-port 8080"]
