"""Tests for the collector module."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from mesh_monitor.collector import MeshCollector
from mesh_monitor.db import Database


@pytest.fixture
def db():
    """Create a temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    database = Database(db_path)
    yield database

    Path(db_path).unlink(missing_ok=True)


@pytest.fixture
def collector(db):
    """Create a collector with test database."""
    coll = MeshCollector(db)
    yield coll
    coll.stop()


class TestCollectorInit:
    """Tests for collector initialization."""

    def test_init(self, db):
        """Test collector initialization."""
        collector = MeshCollector(db)
        assert collector.db is db
        assert collector.interfaces == {}
        assert collector.gateway_ids == {}
        assert collector._running is False
        collector.stop()

    def test_subscriptions_cleanup(self, db):
        """Test that subscriptions are cleaned up on stop."""
        collector = MeshCollector(db)
        collector.stop()
        # Should not raise even if called multiple times
        collector.stop()


class TestPacketHandling:
    """Tests for packet processing."""

    def test_handle_text_message(self, collector, db):
        """Test handling a text message packet."""
        # Create a mock interface
        mock_interface = MagicMock()
        mock_interface.hostname = "192.168.1.1"
        mock_interface.portNumber = 4403

        # Register gateway
        gateway_id = db.upsert_gateway("192.168.1.1", 4403)
        collector.gateway_ids["192.168.1.1:4403"] = gateway_id

        packet = {
            "fromId": "!sender123",
            "toId": "!receiver456",
            "channel": 0,
            "decoded": {
                "portnum": "TEXT_MESSAGE_APP",
                "text": "Hello, mesh network!",
            },
        }

        collector._handle_text_message(packet, mock_interface)

        # Verify message was stored
        messages = db.get_messages()
        assert len(messages) == 1
        assert messages[0].from_node == "!sender123"
        assert messages[0].to_node == "!receiver456"
        assert messages[0].text == "Hello, mesh network!"
        assert messages[0].channel == 0

    def test_handle_text_message_broadcast(self, collector, db):
        """Test handling a broadcast text message."""
        mock_interface = MagicMock()
        mock_interface.hostname = "192.168.1.1"
        mock_interface.portNumber = 4403

        packet = {
            "fromId": "!sender123",
            "toId": "^all",
            "channel": 0,
            "decoded": {
                "portnum": "TEXT_MESSAGE_APP",
                "text": "Broadcast message",
            },
        }

        collector._handle_text_message(packet, mock_interface)

        messages = db.get_messages()
        assert len(messages) == 1
        assert messages[0].to_node is None  # ^all converted to None

    def test_handle_position(self, collector, db):
        """Test handling a position packet."""
        packet = {
            "fromId": "!node12345",
            "decoded": {
                "portnum": "POSITION_APP",
                "position": {
                    "latitudeI": 391148750,  # 39.114875
                    "longitudeI": -843443028,  # -84.3443028
                    "altitude": 284,
                    "locationSource": "LOC_INTERNAL",
                    "time": 1704067200,  # 2024-01-01 00:00:00 UTC
                },
            },
        }

        collector._handle_position(packet)

        # Verify node was created
        node = db.get_node("!node12345")
        assert node is not None

        # Verify position was stored
        positions = db.get_positions("!node12345")
        assert len(positions) == 1
        assert abs(positions[0].latitude - 39.114875) < 0.0001
        assert abs(positions[0].longitude - (-84.3443028)) < 0.0001
        assert positions[0].altitude == 284

    def test_handle_position_no_from_id(self, collector, db):
        """Test that position without from_id is ignored."""
        packet = {
            "decoded": {
                "portnum": "POSITION_APP",
                "position": {
                    "latitudeI": 391148750,
                    "longitudeI": -843443028,
                },
            },
        }

        collector._handle_position(packet)

        # Should not create any positions
        assert db.get_stats()["total_positions"] == 0

    def test_handle_telemetry(self, collector, db):
        """Test handling a telemetry packet."""
        packet = {
            "fromId": "!node12345",
            "decoded": {
                "portnum": "TELEMETRY_APP",
                "telemetry": {
                    "deviceMetrics": {
                        "batteryLevel": 85,
                        "voltage": 4.1,
                        "channelUtilization": 12.5,
                        "airUtilTx": 2.3,
                        "uptimeSeconds": 3600,
                    },
                },
            },
        }

        collector._handle_telemetry(packet)

        # Verify node was created
        node = db.get_node("!node12345")
        assert node is not None

        # Verify metrics were stored
        metrics = db.get_device_metrics("!node12345")
        assert len(metrics) == 1
        assert metrics[0].battery_level == 85
        assert metrics[0].voltage == 4.1
        assert metrics[0].channel_utilization == 12.5

    def test_handle_telemetry_no_device_metrics(self, collector, db):
        """Test telemetry packet without device metrics is handled."""
        packet = {
            "fromId": "!node12345",
            "decoded": {
                "portnum": "TELEMETRY_APP",
                "telemetry": {
                    "environmentMetrics": {
                        "temperature": 25.0,
                    },
                },
            },
        }

        collector._handle_telemetry(packet)

        # Should not create any metrics
        assert db.get_stats()["total_metrics"] == 0

    def test_handle_nodeinfo(self, collector, db):
        """Test handling a nodeinfo packet."""
        packet = {
            "decoded": {
                "portnum": "NODEINFO_APP",
                "user": {
                    "id": "!node12345",
                    "longName": "Test Node",
                    "shortName": "TEST",
                    "hwModel": "TBEAM",
                    "macaddr": "AA:BB:CC:DD:EE:FF",
                },
            },
        }

        collector._handle_nodeinfo(packet)

        node = db.get_node("!node12345")
        assert node is not None
        assert node.long_name == "Test Node"
        assert node.short_name == "TEST"
        assert node.hw_model == "TBEAM"

    def test_process_packet_routing(self, collector, db):
        """Test that packets are routed to correct handlers."""
        mock_interface = MagicMock()

        # Text message
        text_packet = {
            "fromId": "!sender",
            "decoded": {"portnum": "TEXT_MESSAGE_APP", "text": "Test"},
        }
        collector._process_packet(text_packet, mock_interface)
        assert db.get_message_count() == 1

        # Position
        pos_packet = {
            "fromId": "!node1",
            "decoded": {
                "portnum": "POSITION_APP",
                "position": {"latitudeI": 390000000, "longitudeI": -840000000},
            },
        }
        collector._process_packet(pos_packet, mock_interface)
        assert db.get_stats()["total_positions"] == 1

        # Telemetry
        telem_packet = {
            "fromId": "!node2",
            "decoded": {
                "portnum": "TELEMETRY_APP",
                "telemetry": {"deviceMetrics": {"batteryLevel": 90}},
            },
        }
        collector._process_packet(telem_packet, mock_interface)
        assert db.get_stats()["total_metrics"] == 1


