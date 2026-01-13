# Dockerfile for Meshtastic Monitor Sync API
FROM python:3.11-slim

WORKDIR /app

# Install dependencies
RUN pip install --no-cache-dir \
    flask>=3.0.0 \
    gunicorn>=21.0.0 \
    psycopg2-binary>=2.9.0

# Copy application
COPY app.py .

# Create non-root user
RUN useradd --create-home appuser
USER appuser

# Expose port
EXPOSE 5000

# Run with gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "app:app"]
