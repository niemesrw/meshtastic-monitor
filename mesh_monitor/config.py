"""Configuration management for Meshtastic Monitor collectors.

Supports environment variables and config file for collector settings.
"""

import os
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# Default config file locations
CONFIG_LOCATIONS = [
    Path.home() / ".config" / "meshtastic-monitor" / "config",
    Path("/etc/meshtastic-monitor/config"),
]


@dataclass
class CollectorConfig:
    """Configuration for a remote collector."""

    # Unique identifier for this collector
    collector_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])

    # Sync API endpoint (Synology NAS or cloud)
    sync_api_url: Optional[str] = None

    # API key for authentication
    sync_api_key: Optional[str] = None

    # Sync interval in seconds (default: 5 minutes)
    sync_interval: int = 300

    # Database path
    db_path: str = "mesh.db"

    # Enable sync service
    sync_enabled: bool = False

    @classmethod
    def from_env(cls) -> "CollectorConfig":
        """Load configuration from environment variables.

        Environment variables:
            MESHTASTIC_COLLECTOR_ID: Unique collector identifier
            MESHTASTIC_SYNC_API_URL: Sync API endpoint URL
            MESHTASTIC_SYNC_API_KEY: API key for authentication
            MESHTASTIC_SYNC_INTERVAL: Sync interval in seconds
            MESHTASTIC_DB_PATH: Path to SQLite database
            MESHTASTIC_SYNC_ENABLED: Enable sync service (true/false)
        """
        collector_id = os.environ.get("MESHTASTIC_COLLECTOR_ID")
        if not collector_id:
            # Try to load from persistent file, or generate new
            collector_id = cls._get_or_create_collector_id()

        sync_api_url = os.environ.get("MESHTASTIC_SYNC_API_URL")
        sync_api_key = os.environ.get("MESHTASTIC_SYNC_API_KEY")

        sync_interval_str = os.environ.get("MESHTASTIC_SYNC_INTERVAL", "300")
        try:
            sync_interval = int(sync_interval_str)
        except ValueError:
            sync_interval = 300

        db_path = os.environ.get("MESHTASTIC_DB_PATH", "mesh.db")

        sync_enabled_str = os.environ.get("MESHTASTIC_SYNC_ENABLED", "false")
        sync_enabled = sync_enabled_str.lower() in ("true", "1", "yes")

        return cls(
            collector_id=collector_id,
            sync_api_url=sync_api_url,
            sync_api_key=sync_api_key,
            sync_interval=sync_interval,
            db_path=db_path,
            sync_enabled=sync_enabled,
        )

    @classmethod
    def from_file(cls, config_path: Optional[Path] = None) -> "CollectorConfig":
        """Load configuration from a file.

        Args:
            config_path: Path to config file. If None, searches default locations.

        Config file format (shell-style):
            COLLECTOR_ID=my-collector
            SYNC_API_URL=https://nas.local/api/v1/sync
            SYNC_API_KEY=secret-key
            SYNC_INTERVAL=300
            DB_PATH=/var/lib/meshtastic/mesh.db
            SYNC_ENABLED=true
        """
        if config_path is None:
            for path in CONFIG_LOCATIONS:
                if path.exists():
                    config_path = path
                    break

        config_values = {}
        if config_path and config_path.exists():
            with open(config_path) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, value = line.split("=", 1)
                        config_values[key.strip()] = value.strip().strip('"').strip("'")

        collector_id = config_values.get("COLLECTOR_ID")
        if not collector_id:
            collector_id = cls._get_or_create_collector_id()

        sync_interval_str = config_values.get("SYNC_INTERVAL", "300")
        try:
            sync_interval = int(sync_interval_str)
        except ValueError:
            sync_interval = 300

        sync_enabled_str = config_values.get("SYNC_ENABLED", "false")
        sync_enabled = sync_enabled_str.lower() in ("true", "1", "yes")

        return cls(
            collector_id=collector_id,
            sync_api_url=config_values.get("SYNC_API_URL"),
            sync_api_key=config_values.get("SYNC_API_KEY"),
            sync_interval=sync_interval,
            db_path=config_values.get("DB_PATH", "mesh.db"),
            sync_enabled=sync_enabled,
        )

    @staticmethod
    def _get_or_create_collector_id() -> str:
        """Get persistent collector ID or create a new one.

        Stores the ID in ~/.config/meshtastic-monitor/collector_id
        """
        config_dir = Path.home() / ".config" / "meshtastic-monitor"
        id_file = config_dir / "collector_id"

        if id_file.exists():
            return id_file.read_text().strip()

        # Generate a new ID
        collector_id = f"collector-{str(uuid.uuid4())[:8]}"

        # Try to persist it
        try:
            config_dir.mkdir(parents=True, exist_ok=True)
            id_file.write_text(collector_id)
        except OSError:
            # Can't persist, just use the generated ID
            pass

        return collector_id

    def is_sync_configured(self) -> bool:
        """Check if sync is properly configured."""
        return bool(self.sync_api_url and self.sync_api_key)

    def validate(self) -> list[str]:
        """Validate configuration and return list of errors."""
        errors = []

        if self.sync_enabled:
            if not self.sync_api_url:
                errors.append("SYNC_API_URL is required when sync is enabled")
            if not self.sync_api_key:
                errors.append("SYNC_API_KEY is required when sync is enabled")

        if self.sync_interval < 10:
            errors.append("SYNC_INTERVAL must be at least 10 seconds")

        return errors


def load_config() -> CollectorConfig:
    """Load configuration with environment variables taking precedence over file."""
    # Start with file config if available
    config = CollectorConfig.from_file()

    # Override with environment variables
    if os.environ.get("MESHTASTIC_COLLECTOR_ID"):
        config.collector_id = os.environ["MESHTASTIC_COLLECTOR_ID"]
    if os.environ.get("MESHTASTIC_SYNC_API_URL"):
        config.sync_api_url = os.environ["MESHTASTIC_SYNC_API_URL"]
    if os.environ.get("MESHTASTIC_SYNC_API_KEY"):
        config.sync_api_key = os.environ["MESHTASTIC_SYNC_API_KEY"]
    if os.environ.get("MESHTASTIC_SYNC_INTERVAL"):
        try:
            config.sync_interval = int(os.environ["MESHTASTIC_SYNC_INTERVAL"])
        except ValueError:
            pass
    if os.environ.get("MESHTASTIC_DB_PATH"):
        config.db_path = os.environ["MESHTASTIC_DB_PATH"]
    if os.environ.get("MESHTASTIC_SYNC_ENABLED"):
        config.sync_enabled = os.environ["MESHTASTIC_SYNC_ENABLED"].lower() in (
            "true",
            "1",
            "yes",
        )

    return config
