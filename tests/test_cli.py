"""Tests for the CLI module."""

import json
import tempfile
from datetime import datetime
from pathlib import Path

import pytest
from click.testing import CliRunner

from mesh_monitor.cli import cli, _format_datetime, _format_uptime, _node_to_dict
from mesh_monitor.db import Database, Node


@pytest.fixture
def runner():
    """Create a CLI test runner."""
    return CliRunner()


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
    db.insert_message(
        from_node="!node2",
        text="Broadcast message",
        channel=0,
    )

    # Add gateway
    db.upsert_gateway("192.168.1.100", 4403, "!gateway1")

    return db_path


class TestNodesCommand:
    """Tests for the nodes command."""

    def test_nodes_empty(self, runner, db_path):
        """Test nodes command with empty database."""
        result = runner.invoke(cli, ["--db", db_path, "nodes"])
        assert result.exit_code == 0
        assert "No nodes found" in result.output

    def test_nodes_with_data(self, runner, populated_db):
        """Test nodes command with data."""
        result = runner.invoke(cli, ["--db", populated_db, "nodes"])
        assert result.exit_code == 0
        assert "!node1" in result.output
        assert "Test Node 1" in result.output
        assert "!node2" in result.output
        assert "Test Node 2" in result.output
        assert "Total: 2 nodes" in result.output

    def test_nodes_with_limit(self, runner, populated_db):
        """Test nodes command with limit."""
        result = runner.invoke(cli, ["--db", populated_db, "nodes", "--limit", "1"])
        assert result.exit_code == 0
        assert "Total: 1 nodes" in result.output


class TestNodeCommand:
    """Tests for the node detail command."""

    def test_node_not_found(self, runner, db_path):
        """Test node command when node doesn't exist."""
        result = runner.invoke(cli, ["--db", db_path, "node", "!nonexistent"])
        assert result.exit_code == 1
        assert "not found" in result.output

    def test_node_detail(self, runner, populated_db):
        """Test node detail command."""
        result = runner.invoke(cli, ["--db", populated_db, "node", "!node1"])
        assert result.exit_code == 0
        assert "!node1" in result.output
        assert "Test Node 1" in result.output
        assert "TN1" in result.output
        assert "TBEAM" in result.output
        assert "2.0.0" in result.output

    def test_node_shows_metrics(self, runner, populated_db):
        """Test that node detail shows latest metrics."""
        result = runner.invoke(cli, ["--db", populated_db, "node", "!node1"])
        assert result.exit_code == 0
        assert "85%" in result.output  # Battery
        assert "4.1" in result.output  # Voltage

    def test_node_shows_position(self, runner, populated_db):
        """Test that node detail shows latest position."""
        result = runner.invoke(cli, ["--db", populated_db, "node", "!node1"])
        assert result.exit_code == 0
        assert "39.114875" in result.output
        assert "-84.344302" in result.output


class TestPositionsCommand:
    """Tests for the positions command."""

    def test_positions_empty(self, runner, db_path):
        """Test positions command with no data."""
        result = runner.invoke(cli, ["--db", db_path, "positions", "!nonexistent"])
        assert result.exit_code == 0
        assert "No positions found" in result.output

    def test_positions_with_data(self, runner, populated_db):
        """Test positions command with data."""
        result = runner.invoke(cli, ["--db", populated_db, "positions", "!node1"])
        assert result.exit_code == 0
        assert "39.114875" in result.output
        assert "-84.344302" in result.output
        assert "284m" in result.output


class TestMetricsCommand:
    """Tests for the metrics command."""

    def test_metrics_empty(self, runner, db_path):
        """Test metrics command with no data."""
        result = runner.invoke(cli, ["--db", db_path, "metrics", "!nonexistent"])
        assert result.exit_code == 0
        assert "No metrics found" in result.output

    def test_metrics_with_data(self, runner, populated_db):
        """Test metrics command with data."""
        result = runner.invoke(cli, ["--db", populated_db, "metrics", "!node1"])
        assert result.exit_code == 0
        assert "85%" in result.output
        assert "4.10V" in result.output
        assert "12.5%" in result.output


class TestMessagesCommand:
    """Tests for the messages command."""

    def test_messages_empty(self, runner, db_path):
        """Test messages command with no data."""
        result = runner.invoke(cli, ["--db", db_path, "messages"])
        assert result.exit_code == 0
        assert "No messages found" in result.output

    def test_messages_with_data(self, runner, populated_db):
        """Test messages command with data."""
        result = runner.invoke(cli, ["--db", populated_db, "messages"])
        assert result.exit_code == 0
        assert "Hello!" in result.output
        assert "Broadcast message" in result.output
        assert "Total: 2 messages" in result.output

    def test_messages_filter_from(self, runner, populated_db):
        """Test messages command with from filter."""
        result = runner.invoke(
            cli, ["--db", populated_db, "messages", "--from", "!node1"]
        )
        assert result.exit_code == 0
        assert "Hello!" in result.output
        assert "Total: 1 messages" in result.output

    def test_messages_filter_to(self, runner, populated_db):
        """Test messages command with to filter."""
        result = runner.invoke(
            cli, ["--db", populated_db, "messages", "--to", "!node2"]
        )
        assert result.exit_code == 0
        assert "Hello!" in result.output


