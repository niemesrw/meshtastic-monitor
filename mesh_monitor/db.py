"""Database layer for Meshtastic Monitor.

Handles SQLite database operations for storing mesh network data.
"""

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional


@dataclass
class Gateway:
    """A gateway node we connect to directly."""

    id: Optional[int]
    host: str
    port: int
    node_id: Optional[str]
    first_seen: Optional[datetime]
    last_seen: Optional[datetime]


@dataclass
class Node:
    """A mesh node discovered through the network."""

    node_id: str
    node_num: Optional[int]
    long_name: Optional[str]
    short_name: Optional[str]
    hw_model: Optional[str]
    firmware_version: Optional[str]
    mac_addr: Optional[str]
    first_seen: Optional[datetime]
    last_seen: Optional[datetime]


@dataclass
class Position:
    """A position report from a node."""

    id: Optional[int]
    node_id: str
    timestamp: datetime
    latitude: Optional[float]
    longitude: Optional[float]
    altitude: Optional[int]
    location_source: Optional[str]


@dataclass
class DeviceMetrics:
    """Device telemetry from a node."""

    id: Optional[int]
    node_id: str
    timestamp: datetime
    battery_level: Optional[int]
    voltage: Optional[float]
    channel_utilization: Optional[float]
    air_util_tx: Optional[float]
    uptime_seconds: Optional[int]


@dataclass
class Message:
    """A text message from the mesh."""

    id: Optional[int]
    timestamp: datetime
    from_node: Optional[str]
    to_node: Optional[str]
    channel: Optional[int]
    text: Optional[str]
    port_num: Optional[str]
    gateway_id: Optional[int]


SCHEMA = """
CREATE TABLE IF NOT EXISTS gateways (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    host TEXT NOT NULL,
    port INTEGER DEFAULT 4403,
    node_id TEXT,
    first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(host, port)
);

CREATE TABLE IF NOT EXISTS nodes (
    node_id TEXT PRIMARY KEY,
    node_num INTEGER,
    long_name TEXT,
    short_name TEXT,
    hw_model TEXT,
    firmware_version TEXT,
    mac_addr TEXT,
    first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    node_id TEXT NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    latitude REAL,
    longitude REAL,
    altitude INTEGER,
    location_source TEXT,
    FOREIGN KEY (node_id) REFERENCES nodes(node_id)
);

CREATE TABLE IF NOT EXISTS device_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    node_id TEXT NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    battery_level INTEGER,
    voltage REAL,
    channel_utilization REAL,
    air_util_tx REAL,
    uptime_seconds INTEGER,
    FOREIGN KEY (node_id) REFERENCES nodes(node_id)
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TIMESTAMP NOT NULL,
    from_node TEXT,
    to_node TEXT,
    channel INTEGER,
    text TEXT,
    port_num TEXT,
    gateway_id INTEGER,
    FOREIGN KEY (from_node) REFERENCES nodes(node_id),
    FOREIGN KEY (gateway_id) REFERENCES gateways(id)
);

CREATE INDEX IF NOT EXISTS idx_positions_node_id ON positions(node_id);
CREATE INDEX IF NOT EXISTS idx_positions_timestamp ON positions(timestamp);
CREATE INDEX IF NOT EXISTS idx_device_metrics_node_id ON device_metrics(node_id);
CREATE INDEX IF NOT EXISTS idx_device_metrics_timestamp ON device_metrics(timestamp);
CREATE INDEX IF NOT EXISTS idx_messages_timestamp ON messages(timestamp);
CREATE INDEX IF NOT EXISTS idx_messages_from_node ON messages(from_node);
CREATE INDEX IF NOT EXISTS idx_nodes_last_seen ON nodes(last_seen);
"""


