"""Flask web application for Meshtastic Monitor (PostgreSQL version).

This is the central web UI that runs on Synology NAS and displays
aggregated data from all collectors.
"""

import os
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, g, jsonify, render_template, request

import psycopg2
from psycopg2.extras import RealDictCursor


def create_app(database_url: str = None) -> Flask:
    """Create and configure the Flask application."""
    app = Flask(
        __name__,
        template_folder=str(Path(__file__).parent / "templates"),
    )

    app.config["DATABASE_URL"] = database_url or os.environ.get(
        "DATABASE_URL", "postgresql://meshtastic:meshtastic@db/meshtastic"
    )

    def get_db():
        """Get database connection for current request."""
        if "db" not in g:
            g.db = psycopg2.connect(
                app.config["DATABASE_URL"],
                cursor_factory=RealDictCursor,
            )
        return g.db

    @app.teardown_appcontext
    def close_db(exception):
        """Close database connection at end of request."""
        db = g.pop("db", None)
        if db is not None:
            db.close()

    # Template filters
    @app.template_filter("datetime")
    def format_datetime(value):
        """Format datetime for display."""
        if value is None:
            return "N/A"
        if isinstance(value, str):
            return value
        return value.strftime("%Y-%m-%d %H:%M:%S")

    @app.template_filter("relative_time")
    def relative_time(value):
        """Format datetime as relative time."""
        if value is None:
            return "Never"
        if isinstance(value, str):
            try:
                value = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                return value

        now = datetime.now(timezone.utc) if value.tzinfo else datetime.now()
        diff = now - value

        seconds = diff.total_seconds()
        if seconds < 60:
            return "Just now"
        elif seconds < 3600:
            minutes = int(seconds / 60)
            return f"{minutes}m ago"
        elif seconds < 86400:
            hours = int(seconds / 3600)
            return f"{hours}h ago"
        else:
            days = int(seconds / 86400)
            return f"{days}d ago"

    # View routes
    @app.route("/")
    def dashboard():
        """Dashboard view with aggregated stats from all collectors."""
        conn = get_db()
        with conn.cursor() as cur:
            # Get stats
            stats = {}
            for table in ["nodes", "positions", "device_metrics", "messages", "gateways"]:
                cur.execute(f"SELECT COUNT(*) as count FROM {table}")
                result = cur.fetchone()
                stats[f"total_{table}"] = result["count"]

            # Get active nodes (last hour)
            cur.execute("""
                SELECT COUNT(*) as count FROM nodes
                WHERE last_seen > NOW() - INTERVAL '1 hour'
            """)
            stats["active_nodes"] = cur.fetchone()["count"]

            # Get collector count
            cur.execute("SELECT COUNT(*) as count FROM collectors")
            stats["total_collectors"] = cur.fetchone()["count"]

            # Get recent nodes
            cur.execute("""
                SELECT node_id, long_name, short_name, hw_model, last_seen, collector_id
                FROM nodes
                ORDER BY last_seen DESC
                LIMIT 10
            """)
            nodes = cur.fetchall()

            # Get recent messages
            cur.execute("""
                SELECT timestamp, from_node, to_node, text, collector_id
                FROM messages
                ORDER BY timestamp DESC
                LIMIT 10
            """)
            messages = cur.fetchall()

            # Get collector health
            cur.execute("""
                SELECT * FROM collector_health
                LIMIT 10
            """)
            collectors = cur.fetchall()

        return render_template(
            "dashboard.html",
            stats=stats,
            nodes=nodes,
            messages=messages,
            collectors=collectors,
        )

    @app.route("/map")
    def map_view():
        """Map view with positions from all collectors."""
        conn = get_db()
        with conn.cursor() as cur:
            cur.execute("""
                SELECT p.node_id, p.latitude, p.longitude, p.altitude, p.timestamp,
                       n.long_name, n.short_name, p.collector_id
                FROM latest_positions p
                JOIN nodes n ON p.node_id = n.node_id
                WHERE p.latitude IS NOT NULL AND p.longitude IS NOT NULL
                LIMIT 500
            """)
            positions = cur.fetchall()

        node_data = []
        for pos in positions:
            node_data.append({
                "node_id": pos["node_id"],
                "name": pos["long_name"] or pos["node_id"],
                "short_name": pos["short_name"],
                "latitude": float(pos["latitude"]),
                "longitude": float(pos["longitude"]),
                "altitude": pos["altitude"],
                "timestamp": pos["timestamp"].isoformat() if pos["timestamp"] else None,
                "collector_id": pos["collector_id"],
            })

        return render_template("map.html", nodes=node_data)

    @app.route("/nodes")
    def nodes_list():
        """Nodes list view."""
        conn = get_db()
        page = request.args.get("page", 1, type=int)
        collector = request.args.get("collector")
        limit = 50
        offset = (page - 1) * limit

        with conn.cursor() as cur:
            # Build query with optional collector filter
            where = ""
            params = []
            if collector:
                where = "WHERE collector_id = %s"
                params.append(collector)

            cur.execute(f"""
                SELECT * FROM nodes
                {where}
                ORDER BY last_seen DESC
                LIMIT %s OFFSET %s
            """, params + [limit, offset])
            nodes = cur.fetchall()

            cur.execute(f"SELECT COUNT(*) as count FROM nodes {where}", params)
            total = cur.fetchone()["count"]

            # Get collectors for filter dropdown
            cur.execute("SELECT collector_id FROM collectors ORDER BY collector_id")
            collectors = [r["collector_id"] for r in cur.fetchall()]

        return render_template(
            "nodes.html",
            nodes=nodes,
            page=page,
            total=total,
            pages=(total + limit - 1) // limit,
            collector_filter=collector,
            collectors=collectors,
        )

    @app.route("/nodes/<node_id>")
    def node_detail(node_id):
        """Node detail view."""
        conn = get_db()
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM nodes WHERE node_id = %s", (node_id,))
            node = cur.fetchone()
            if not node:
                return render_template("404.html", message=f"Node {node_id} not found"), 404

            cur.execute("""
                SELECT * FROM positions
                WHERE node_id = %s
                ORDER BY timestamp DESC
                LIMIT 100
            """, (node_id,))
            positions = cur.fetchall()

            cur.execute("""
                SELECT * FROM device_metrics
                WHERE node_id = %s
                ORDER BY timestamp DESC
                LIMIT 50
            """, (node_id,))
            metrics = cur.fetchall()

            cur.execute("""
                SELECT * FROM messages
                WHERE from_node = %s
                ORDER BY timestamp DESC
                LIMIT 20
            """, (node_id,))
            messages = cur.fetchall()

        return render_template(
            "node_detail.html",
            node=node,
            positions=positions,
            metrics=metrics,
            messages=messages,
        )

    @app.route("/messages")
    def messages_view():
        """Messages view."""
        conn = get_db()
        page = request.args.get("page", 1, type=int)
        from_node = request.args.get("from")
        to_node = request.args.get("to")
        collector = request.args.get("collector")
        limit = 50
        offset = (page - 1) * limit

        with conn.cursor() as cur:
            # Build query with filters
            conditions = []
            params = []
            if from_node:
                conditions.append("from_node = %s")
                params.append(from_node)
            if to_node:
                conditions.append("to_node = %s")
                params.append(to_node)
            if collector:
                conditions.append("collector_id = %s")
                params.append(collector)

            where = ""
            if conditions:
                where = "WHERE " + " AND ".join(conditions)

            cur.execute(f"""
                SELECT * FROM messages
                {where}
                ORDER BY timestamp DESC
                LIMIT %s OFFSET %s
            """, params + [limit, offset])
            messages = cur.fetchall()

            cur.execute(f"SELECT COUNT(*) as count FROM messages {where}", params)
            total = cur.fetchone()["count"]

        return render_template(
            "messages.html",
            messages=messages,
            page=page,
            total=total,
            pages=(total + limit - 1) // limit,
            from_filter=from_node,
            to_filter=to_node,
        )

    @app.route("/collectors")
    def collectors_view():
        """Collectors status view."""
        conn = get_db()
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM collector_health")
            collectors = cur.fetchall()

        return render_template("collectors.html", collectors=collectors)

    # API routes
    @app.route("/api/nodes")
    def api_nodes():
        """Get all nodes."""
        conn = get_db()
        limit = request.args.get("limit", 100, type=int)
        offset = request.args.get("offset", 0, type=int)
        collector = request.args.get("collector")

        with conn.cursor() as cur:
            if collector:
                cur.execute("""
                    SELECT * FROM nodes
                    WHERE collector_id = %s
                    ORDER BY last_seen DESC
                    LIMIT %s OFFSET %s
                """, (collector, limit, offset))
            else:
                cur.execute("""
                    SELECT * FROM nodes
                    ORDER BY last_seen DESC
                    LIMIT %s OFFSET %s
                """, (limit, offset))
            nodes = cur.fetchall()

            cur.execute("SELECT COUNT(*) as count FROM nodes")
            total = cur.fetchone()["count"]

        return jsonify({
            "nodes": [_row_to_dict(n) for n in nodes],
            "total": total,
        })

    @app.route("/api/nodes/<node_id>")
    def api_node(node_id):
        """Get single node."""
        conn = get_db()
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM nodes WHERE node_id = %s", (node_id,))
            node = cur.fetchone()
            if not node:
                return jsonify({"error": "Node not found"}), 404

        return jsonify(_row_to_dict(node))

    @app.route("/api/stats")
    def api_stats():
        """Get database statistics."""
        conn = get_db()
        with conn.cursor() as cur:
            stats = {}
            for table in ["nodes", "positions", "device_metrics", "messages", "gateways", "collectors"]:
                cur.execute(f"SELECT COUNT(*) as count FROM {table}")
                stats[f"total_{table}"] = cur.fetchone()["count"]

            cur.execute("""
                SELECT COUNT(*) as count FROM nodes
                WHERE last_seen > NOW() - INTERVAL '1 hour'
            """)
            stats["active_nodes"] = cur.fetchone()["count"]

        return jsonify(stats)

    @app.route("/api/collectors")
    def api_collectors():
        """Get collector status."""
        conn = get_db()
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM collector_health")
            collectors = cur.fetchall()

        return jsonify({
            "collectors": [_row_to_dict(c) for c in collectors],
        })

    @app.route("/api/positions")
    def api_positions():
        """Get latest positions."""
        conn = get_db()
        limit = request.args.get("limit", 100, type=int)

        with conn.cursor() as cur:
            cur.execute("""
                SELECT * FROM latest_positions
                LIMIT %s
            """, (limit,))
            positions = cur.fetchall()

        return jsonify({
            "positions": [_row_to_dict(p) for p in positions],
        })

    @app.route("/api/messages")
    def api_messages():
        """Get messages."""
        conn = get_db()
        limit = request.args.get("limit", 100, type=int)
        offset = request.args.get("offset", 0, type=int)

        with conn.cursor() as cur:
            cur.execute("""
                SELECT * FROM messages
                ORDER BY timestamp DESC
                LIMIT %s OFFSET %s
            """, (limit, offset))
            messages = cur.fetchall()

            cur.execute("SELECT COUNT(*) as count FROM messages")
            total = cur.fetchone()["count"]

        return jsonify({
            "messages": [_row_to_dict(m) for m in messages],
            "total": total,
        })

    return app


def _row_to_dict(row) -> dict:
    """Convert database row to dict with datetime serialization."""
    if row is None:
        return None
    result = dict(row)
    for key, value in result.items():
        if isinstance(value, datetime):
            result[key] = value.isoformat()
    return result


# Application entry point
app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
