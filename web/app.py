"""Flask web application for Meshtastic Monitor."""

from datetime import datetime
from functools import wraps
from pathlib import Path

from flask import Flask, jsonify, render_template, request, g

from mesh_monitor.db import Database


def create_app(db_path: str = "mesh.db") -> Flask:
    """Create and configure the Flask application.

    Args:
        db_path: Path to SQLite database.

    Returns:
        Configured Flask application.
    """
    app = Flask(
        __name__,
        template_folder=str(Path(__file__).parent / "templates"),
        static_folder=str(Path(__file__).parent / "static"),
    )

    app.config["DB_PATH"] = db_path

    def get_db() -> Database:
        """Get database instance for current request."""
        if "db" not in g:
            g.db = Database(app.config["DB_PATH"])
        return g.db

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
                value = datetime.fromisoformat(value)
            except ValueError:
                return value

        now = datetime.now()
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
        """Dashboard view."""
        db = get_db()
        stats = db.get_stats()
        nodes = db.get_all_nodes(limit=10)
        messages = db.get_messages(limit=10)

        # Calculate active nodes (heard in last hour)
        active_count = 0
        for node in db.get_all_nodes(limit=1000):
            if node.last_seen:
                diff = (datetime.now() - node.last_seen).total_seconds()
                if diff < 3600:
                    active_count += 1

        return render_template(
            "dashboard.html",
            stats=stats,
            nodes=nodes,
            messages=messages,
            active_count=active_count,
        )

    @app.route("/map")
    def map_view():
        """Map view."""
        db = get_db()
        positions = db.get_latest_positions(limit=500)
        nodes = {n.node_id: n for n in db.get_all_nodes(limit=1000)}

        # Build node data with positions
        node_data = []
        for pos in positions:
            if pos.latitude and pos.longitude:
                node = nodes.get(pos.node_id)
                node_data.append({
                    "node_id": pos.node_id,
                    "name": node.long_name if node else pos.node_id,
                    "short_name": node.short_name if node else None,
                    "latitude": pos.latitude,
                    "longitude": pos.longitude,
                    "altitude": pos.altitude,
                    "timestamp": pos.timestamp.isoformat() if pos.timestamp else None,
                })

        return render_template("map.html", nodes=node_data)

    @app.route("/nodes")
    def nodes_list():
        """Nodes list view."""
        db = get_db()
        page = request.args.get("page", 1, type=int)
        limit = 50
        offset = (page - 1) * limit

        nodes = db.get_all_nodes(limit=limit, offset=offset)
        total = db.get_node_count()

        # Get latest metrics for each node
        node_metrics = {}
        for node in nodes:
            metrics = db.get_latest_device_metrics(node.node_id)
            if metrics:
                node_metrics[node.node_id] = metrics

        return render_template(
            "nodes.html",
            nodes=nodes,
            node_metrics=node_metrics,
            page=page,
            total=total,
            pages=(total + limit - 1) // limit,
        )

    @app.route("/nodes/<node_id>")
    def node_detail(node_id):
        """Node detail view."""
        db = get_db()
        node = db.get_node(node_id)
        if not node:
            return render_template("404.html", message=f"Node {node_id} not found"), 404

        positions = db.get_positions(node_id, limit=100)
        metrics = db.get_device_metrics(node_id, limit=50)
        messages = db.get_messages(from_node=node_id, limit=20)

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
        db = get_db()
        page = request.args.get("page", 1, type=int)
        from_node = request.args.get("from")
        to_node = request.args.get("to")
        limit = 50
        offset = (page - 1) * limit

        messages = db.get_messages(
            from_node=from_node,
            to_node=to_node,
            limit=limit,
            offset=offset,
        )
        total = db.get_message_count()

        return render_template(
            "messages.html",
            messages=messages,
            page=page,
            total=total,
            pages=(total + limit - 1) // limit,
            from_filter=from_node,
            to_filter=to_node,
        )

    # API routes
    @app.route("/api/nodes")
    def api_nodes():
        """Get all nodes."""
        db = get_db()
        limit = request.args.get("limit", 100, type=int)
        offset = request.args.get("offset", 0, type=int)

        nodes = db.get_all_nodes(limit=limit, offset=offset)
        return jsonify({
            "nodes": [_node_to_dict(n) for n in nodes],
            "total": db.get_node_count(),
        })

    @app.route("/api/nodes/<node_id>")
    def api_node(node_id):
        """Get single node."""
        db = get_db()
        node = db.get_node(node_id)
        if not node:
            return jsonify({"error": "Node not found"}), 404

        return jsonify(_node_to_dict(node))

    @app.route("/api/nodes/<node_id>/positions")
    def api_node_positions(node_id):
        """Get positions for a node."""
        db = get_db()
        limit = request.args.get("limit", 100, type=int)
        offset = request.args.get("offset", 0, type=int)

        positions = db.get_positions(node_id, limit=limit, offset=offset)
        return jsonify({
            "positions": [_position_to_dict(p) for p in positions],
        })

    @app.route("/api/nodes/<node_id>/metrics")
    def api_node_metrics(node_id):
        """Get metrics for a node."""
        db = get_db()
        limit = request.args.get("limit", 100, type=int)
        offset = request.args.get("offset", 0, type=int)

        metrics = db.get_device_metrics(node_id, limit=limit, offset=offset)
        return jsonify({
            "metrics": [_metrics_to_dict(m) for m in metrics],
        })

    @app.route("/api/positions")
    def api_positions():
        """Get latest positions for all nodes."""
        db = get_db()
        limit = request.args.get("limit", 100, type=int)

        positions = db.get_latest_positions(limit=limit)
        nodes = {n.node_id: n for n in db.get_all_nodes(limit=1000)}

        result = []
        for pos in positions:
            data = _position_to_dict(pos)
            node = nodes.get(pos.node_id)
            if node:
                data["node_name"] = node.long_name
                data["node_short_name"] = node.short_name
            result.append(data)

        return jsonify({"positions": result})

    @app.route("/api/messages")
    def api_messages():
        """Get messages."""
        db = get_db()
        limit = request.args.get("limit", 100, type=int)
        offset = request.args.get("offset", 0, type=int)
        from_node = request.args.get("from")
        to_node = request.args.get("to")

        messages = db.get_messages(
            from_node=from_node,
            to_node=to_node,
            limit=limit,
            offset=offset,
        )
        return jsonify({
            "messages": [_message_to_dict(m) for m in messages],
            "total": db.get_message_count(),
        })

    @app.route("/api/stats")
    def api_stats():
        """Get database statistics."""
        db = get_db()
        stats = db.get_stats()

        # Calculate active nodes
        active_count = 0
        for node in db.get_all_nodes(limit=1000):
            if node.last_seen:
                diff = (datetime.now() - node.last_seen).total_seconds()
                if diff < 3600:
                    active_count += 1

        stats["active_nodes"] = active_count
        return jsonify(stats)

    @app.route("/api/gateways")
    def api_gateways():
        """Get gateway status."""
        db = get_db()
        gateways = db.get_all_gateways()
        return jsonify({
            "gateways": [_gateway_to_dict(gw) for gw in gateways],
        })

    return app


