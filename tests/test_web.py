"""Tests for the web UI module."""

import json
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from mesh_monitor.db import Database
from web.app import create_app


@pytest.fixture
def db_path():
    """Create a temporary database path."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    yield path
    Path(path).unlink(missing_ok=True)


@pytest.fixture
def populated_db(db_path):
    """Create a database with sample data."""
    db = Database(db_path)

    # Add nodes
    db.upsert_node(
        node_id="!node1",
        node_num=1234567,
        long_name="Test Node 1",
        short_name="TN1",
        hw_model="TBEAM",
        firmware_version="2.0.0",
    )
    db.upsert_node(
        node_id="!node2",
        node_num=7654321,
        long_name="Test Node 2",
        short_name="TN2",
        hw_model="HELTEC",
    )

    # Add positions
    db.insert_position(
        node_id="!node1",
        latitude=39.114875,
        longitude=-84.344302,
        altitude=284,
        timestamp=datetime(2024, 1, 15, 12, 0, 0),
    )

    # Add metrics
    db.insert_device_metrics(
        node_id="!node1",
        battery_level=85,
        voltage=4.1,
        channel_utilization=12.5,
        air_util_tx=2.3,
        uptime_seconds=3600,
    )

    # Add messages
    db.insert_message(
        from_node="!node1",
        to_node="!node2",
        text="Hello!",
        channel=0,
    )

    # Add gateway
    db.upsert_gateway("192.168.1.100", 4403, "!gateway1")

    return db_path


@pytest.fixture
def app(populated_db):
    """Create test Flask application."""
    app = create_app(populated_db)
    app.config["TESTING"] = True
    return app


@pytest.fixture
def client(app):
    """Create test client."""
    return app.test_client()


class TestDashboard:
    """Tests for dashboard view."""

    def test_dashboard_loads(self, client):
        """Test dashboard page loads."""
        response = client.get("/")
        assert response.status_code == 200
        assert b"Dashboard" in response.data

    def test_dashboard_shows_stats(self, client):
        """Test dashboard shows statistics."""
        response = client.get("/")
        assert response.status_code == 200
        # Should show node count
        assert b"Total Nodes" in response.data

    def test_dashboard_shows_nodes(self, client):
        """Test dashboard shows recent nodes."""
        response = client.get("/")
        assert response.status_code == 200
        assert b"Test Node 1" in response.data


class TestMapView:
    """Tests for map view."""

    def test_map_loads(self, client):
        """Test map page loads."""
        response = client.get("/map")
        assert response.status_code == 200
        assert b"Map" in response.data

    def test_map_includes_leaflet(self, client):
        """Test map includes Leaflet library."""
        response = client.get("/map")
        assert response.status_code == 200
        assert b"leaflet" in response.data.lower()


class TestNodesView:
    """Tests for nodes list view."""

    def test_nodes_list_loads(self, client):
        """Test nodes list page loads."""
        response = client.get("/nodes")
        assert response.status_code == 200
        assert b"Nodes" in response.data

    def test_nodes_list_shows_nodes(self, client):
        """Test nodes list shows nodes."""
        response = client.get("/nodes")
        assert response.status_code == 200
        assert b"!node1" in response.data
        assert b"Test Node 1" in response.data

    def test_nodes_pagination(self, client):
        """Test nodes list pagination."""
        response = client.get("/nodes?page=1")
        assert response.status_code == 200


class TestNodeDetail:
    """Tests for node detail view."""

    def test_node_detail_loads(self, client):
        """Test node detail page loads."""
        response = client.get("/nodes/!node1")
        assert response.status_code == 200
        assert b"Test Node 1" in response.data

    def test_node_detail_shows_info(self, client):
        """Test node detail shows node info."""
        response = client.get("/nodes/!node1")
        assert response.status_code == 200
        assert b"TBEAM" in response.data
        assert b"2.0.0" in response.data

    def test_node_detail_not_found(self, client):
        """Test node detail 404 for nonexistent node."""
        response = client.get("/nodes/!nonexistent")
        assert response.status_code == 404


class TestMessagesView:
    """Tests for messages view."""

    def test_messages_loads(self, client):
        """Test messages page loads."""
        response = client.get("/messages")
        assert response.status_code == 200
        assert b"Messages" in response.data

    def test_messages_shows_messages(self, client):
        """Test messages page shows messages."""
        response = client.get("/messages")
        assert response.status_code == 200
        assert b"Hello!" in response.data

    def test_messages_filter_from(self, client):
        """Test messages filter by from node."""
        response = client.get("/messages?from=!node1")
        assert response.status_code == 200
        assert b"Hello!" in response.data


class TestAPINodes:
    """Tests for nodes API."""

    def test_api_nodes(self, client):
        """Test GET /api/nodes."""
        response = client.get("/api/nodes")
        assert response.status_code == 200

        data = json.loads(response.data)
        assert "nodes" in data
        assert "total" in data
        assert len(data["nodes"]) == 2

    def test_api_nodes_limit(self, client):
        """Test GET /api/nodes with limit."""
        response = client.get("/api/nodes?limit=1")
        assert response.status_code == 200

        data = json.loads(response.data)
        assert len(data["nodes"]) == 1

    def test_api_node_detail(self, client):
        """Test GET /api/nodes/<id>."""
        response = client.get("/api/nodes/!node1")
        assert response.status_code == 200

        data = json.loads(response.data)
        assert data["node_id"] == "!node1"
        assert data["long_name"] == "Test Node 1"

    def test_api_node_not_found(self, client):
        """Test GET /api/nodes/<id> for nonexistent node."""
        response = client.get("/api/nodes/!nonexistent")
        assert response.status_code == 404


class TestAPIPositions:
    """Tests for positions API."""

    def test_api_node_positions(self, client):
        """Test GET /api/nodes/<id>/positions."""
        response = client.get("/api/nodes/!node1/positions")
        assert response.status_code == 200

        data = json.loads(response.data)
        assert "positions" in data
        assert len(data["positions"]) == 1
        assert data["positions"][0]["latitude"] == 39.114875

    def test_api_positions(self, client):
        """Test GET /api/positions."""
        response = client.get("/api/positions")
        assert response.status_code == 200

        data = json.loads(response.data)
        assert "positions" in data


class TestAPIMetrics:
    """Tests for metrics API."""

    def test_api_node_metrics(self, client):
        """Test GET /api/nodes/<id>/metrics."""
        response = client.get("/api/nodes/!node1/metrics")
        assert response.status_code == 200

        data = json.loads(response.data)
        assert "metrics" in data
        assert len(data["metrics"]) == 1
        assert data["metrics"][0]["battery_level"] == 85


class TestAPIMessages:
    """Tests for messages API."""

    def test_api_messages(self, client):
        """Test GET /api/messages."""
        response = client.get("/api/messages")
        assert response.status_code == 200

        data = json.loads(response.data)
        assert "messages" in data
        assert "total" in data
        assert len(data["messages"]) == 1

    def test_api_messages_filter(self, client):
        """Test GET /api/messages with filter."""
        response = client.get("/api/messages?from=!node1")
        assert response.status_code == 200

        data = json.loads(response.data)
        assert len(data["messages"]) == 1


class TestAPIStats:
    """Tests for stats API."""

    def test_api_stats(self, client):
        """Test GET /api/stats."""
        response = client.get("/api/stats")
        assert response.status_code == 200

        data = json.loads(response.data)
        assert data["total_nodes"] == 2
        assert data["total_positions"] == 1
        assert data["total_messages"] == 1


class TestAPIGateways:
    """Tests for gateways API."""

    def test_api_gateways(self, client):
        """Test GET /api/gateways."""
        response = client.get("/api/gateways")
        assert response.status_code == 200

        data = json.loads(response.data)
        assert "gateways" in data
        assert len(data["gateways"]) == 1
        assert data["gateways"][0]["host"] == "192.168.1.100"
