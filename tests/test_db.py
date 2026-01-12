"""Tests for the database layer."""

import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from mesh_monitor.db import Database, Node, Position, DeviceMetrics, Message, Gateway


@pytest.fixture
def db():
    """Create a temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    database = Database(db_path)
    yield database

    # Cleanup
    Path(db_path).unlink(missing_ok=True)


class TestGateway:
    """Tests for gateway operations."""

    def test_upsert_gateway_new(self, db):
        """Test inserting a new gateway."""
        gateway_id = db.upsert_gateway("192.168.1.100", 4403)
        assert gateway_id == 1

        gateway = db.get_gateway(gateway_id)
        assert gateway is not None
        assert gateway.host == "192.168.1.100"
        assert gateway.port == 4403
        assert gateway.node_id is None

    def test_upsert_gateway_with_node_id(self, db):
        """Test inserting a gateway with node ID."""
        gateway_id = db.upsert_gateway("192.168.1.100", 4403, "!abc12345")

        gateway = db.get_gateway(gateway_id)
        assert gateway.node_id == "!abc12345"

    def test_upsert_gateway_update(self, db):
        """Test updating an existing gateway."""
        gateway_id1 = db.upsert_gateway("192.168.1.100", 4403)
        gateway_id2 = db.upsert_gateway("192.168.1.100", 4403, "!abc12345")

        # Should return same ID (upsert)
        assert gateway_id1 == gateway_id2

        gateway = db.get_gateway(gateway_id1)
        assert gateway.node_id == "!abc12345"

    def test_get_all_gateways(self, db):
        """Test getting all gateways."""
        db.upsert_gateway("192.168.1.100", 4403)
        db.upsert_gateway("192.168.1.101", 4403)

        gateways = db.get_all_gateways()
        assert len(gateways) == 2

    def test_get_nonexistent_gateway(self, db):
        """Test getting a gateway that doesn't exist."""
        gateway = db.get_gateway(999)
        assert gateway is None


class TestNode:
    """Tests for node operations."""

    def test_upsert_node_new(self, db):
        """Test inserting a new node."""
        db.upsert_node(
            node_id="!abc12345",
            node_num=123456789,
            long_name="Test Node",
            short_name="TEST",
            hw_model="TBEAM",
            firmware_version="2.0.0",
            mac_addr="AA:BB:CC:DD:EE:FF",
        )

        node = db.get_node("!abc12345")
        assert node is not None
        assert node.node_id == "!abc12345"
        assert node.node_num == 123456789
        assert node.long_name == "Test Node"
        assert node.short_name == "TEST"
        assert node.hw_model == "TBEAM"
        assert node.firmware_version == "2.0.0"

    def test_upsert_node_partial(self, db):
        """Test inserting a node with partial data."""
        db.upsert_node(node_id="!abc12345", long_name="Test Node")

        node = db.get_node("!abc12345")
        assert node.long_name == "Test Node"
        assert node.short_name is None

    def test_upsert_node_update(self, db):
        """Test updating an existing node."""
        db.upsert_node(node_id="!abc12345", long_name="Original Name")
        db.upsert_node(node_id="!abc12345", long_name="Updated Name")

        node = db.get_node("!abc12345")
        assert node.long_name == "Updated Name"

    def test_upsert_node_preserves_existing(self, db):
        """Test that upsert preserves existing data when new data is None."""
        db.upsert_node(node_id="!abc12345", long_name="Test", short_name="TST")
        db.upsert_node(node_id="!abc12345", hw_model="TBEAM")

        node = db.get_node("!abc12345")
        assert node.long_name == "Test"
        assert node.short_name == "TST"
        assert node.hw_model == "TBEAM"

    def test_get_all_nodes(self, db):
        """Test getting all nodes."""
        db.upsert_node(node_id="!node1", long_name="Node 1")
        db.upsert_node(node_id="!node2", long_name="Node 2")
        db.upsert_node(node_id="!node3", long_name="Node 3")

        nodes = db.get_all_nodes()
        assert len(nodes) == 3

    def test_get_all_nodes_with_limit(self, db):
        """Test getting nodes with limit."""
        for i in range(10):
            db.upsert_node(node_id=f"!node{i}", long_name=f"Node {i}")

        nodes = db.get_all_nodes(limit=5)
        assert len(nodes) == 5

    def test_get_all_nodes_with_offset(self, db):
        """Test getting nodes with offset."""
        for i in range(10):
            db.upsert_node(node_id=f"!node{i}", long_name=f"Node {i}")

        nodes = db.get_all_nodes(limit=5, offset=5)
        assert len(nodes) == 5

    def test_get_node_count(self, db):
        """Test getting node count."""
        assert db.get_node_count() == 0

        db.upsert_node(node_id="!node1")
        db.upsert_node(node_id="!node2")

        assert db.get_node_count() == 2

    def test_get_nonexistent_node(self, db):
        """Test getting a node that doesn't exist."""
        node = db.get_node("!nonexistent")
        assert node is None


