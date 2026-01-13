"""Sync API for receiving data from remote collectors.

This Flask app runs on the Synology NAS (in Docker) and receives
batched data from Raspberry Pi collectors.
"""

import logging
import os
from datetime import datetime
from functools import wraps
from typing import Optional

from flask import Flask, g, jsonify, request

import psycopg2
from psycopg2.extras import execute_values

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def create_app(database_url: Optional[str] = None) -> Flask:
    """Create and configure the Flask application."""
    app = Flask(__name__)

    # Configuration from environment
    app.config["DATABASE_URL"] = database_url or os.environ.get(
        "DATABASE_URL", "postgresql://meshtastic:meshtastic@db/meshtastic"
    )
    app.config["API_KEYS"] = set(
        os.environ.get("API_KEYS", "").split(",")
    )

    def get_db():
        """Get database connection for current request."""
        if "db" not in g:
            g.db = psycopg2.connect(app.config["DATABASE_URL"])
        return g.db

    @app.teardown_appcontext
    def close_db(exception):
        """Close database connection at end of request."""
        db = g.pop("db", None)
        if db is not None:
            db.close()

    def require_api_key(f):
        """Decorator to require valid API key."""
        @wraps(f)
        def decorated(*args, **kwargs):
            auth_header = request.headers.get("Authorization", "")
            if not auth_header.startswith("Bearer "):
                return jsonify({"error": "Missing authorization header"}), 401

            token = auth_header[7:]  # Remove "Bearer " prefix
            if token not in app.config["API_KEYS"]:
                logger.warning("Invalid API key attempt from %s", request.remote_addr)
                return jsonify({"error": "Invalid API key"}), 401

            return f(*args, **kwargs)
        return decorated

    @app.route("/health", methods=["GET"])
    def health():
        """Health check endpoint."""
        try:
            conn = get_db()
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
            return jsonify({"status": "healthy", "database": "connected"})
        except Exception as e:
            return jsonify({"status": "unhealthy", "error": str(e)}), 500

    @app.route("/api/v1/sync", methods=["POST"])
    @require_api_key
    def sync():
        """Receive sync data from a collector.

        Expected payload:
        {
            "collector_id": "pi-alpha",
            "batch_id": "uuid",
            "data": {
                "nodes": [...],
                "positions": [...],
                "device_metrics": [...],
                "messages": [...],
                "gateways": [...]
            },
            "local_timestamps": {
                "oldest": "2024-01-15T10:00:00",
                "newest": "2024-01-15T12:30:00"
            }
        }
        """
        try:
            payload = request.get_json()
            if not payload:
                return jsonify({"error": "Missing JSON payload"}), 400

            collector_id = payload.get("collector_id")
            batch_id = payload.get("batch_id")
            data = payload.get("data", {})

            if not collector_id:
                return jsonify({"error": "Missing collector_id"}), 400

            logger.info(
                "Sync from collector %s (batch %s)",
                collector_id,
                batch_id,
            )

            conn = get_db()
            records_received = {}

            # Process each table
            with conn.cursor() as cur:
                # Upsert nodes
                nodes = data.get("nodes", [])
                if nodes:
                    records_received["nodes"] = _upsert_nodes(cur, nodes, collector_id)

                # Insert positions
                positions = data.get("positions", [])
                if positions:
                    records_received["positions"] = _insert_positions(
                        cur, positions, collector_id
                    )

                # Insert device metrics
                metrics = data.get("device_metrics", [])
                if metrics:
                    records_received["device_metrics"] = _insert_device_metrics(
                        cur, metrics, collector_id
                    )

                # Insert messages
                messages = data.get("messages", [])
                if messages:
                    records_received["messages"] = _insert_messages(
                        cur, messages, collector_id
                    )

                # Upsert gateways
                gateways = data.get("gateways", [])
                if gateways:
                    records_received["gateways"] = _upsert_gateways(
                        cur, gateways, collector_id
                    )

                # Update collector last_seen
                _update_collector(cur, collector_id)

            conn.commit()

            total = sum(records_received.values())
            logger.info(
                "Processed %d records from collector %s",
                total,
                collector_id,
            )

            return jsonify({
                "status": "ok",
                "batch_id": batch_id,
                "records_received": records_received,
                "server_time": datetime.utcnow().isoformat(),
            })

        except Exception as e:
            logger.exception("Error processing sync request: %s", e)
            return jsonify({"error": str(e)}), 500

    @app.route("/api/v1/collectors", methods=["GET"])
    @require_api_key
    def list_collectors():
        """List all known collectors and their status."""
        try:
            conn = get_db()
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT collector_id, last_seen, record_count
                    FROM collectors
                    ORDER BY last_seen DESC
                """)
                collectors = []
                for row in cur.fetchall():
                    collectors.append({
                        "collector_id": row[0],
                        "last_seen": row[1].isoformat() if row[1] else None,
                        "record_count": row[2],
                    })

            return jsonify({"collectors": collectors})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/v1/stats", methods=["GET"])
    @require_api_key
    def stats():
        """Get database statistics."""
        try:
            conn = get_db()
            with conn.cursor() as cur:
                stats = {}
                for table in ["nodes", "positions", "device_metrics", "messages", "gateways"]:
                    cur.execute(f"SELECT COUNT(*) FROM {table}")
                    stats[f"total_{table}"] = cur.fetchone()[0]

                cur.execute("SELECT COUNT(*) FROM collectors")
                stats["total_collectors"] = cur.fetchone()[0]

            return jsonify(stats)
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    return app


def _upsert_nodes(cur, nodes: list, collector_id: str) -> int:
    """Upsert nodes into the database."""
    if not nodes:
        return 0

    values = []
    for n in nodes:
        values.append((
            n.get("node_id"),
            n.get("node_num"),
            n.get("long_name"),
            n.get("short_name"),
            n.get("hw_model"),
            n.get("firmware_version"),
            n.get("mac_addr"),
            n.get("first_seen"),
            n.get("last_seen"),
            collector_id,
        ))

    execute_values(
        cur,
        """
        INSERT INTO nodes (node_id, node_num, long_name, short_name, hw_model,
                          firmware_version, mac_addr, first_seen, last_seen, collector_id)
        VALUES %s
        ON CONFLICT (node_id) DO UPDATE SET
            node_num = COALESCE(EXCLUDED.node_num, nodes.node_num),
            long_name = COALESCE(EXCLUDED.long_name, nodes.long_name),
            short_name = COALESCE(EXCLUDED.short_name, nodes.short_name),
            hw_model = COALESCE(EXCLUDED.hw_model, nodes.hw_model),
            firmware_version = COALESCE(EXCLUDED.firmware_version, nodes.firmware_version),
            mac_addr = COALESCE(EXCLUDED.mac_addr, nodes.mac_addr),
            last_seen = GREATEST(nodes.last_seen, EXCLUDED.last_seen),
            synced_at = NOW()
        """,
        values,
    )
    return len(values)


def _insert_positions(cur, positions: list, collector_id: str) -> int:
    """Insert positions into the database."""
    if not positions:
        return 0

    values = []
    for p in positions:
        values.append((
            p.get("node_id"),
            p.get("timestamp"),
            p.get("latitude"),
            p.get("longitude"),
            p.get("altitude"),
            p.get("location_source"),
            collector_id,
        ))

    execute_values(
        cur,
        """
        INSERT INTO positions (node_id, timestamp, latitude, longitude, altitude,
                              location_source, collector_id, synced_at)
        VALUES %s
        ON CONFLICT DO NOTHING
        """,
        values,
        template="(%s, %s, %s, %s, %s, %s, %s, NOW())",
    )
    return len(values)


def _insert_device_metrics(cur, metrics: list, collector_id: str) -> int:
    """Insert device metrics into the database."""
    if not metrics:
        return 0

    values = []
    for m in metrics:
        values.append((
            m.get("node_id"),
            m.get("timestamp"),
            m.get("battery_level"),
            m.get("voltage"),
            m.get("channel_utilization"),
            m.get("air_util_tx"),
            m.get("uptime_seconds"),
            collector_id,
        ))

    execute_values(
        cur,
        """
        INSERT INTO device_metrics (node_id, timestamp, battery_level, voltage,
                                   channel_utilization, air_util_tx, uptime_seconds,
                                   collector_id, synced_at)
        VALUES %s
        ON CONFLICT DO NOTHING
        """,
        values,
        template="(%s, %s, %s, %s, %s, %s, %s, %s, NOW())",
    )
    return len(values)


def _insert_messages(cur, messages: list, collector_id: str) -> int:
    """Insert messages into the database."""
    if not messages:
        return 0

    values = []
    for m in messages:
        values.append((
            m.get("timestamp"),
            m.get("from_node"),
            m.get("to_node"),
            m.get("channel"),
            m.get("text"),
            m.get("port_num"),
            collector_id,
        ))

    execute_values(
        cur,
        """
        INSERT INTO messages (timestamp, from_node, to_node, channel, text,
                             port_num, collector_id, synced_at)
        VALUES %s
        ON CONFLICT DO NOTHING
        """,
        values,
        template="(%s, %s, %s, %s, %s, %s, %s, NOW())",
    )
    return len(values)


def _upsert_gateways(cur, gateways: list, collector_id: str) -> int:
    """Upsert gateways into the database."""
    if not gateways:
        return 0

    values = []
    for g in gateways:
        values.append((
            g.get("host"),
            g.get("port"),
            g.get("node_id"),
            g.get("first_seen"),
            g.get("last_seen"),
            collector_id,
        ))

    execute_values(
        cur,
        """
        INSERT INTO gateways (host, port, node_id, first_seen, last_seen, collector_id, synced_at)
        VALUES %s
        ON CONFLICT (host, port, collector_id) DO UPDATE SET
            node_id = COALESCE(EXCLUDED.node_id, gateways.node_id),
            last_seen = GREATEST(gateways.last_seen, EXCLUDED.last_seen),
            synced_at = NOW()
        """,
        values,
    )
    return len(values)


def _update_collector(cur, collector_id: str) -> None:
    """Update collector last_seen and increment record count."""
    cur.execute(
        """
        INSERT INTO collectors (collector_id, last_seen, record_count)
        VALUES (%s, NOW(), 1)
        ON CONFLICT (collector_id) DO UPDATE SET
            last_seen = NOW(),
            record_count = collectors.record_count + 1
        """,
        (collector_id,),
    )


# Application entry point
app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