class Database:
    """SQLite database manager for mesh network data."""

    def __init__(self, db_path: str = "mesh.db"):
        """Initialize database connection.

        Args:
            db_path: Path to SQLite database file.
        """
        self.db_path = Path(db_path)
        self._init_db()

    def _init_db(self) -> None:
        """Initialize database schema."""
        with self._get_connection() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def _get_connection(self):
        """Get a database connection with row factory."""
        conn = sqlite3.connect(self.db_path, detect_types=sqlite3.PARSE_DECLTYPES)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    # Gateway operations

    def upsert_gateway(self, host: str, port: int = 4403, node_id: Optional[str] = None) -> int:
        """Insert or update a gateway.

        Args:
            host: Gateway hostname or IP.
            port: Gateway TCP port.
            node_id: Meshtastic node ID if known.

        Returns:
            Gateway ID.
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO gateways (host, port, node_id, last_seen)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(host, port) DO UPDATE SET
                    node_id = COALESCE(excluded.node_id, node_id),
                    last_seen = CURRENT_TIMESTAMP
                RETURNING id
                """,
                (host, port, node_id),
            )
            return cursor.fetchone()[0]

    def get_gateway(self, gateway_id: int) -> Optional[Gateway]:
        """Get a gateway by ID."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM gateways WHERE id = ?", (gateway_id,)
            ).fetchone()
            if row:
                return Gateway(**dict(row))
            return None

    def get_all_gateways(self) -> list[Gateway]:
        """Get all gateways."""
        with self._get_connection() as conn:
            rows = conn.execute("SELECT * FROM gateways ORDER BY last_seen DESC").fetchall()
            return [Gateway(**dict(row)) for row in rows]

    # Node operations

    def upsert_node(
        self,
        node_id: str,
        node_num: Optional[int] = None,
        long_name: Optional[str] = None,
        short_name: Optional[str] = None,
        hw_model: Optional[str] = None,
        firmware_version: Optional[str] = None,
        mac_addr: Optional[str] = None,
    ) -> None:
        """Insert or update a node.

        Args:
            node_id: Meshtastic node ID (e.g., !435a7b70).
            node_num: Numeric node identifier.
            long_name: User-configured long name.
            short_name: 4-character short name.
            hw_model: Hardware model.
            firmware_version: Firmware version string.
            mac_addr: MAC address.
        """
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO nodes (node_id, node_num, long_name, short_name,
                                   hw_model, firmware_version, mac_addr, last_seen)
                VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(node_id) DO UPDATE SET
                    node_num = COALESCE(excluded.node_num, node_num),
                    long_name = COALESCE(excluded.long_name, long_name),
                    short_name = COALESCE(excluded.short_name, short_name),
                    hw_model = COALESCE(excluded.hw_model, hw_model),
                    firmware_version = COALESCE(excluded.firmware_version, firmware_version),
                    mac_addr = COALESCE(excluded.mac_addr, mac_addr),
                    last_seen = CURRENT_TIMESTAMP
                """,
                (node_id, node_num, long_name, short_name, hw_model, firmware_version, mac_addr),
            )

    def get_node(self, node_id: str) -> Optional[Node]:
        """Get a node by ID."""
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM nodes WHERE node_id = ?", (node_id,)).fetchone()
            if row:
                return Node(**dict(row))
            return None

    def get_all_nodes(self, limit: int = 100, offset: int = 0) -> list[Node]:
        """Get all nodes ordered by last seen."""
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM nodes ORDER BY last_seen DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
            return [Node(**dict(row)) for row in rows]

    def get_node_count(self) -> int:
        """Get total number of nodes."""
        with self._get_connection() as conn:
            return conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]

    # Position operations

    def insert_position(
        self,
        node_id: str,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
        altitude: Optional[int] = None,
        location_source: Optional[str] = None,
        timestamp: Optional[datetime] = None,
    ) -> int:
        """Insert a position record.

        Args:
            node_id: Node ID that reported the position.
            latitude: Latitude in degrees.
            longitude: Longitude in degrees.
            altitude: Altitude in meters.
            location_source: Source of location data.
            timestamp: When position was received (defaults to now).

        Returns:
            Position ID.
        """
        if timestamp is None:
            timestamp = datetime.now()

        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO positions (node_id, timestamp, latitude, longitude,
                                       altitude, location_source)
                VALUES (?, ?, ?, ?, ?, ?)
                RETURNING id
                """,
                (node_id, timestamp, latitude, longitude, altitude, location_source),
            )
            return cursor.fetchone()[0]

    def get_positions(
        self, node_id: str, limit: int = 100, offset: int = 0
    ) -> list[Position]:
        """Get positions for a node."""
        with self._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM positions
                WHERE node_id = ?
                ORDER BY timestamp DESC
                LIMIT ? OFFSET ?
                """,
                (node_id, limit, offset),
            ).fetchall()
            return [Position(**dict(row)) for row in rows]

    def get_latest_positions(self, limit: int = 100) -> list[Position]:
        """Get the latest position for each node."""
        with self._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT p.* FROM positions p
                INNER JOIN (
                    SELECT node_id, MAX(timestamp) as max_ts
                    FROM positions
                    GROUP BY node_id
                ) latest ON p.node_id = latest.node_id AND p.timestamp = latest.max_ts
                ORDER BY p.timestamp DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [Position(**dict(row)) for row in rows]

    # Device metrics operations

    def insert_device_metrics(
        self,
        node_id: str,
        battery_level: Optional[int] = None,
        voltage: Optional[float] = None,
        channel_utilization: Optional[float] = None,
        air_util_tx: Optional[float] = None,
        uptime_seconds: Optional[int] = None,
        timestamp: Optional[datetime] = None,
    ) -> int:
        """Insert device metrics.

        Args:
            node_id: Node ID that reported metrics.
            battery_level: Battery percentage (0-100).
            voltage: Battery voltage.
            channel_utilization: Channel utilization percentage.
            air_util_tx: Airtime TX utilization percentage.
            uptime_seconds: Device uptime in seconds.
            timestamp: When metrics were received (defaults to now).

        Returns:
            Metrics ID.
        """
        if timestamp is None:
            timestamp = datetime.now()

        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO device_metrics (node_id, timestamp, battery_level, voltage,
                                            channel_utilization, air_util_tx, uptime_seconds)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                RETURNING id
                """,
                (
                    node_id,
                    timestamp,
                    battery_level,
                    voltage,
                    channel_utilization,
                    air_util_tx,
                    uptime_seconds,
                ),
            )
            return cursor.fetchone()[0]

    def get_device_metrics(
        self, node_id: str, limit: int = 100, offset: int = 0
    ) -> list[DeviceMetrics]:
        """Get device metrics for a node."""
        with self._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM device_metrics
                WHERE node_id = ?
                ORDER BY timestamp DESC
                LIMIT ? OFFSET ?
                """,
                (node_id, limit, offset),
            ).fetchall()
            return [DeviceMetrics(**dict(row)) for row in rows]

    def get_latest_device_metrics(self, node_id: str) -> Optional[DeviceMetrics]:
        """Get the latest device metrics for a node."""
        with self._get_connection() as conn:
            row = conn.execute(
                """
                SELECT * FROM device_metrics
                WHERE node_id = ?
                ORDER BY timestamp DESC
                LIMIT 1
                """,
                (node_id,),
            ).fetchone()
            if row:
                return DeviceMetrics(**dict(row))
            return None

    # Message operations

    def insert_message(
        self,
        from_node: Optional[str] = None,
        to_node: Optional[str] = None,
        channel: Optional[int] = None,
        text: Optional[str] = None,
        port_num: Optional[str] = None,
        gateway_id: Optional[int] = None,
        timestamp: Optional[datetime] = None,
    ) -> int:
        """Insert a message.

        Args:
            from_node: Sender node ID.
            to_node: Recipient node ID.
            channel: Channel index.
            text: Message text.
            port_num: Port number/type.
            gateway_id: Gateway that received the message.
            timestamp: When message was received (defaults to now).

        Returns:
            Message ID.
        """
        if timestamp is None:
            timestamp = datetime.now()

        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO messages (timestamp, from_node, to_node, channel,
                                      text, port_num, gateway_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                RETURNING id
                """,
                (timestamp, from_node, to_node, channel, text, port_num, gateway_id),
            )
            return cursor.fetchone()[0]

    def get_messages(
        self,
        from_node: Optional[str] = None,
        to_node: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Message]:
        """Get messages with optional filters."""
        query = "SELECT * FROM messages WHERE 1=1"
        params: list = []

        if from_node:
            query += " AND from_node = ?"
            params.append(from_node)
        if to_node:
            query += " AND to_node = ?"
            params.append(to_node)

        query += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        with self._get_connection() as conn:
            rows = conn.execute(query, params).fetchall()
            return [Message(**dict(row)) for row in rows]

    def get_message_count(self) -> int:
        """Get total number of messages."""
        with self._get_connection() as conn:
            return conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]

    # Statistics

    def get_stats(self) -> dict:
        """Get database statistics."""
        with self._get_connection() as conn:
            return {
                "total_nodes": conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0],
                "total_positions": conn.execute("SELECT COUNT(*) FROM positions").fetchone()[0],
                "total_metrics": conn.execute("SELECT COUNT(*) FROM device_metrics").fetchone()[0],
                "total_messages": conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0],
                "total_gateways": conn.execute("SELECT COUNT(*) FROM gateways").fetchone()[0],
            }