class TestNodeDatabaseSync:
    """Tests for node database synchronization."""

    def test_process_node_info(self, collector, db):
        """Test processing node info from node database."""
        node = {
            "num": 123456789,
            "user": {
                "id": "!node12345",
                "longName": "Test Node",
                "shortName": "TEST",
                "hwModel": "TBEAM",
            },
            "position": {
                "latitudeI": 391000000,
                "longitudeI": -840000000,
                "altitude": 200,
            },
            "deviceMetrics": {
                "batteryLevel": 75,
                "voltage": 3.9,
            },
        }

        collector._process_node_info(node)

        # Verify node
        db_node = db.get_node("!node12345")
        assert db_node is not None
        assert db_node.node_num == 123456789
        assert db_node.long_name == "Test Node"

        # Verify position
        positions = db.get_positions("!node12345")
        assert len(positions) == 1

        # Verify metrics
        metrics = db.get_device_metrics("!node12345")
        assert len(metrics) == 1
        assert metrics[0].battery_level == 75

    def test_sync_node_db(self, collector, db):
        """Test syncing node database from interface."""
        mock_interface = MagicMock()
        mock_interface.nodes = {
            "!node1": {
                "num": 1,
                "user": {"id": "!node1", "longName": "Node 1"},
            },
            "!node2": {
                "num": 2,
                "user": {"id": "!node2", "longName": "Node 2"},
            },
        }

        collector._sync_node_db(mock_interface)

        assert db.get_node_count() == 2
        assert db.get_node("!node1").long_name == "Node 1"
        assert db.get_node("!node2").long_name == "Node 2"

    def test_sync_node_db_empty(self, collector, db):
        """Test syncing empty node database."""
        mock_interface = MagicMock()
        mock_interface.nodes = {}

        collector._sync_node_db(mock_interface)

        assert db.get_node_count() == 0