class TestPosition:
    """Tests for position operations."""

    def test_insert_position(self, db):
        """Test inserting a position."""
        db.upsert_node(node_id="!abc12345")

        pos_id = db.insert_position(
            node_id="!abc12345",
            latitude=39.114875,
            longitude=-84.344302,
            altitude=284,
            location_source="LOC_INTERNAL",
        )

        assert pos_id == 1

    def test_insert_position_with_timestamp(self, db):
        """Test inserting a position with custom timestamp."""
        db.upsert_node(node_id="!abc12345")
        ts = datetime(2024, 1, 15, 12, 0, 0)

        db.insert_position(
            node_id="!abc12345",
            latitude=39.0,
            longitude=-84.0,
            timestamp=ts,
        )

        positions = db.get_positions("!abc12345")
        assert len(positions) == 1
        assert positions[0].timestamp == ts

    def test_get_positions(self, db):
        """Test getting positions for a node."""
        db.upsert_node(node_id="!abc12345")

        for i in range(5):
            db.insert_position(
                node_id="!abc12345",
                latitude=39.0 + i * 0.01,
                longitude=-84.0,
            )

        positions = db.get_positions("!abc12345")
        assert len(positions) == 5

    def test_get_positions_ordered_by_timestamp(self, db):
        """Test that positions are returned in reverse chronological order."""
        db.upsert_node(node_id="!abc12345")

        ts1 = datetime(2024, 1, 1)
        ts2 = datetime(2024, 1, 2)
        ts3 = datetime(2024, 1, 3)

        db.insert_position(node_id="!abc12345", latitude=1.0, timestamp=ts1)
        db.insert_position(node_id="!abc12345", latitude=2.0, timestamp=ts3)
        db.insert_position(node_id="!abc12345", latitude=3.0, timestamp=ts2)

        positions = db.get_positions("!abc12345")
        assert positions[0].timestamp == ts3
        assert positions[1].timestamp == ts2
        assert positions[2].timestamp == ts1

    def test_get_latest_positions(self, db):
        """Test getting latest position for each node."""
        db.upsert_node(node_id="!node1")
        db.upsert_node(node_id="!node2")

        ts1 = datetime(2024, 1, 1)
        ts2 = datetime(2024, 1, 2)

        db.insert_position(node_id="!node1", latitude=1.0, timestamp=ts1)
        db.insert_position(node_id="!node1", latitude=2.0, timestamp=ts2)
        db.insert_position(node_id="!node2", latitude=3.0, timestamp=ts1)

        latest = db.get_latest_positions()
        assert len(latest) == 2

        # Find node1's latest
        node1_pos = next(p for p in latest if p.node_id == "!node1")
        assert node1_pos.latitude == 2.0


