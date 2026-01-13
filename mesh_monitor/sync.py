"""Sync service for pushing data to central Synology NAS.

Handles batching, retries, and marking records as synced.
"""

import json
import logging
import threading
import time
import uuid
from datetime import datetime
from typing import Optional

import requests

from .config import CollectorConfig, load_config
from .db import Database

logger = logging.getLogger(__name__)


class SyncError(Exception):
    """Error during sync operation."""

    pass


class SyncService:
    """Service for syncing local data to central server."""

    def __init__(self, db: Database, config: Optional[CollectorConfig] = None):
        """Initialize sync service.

        Args:
            db: Database instance to sync from.
            config: Collector configuration. If None, loads from env/file.
        """
        self.db = db
        self.config = config or load_config()
        self._stop_event = threading.Event()
        self._sync_thread: Optional[threading.Thread] = None

    def sync_once(self) -> dict:
        """Perform a single sync operation.

        Returns:
            Dictionary with sync results including record counts.

        Raises:
            SyncError: If sync fails.
        """
        if not self.config.is_sync_configured():
            raise SyncError("Sync not configured: missing SYNC_API_URL or SYNC_API_KEY")

        # Get unsynced records
        unsynced = self.db.get_unsynced_records(limit=1000)

        # Check if there's anything to sync
        total_records = sum(len(records) for records in unsynced.values())
        if total_records == 0:
            logger.debug("No records to sync")
            return {"status": "ok", "records_synced": 0, "message": "No records to sync"}

        # Prepare the sync payload
        batch_id = str(uuid.uuid4())
        payload = self._prepare_payload(batch_id, unsynced)

        # Send to sync API
        try:
            response = self._send_sync_request(payload)
        except requests.RequestException as e:
            raise SyncError(f"Failed to send sync request: {e}") from e

        # Mark records as synced
        record_ids = self._extract_record_ids(unsynced)
        self.db.mark_synced(record_ids)

        logger.info(
            "Synced %d records (nodes=%d, positions=%d, metrics=%d, messages=%d, gateways=%d)",
            total_records,
            len(unsynced.get("nodes", [])),
            len(unsynced.get("positions", [])),
            len(unsynced.get("device_metrics", [])),
            len(unsynced.get("messages", [])),
            len(unsynced.get("gateways", [])),
        )

        return {
            "status": "ok",
            "batch_id": batch_id,
            "records_synced": total_records,
            "details": {
                "nodes": len(unsynced.get("nodes", [])),
                "positions": len(unsynced.get("positions", [])),
                "device_metrics": len(unsynced.get("device_metrics", [])),
                "messages": len(unsynced.get("messages", [])),
                "gateways": len(unsynced.get("gateways", [])),
            },
        }

    def _prepare_payload(self, batch_id: str, unsynced: dict) -> dict:
        """Prepare the sync payload."""
        # Convert datetime objects to ISO format strings
        data = {}
        for table, records in unsynced.items():
            data[table] = []
            for record in records:
                converted = {}
                for key, value in record.items():
                    if isinstance(value, datetime):
                        converted[key] = value.isoformat()
                    else:
                        converted[key] = value
                data[table].append(converted)

        # Find timestamp range
        timestamps = []
        for records in unsynced.values():
            for record in records:
                if "timestamp" in record and record["timestamp"]:
                    timestamps.append(record["timestamp"])
                elif "last_seen" in record and record["last_seen"]:
                    timestamps.append(record["last_seen"])

        oldest = min(timestamps).isoformat() if timestamps else None
        newest = max(timestamps).isoformat() if timestamps else None

        return {
            "collector_id": self.config.collector_id,
            "batch_id": batch_id,
            "data": data,
            "local_timestamps": {
                "oldest": oldest,
                "newest": newest,
            },
        }

    def _send_sync_request(self, payload: dict) -> dict:
        """Send sync request to the API."""
        headers = {
            "Authorization": f"Bearer {self.config.sync_api_key}",
            "Content-Type": "application/json",
        }

        response = requests.post(
            self.config.sync_api_url,
            json=payload,
            headers=headers,
            timeout=30,
        )

        if not response.ok:
            raise SyncError(f"Sync API returned {response.status_code}: {response.text}")

        return response.json()

    def _extract_record_ids(self, unsynced: dict) -> dict:
        """Extract record IDs for marking as synced."""
        return {
            "nodes": [r["node_id"] for r in unsynced.get("nodes", [])],
            "positions": [r["id"] for r in unsynced.get("positions", [])],
            "device_metrics": [r["id"] for r in unsynced.get("device_metrics", [])],
            "messages": [r["id"] for r in unsynced.get("messages", [])],
            "gateways": [r["id"] for r in unsynced.get("gateways", [])],
        }

    def start(self) -> None:
        """Start the background sync service."""
        if self._sync_thread and self._sync_thread.is_alive():
            logger.warning("Sync service already running")
            return

        if not self.config.sync_enabled:
            logger.warning("Sync service not enabled in configuration")
            return

        self._stop_event.clear()
        self._sync_thread = threading.Thread(target=self._sync_loop, daemon=True)
        self._sync_thread.start()
        logger.info(
            "Sync service started (interval=%ds, collector=%s)",
            self.config.sync_interval,
            self.config.collector_id,
        )

    def stop(self) -> None:
        """Stop the background sync service."""
        self._stop_event.set()
        if self._sync_thread:
            self._sync_thread.join(timeout=5)
            self._sync_thread = None
        logger.info("Sync service stopped")

    def _sync_loop(self) -> None:
        """Background sync loop with exponential backoff on failures."""
        backoff = 1
        max_backoff = 300  # 5 minutes max

        while not self._stop_event.is_set():
            try:
                self.sync_once()
                backoff = 1  # Reset on success
            except SyncError as e:
                logger.error("Sync failed: %s (retry in %ds)", e, backoff)
                backoff = min(backoff * 2, max_backoff)
            except Exception as e:
                logger.exception("Unexpected error during sync: %s", e)
                backoff = min(backoff * 2, max_backoff)

            # Wait for next sync interval or stop event
            self._stop_event.wait(timeout=max(self.config.sync_interval, backoff))

    def get_status(self) -> dict:
        """Get sync service status."""
        unsynced = self.db.get_unsynced_count()
        sync_stats = self.db.get_sync_stats()

        return {
            "collector_id": self.config.collector_id,
            "sync_enabled": self.config.sync_enabled,
            "sync_configured": self.config.is_sync_configured(),
            "sync_api_url": self.config.sync_api_url,
            "sync_interval": self.config.sync_interval,
            "running": self._sync_thread is not None and self._sync_thread.is_alive(),
            "unsynced": unsynced,
            "sync_stats": sync_stats,
        }


def run_sync_service(db_path: str = "mesh.db", config: Optional[CollectorConfig] = None) -> None:
    """Run the sync service as a standalone process.

    Args:
        db_path: Path to SQLite database.
        config: Optional configuration override.
    """
    config = config or load_config()

    # Validate configuration
    errors = config.validate()
    if errors:
        for error in errors:
            logger.error("Configuration error: %s", error)
        raise SyncError("Invalid configuration")

    db = Database(db_path=db_path, collector_id=config.collector_id)
    service = SyncService(db, config)

    logger.info("Starting sync service for collector %s", config.collector_id)
    logger.info("Sync API: %s", config.sync_api_url)
    logger.info("Sync interval: %ds", config.sync_interval)

    service.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Received interrupt, stopping sync service")
        service.stop()