class TestCallbacks:
    """Tests for collector callbacks."""

    def test_connection_callback(self, collector):
        """Test connection callback is called."""
        callback_called = []

        def on_connect(key):
            callback_called.append(key)

        collector.set_on_connection_callback(on_connect)

        # Simulate connection event
        mock_interface = MagicMock()
        mock_interface.hostname = "192.168.1.1"
        mock_interface.portNumber = 4403
        mock_interface.myInfo = None
        mock_interface.nodes = {}

        collector._on_connection(mock_interface)

        assert len(callback_called) == 1
        assert callback_called[0] == "192.168.1.1:4403"

    def test_disconnect_callback(self, collector):
        """Test disconnect callback is called."""
        callback_called = []

        def on_disconnect(key):
            callback_called.append(key)

        collector.set_on_disconnect_callback(on_disconnect)

        # Simulate disconnect event
        mock_interface = MagicMock()
        mock_interface.hostname = "192.168.1.1"
        mock_interface.portNumber = 4403

        collector._on_disconnect(mock_interface)

        assert len(callback_called) == 1
        assert callback_called[0] == "192.168.1.1:4403"


class TestConnectionManagement:
    """Tests for connection management."""

    def test_connect(self, collector, db):
        """Test connecting to a gateway."""
        mock_interface = MagicMock()
        mock_tcp_class = MagicMock(return_value=mock_interface)

        # Patch the import inside connect method
        mock_module = MagicMock()
        mock_module.TCPInterface = mock_tcp_class

        with patch.dict("sys.modules", {"meshtastic.tcp_interface": mock_module}):
            result = collector.connect("192.168.1.1", 4403)

        assert result is True
        assert "192.168.1.1:4403" in collector.interfaces
        assert "192.168.1.1:4403" in collector.gateway_ids

        # Verify gateway was created in database
        gateways = db.get_all_gateways()
        assert len(gateways) == 1
        assert gateways[0].host == "192.168.1.1"
        assert gateways[0].port == 4403

    def test_connect_already_connected(self, collector, db):
        """Test connecting when already connected."""
        # Add a fake connection
        collector.interfaces["192.168.1.1:4403"] = MagicMock()

        result = collector.connect("192.168.1.1", 4403)
        assert result is False

    def test_disconnect_not_connected(self, collector):
        """Test disconnecting when not connected."""
        result = collector.disconnect("192.168.1.1", 4403)
        assert result is False

    def test_disconnect_all_empty(self, collector):
        """Test disconnecting all when none connected."""
        collector.disconnect_all()  # Should not raise


class TestRunStop:
    """Tests for run/stop functionality."""

    def test_stop(self, collector):
        """Test stopping the collector."""
        collector._running = True
        collector.stop()
        assert collector._running is False

    def test_stop_multiple_times(self, collector):
        """Test stopping multiple times doesn't raise."""
        collector.stop()
        collector.stop()
        collector.stop()