class TestDeviceMetrics:
    """Tests for device metrics operations."""

    def test_insert_device_metrics(self, db):
        """Test inserting device metrics."""
        db.upsert_node(node_id="!abc12345")

        metrics_id = db.insert_device_metrics(
            node_id="!abc12345",
            battery_level=85,
            voltage=4.1,
            channel_utilization=12.5,
            air_util_tx=2.3,
            uptime_seconds=3600,
        )

        assert metrics_id == 1

    def test_get_device_metrics(self, db):
        """Test getting device metrics for a node."""
        db.upsert_node(node_id="!abc12345")

        for i in range(5):
            db.insert_device_metrics(
                node_id="!abc12345",
                battery_level=100 - i * 5,
            )

        metrics = db.get_device_metrics("!abc12345")
        assert len(metrics) == 5

    def test_get_latest_device_metrics(self, db):
        """Test getting latest device metrics for a node."""
        db.upsert_node(node_id="!abc12345")

        ts1 = datetime(2024, 1, 1)
        ts2 = datetime(2024, 1, 2)

        db.insert_device_metrics(node_id="!abc12345", battery_level=90, timestamp=ts1)
        db.insert_device_metrics(node_id="!abc12345", battery_level=85, timestamp=ts2)

        latest = db.get_latest_device_metrics("!abc12345")
        assert latest is not None
        assert latest.battery_level == 85

    def test_get_latest_device_metrics_none(self, db):
        """Test getting latest metrics when none exist."""
        latest = db.get_latest_device_metrics("!nonexistent")
        assert latest is None


class TestMessage:
    """Tests for message operations."""

    def test_insert_message(self, db):
        """Test inserting a message."""
        msg_id = db.insert_message(
            from_node="!sender",
            to_node="!receiver",
            channel=0,
            text="Hello, mesh!",
            port_num="TEXT_MESSAGE_APP",
        )

        assert msg_id == 1

    def test_get_messages(self, db):
        """Test getting messages."""
        for i in range(5):
            db.insert_message(
                from_node="!sender",
                to_node="!receiver",
                text=f"Message {i}",
            )

        messages = db.get_messages()
        assert len(messages) == 5

    def test_get_messages_filter_by_from_node(self, db):
        """Test filtering messages by sender."""
        db.insert_message(from_node="!sender1", text="From sender 1")
        db.insert_message(from_node="!sender2", text="From sender 2")
        db.insert_message(from_node="!sender1", text="Also from sender 1")

        messages = db.get_messages(from_node="!sender1")
        assert len(messages) == 2

    def test_get_messages_filter_by_to_node(self, db):
        """Test filtering messages by recipient."""
        db.insert_message(to_node="!receiver1", text="To receiver 1")
        db.insert_message(to_node="!receiver2", text="To receiver 2")

        messages = db.get_messages(to_node="!receiver1")
        assert len(messages) == 1

    def test_get_message_count(self, db):
        """Test getting message count."""
        assert db.get_message_count() == 0

        db.insert_message(text="Test 1")
        db.insert_message(text="Test 2")

        assert db.get_message_count() == 2


class TestStats:
    """Tests for statistics."""

    def test_get_stats_empty(self, db):
        """Test getting stats from empty database."""
        stats = db.get_stats()

        assert stats["total_nodes"] == 0
        assert stats["total_positions"] == 0
        assert stats["total_metrics"] == 0
        assert stats["total_messages"] == 0
        assert stats["total_gateways"] == 0

    def test_get_stats_with_data(self, db):
        """Test getting stats with data."""
        db.upsert_gateway("192.168.1.1")
        db.upsert_node(node_id="!node1")
        db.upsert_node(node_id="!node2")
        db.insert_position(node_id="!node1", latitude=39.0)
        db.insert_device_metrics(node_id="!node1", battery_level=90)
        db.insert_message(text="Hello")

        stats = db.get_stats()

        assert stats["total_nodes"] == 2
        assert stats["total_positions"] == 1
        assert stats["total_metrics"] == 1
        assert stats["total_messages"] == 1
        assert stats["total_gateways"] == 1


class TestDatabaseInit:
    """Tests for database initialization."""

    def test_creates_database_file(self):
        """Test that database file is created."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            assert not db_path.exists()

            Database(str(db_path))

            assert db_path.exists()

    def test_schema_created(self, db):
        """Test that all tables are created."""
        with db._get_connection() as conn:
            tables = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
            table_names = {t[0] for t in tables}

            assert "gateways" in table_names
            assert "nodes" in table_names
            assert "positions" in table_names
            assert "device_metrics" in table_names
            assert "messages" in table_names

    def test_indexes_created(self, db):
        """Test that indexes are created."""
        with db._get_connection() as conn:
            indexes = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
            ).fetchall()
            index_names = {i[0] for i in indexes}

            assert "idx_positions_node_id" in index_names
            assert "idx_positions_timestamp" in index_names
            assert "idx_device_metrics_node_id" in index_names