# Helper functions for JSON serialization

def _node_to_dict(node) -> dict:
    """Convert Node to dict."""
    return {
        "node_id": node.node_id,
        "node_num": node.node_num,
        "long_name": node.long_name,
        "short_name": node.short_name,
        "hw_model": node.hw_model,
        "firmware_version": node.firmware_version,
        "mac_addr": node.mac_addr,
        "first_seen": node.first_seen.isoformat() if node.first_seen else None,
        "last_seen": node.last_seen.isoformat() if node.last_seen else None,
    }


def _position_to_dict(pos) -> dict:
    """Convert Position to dict."""
    return {
        "id": pos.id,
        "node_id": pos.node_id,
        "timestamp": pos.timestamp.isoformat() if pos.timestamp else None,
        "latitude": pos.latitude,
        "longitude": pos.longitude,
        "altitude": pos.altitude,
        "location_source": pos.location_source,
    }


def _metrics_to_dict(metrics) -> dict:
    """Convert DeviceMetrics to dict."""
    return {
        "id": metrics.id,
        "node_id": metrics.node_id,
        "timestamp": metrics.timestamp.isoformat() if metrics.timestamp else None,
        "battery_level": metrics.battery_level,
        "voltage": metrics.voltage,
        "channel_utilization": metrics.channel_utilization,
        "air_util_tx": metrics.air_util_tx,
        "uptime_seconds": metrics.uptime_seconds,
    }


def _message_to_dict(msg) -> dict:
    """Convert Message to dict."""
    return {
        "id": msg.id,
        "timestamp": msg.timestamp.isoformat() if msg.timestamp else None,
        "from_node": msg.from_node,
        "to_node": msg.to_node,
        "channel": msg.channel,
        "text": msg.text,
        "port_num": msg.port_num,
    }


def _gateway_to_dict(gw) -> dict:
    """Convert Gateway to dict."""
    return {
        "id": gw.id,
        "host": gw.host,
        "port": gw.port,
        "node_id": gw.node_id,
        "first_seen": gw.first_seen.isoformat() if gw.first_seen else None,
        "last_seen": gw.last_seen.isoformat() if gw.last_seen else None,
    }