class TestStatusCommand:
    """Tests for the status command."""

    def test_status_empty(self, runner, db_path):
        """Test status command with empty database."""
        result = runner.invoke(cli, ["--db", db_path, "status"])
        assert result.exit_code == 0
        assert "Total Nodes:     0" in result.output

    def test_status_with_data(self, runner, populated_db):
        """Test status command with data."""
        result = runner.invoke(cli, ["--db", populated_db, "status"])
        assert result.exit_code == 0
        assert "Total Nodes:     2" in result.output
        assert "Total Positions: 1" in result.output
        assert "Total Metrics:   1" in result.output
        assert "Total Messages:  2" in result.output
        assert "192.168.1.100:4403" in result.output


class TestExportCommand:
    """Tests for the export command."""

    def test_export_json(self, runner, populated_db):
        """Test export command with JSON format."""
        result = runner.invoke(cli, ["--db", populated_db, "export", "--format", "json"])
        assert result.exit_code == 0

        data = json.loads(result.output)
        assert "nodes" in data
        assert "stats" in data
        assert len(data["nodes"]) == 2

    def test_export_csv(self, runner, populated_db):
        """Test export command with CSV format."""
        result = runner.invoke(cli, ["--db", populated_db, "export", "--format", "csv"])
        assert result.exit_code == 0
        assert "node_id,long_name" in result.output
        assert "!node1,Test Node 1" in result.output

    def test_export_to_file(self, runner, populated_db):
        """Test export command writing to file."""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            output_path = f.name

        try:
            result = runner.invoke(
                cli,
                ["--db", populated_db, "export", "--format", "json", "-o", output_path],
            )
            assert result.exit_code == 0
            assert f"Exported to {output_path}" in result.output

            with open(output_path) as f:
                data = json.load(f)
            assert len(data["nodes"]) == 2
        finally:
            Path(output_path).unlink(missing_ok=True)


class TestHelperFunctions:
    """Tests for CLI helper functions."""

    def test_format_datetime_none(self):
        """Test formatting None datetime."""
        assert _format_datetime(None) == "N/A"

    def test_format_datetime_string(self):
        """Test formatting string datetime."""
        assert _format_datetime("2024-01-15") == "2024-01-15"

    def test_format_datetime(self):
        """Test formatting datetime object."""
        dt = datetime(2024, 1, 15, 12, 30, 45)
        assert _format_datetime(dt) == "2024-01-15 12:30:45"

    def test_format_uptime_none(self):
        """Test formatting None uptime."""
        assert _format_uptime(None) == "N/A"

    def test_format_uptime_seconds(self):
        """Test formatting small uptime."""
        assert _format_uptime(65) == "1m 5s"

    def test_format_uptime_hours(self):
        """Test formatting hours uptime."""
        assert _format_uptime(3665) == "1h 1m"

    def test_format_uptime_days(self):
        """Test formatting days uptime."""
        assert _format_uptime(90061) == "1d 1h 1m"

    def test_node_to_dict(self):
        """Test converting Node to dict."""
        node = Node(
            node_id="!test",
            node_num=123,
            long_name="Test",
            short_name="T",
            hw_model="TBEAM",
            firmware_version="2.0",
            mac_addr="AA:BB:CC",
            first_seen=datetime(2024, 1, 1),
            last_seen=datetime(2024, 1, 15),
        )
        d = _node_to_dict(node)
        assert d["node_id"] == "!test"
        assert d["long_name"] == "Test"
        assert "2024-01-01" in d["first_seen"]


class TestCLIOptions:
    """Tests for CLI global options."""

    def test_default_db(self, runner):
        """Test default database path."""
        result = runner.invoke(cli, ["status"])
        assert result.exit_code == 0

    def test_custom_db(self, runner, db_path):
        """Test custom database path."""
        result = runner.invoke(cli, ["--db", db_path, "status"])
        assert result.exit_code == 0


class TestStartCommand:
    """Tests for the start command (limited - can't test actual connections)."""

    def test_start_no_host(self, runner, db_path):
        """Test start command without host."""
        result = runner.invoke(cli, ["--db", db_path, "start"])
        assert result.exit_code != 0
        assert "Missing option" in result.output or "required" in result.output.lower()
