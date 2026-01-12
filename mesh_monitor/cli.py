"""Command-line interface for Meshtastic Monitor."""

import logging
import sys
import threading
from datetime import datetime
from typing import Optional

import click

from mesh_monitor.db import Database
from mesh_monitor.collector import MeshCollector

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@click.group()
@click.option(
    "--db",
    default="mesh.db",
    help="Path to SQLite database file.",
    type=click.Path(),
)
@click.pass_context
def cli(ctx, db):
    """Meshtastic Monitor - Monitor and analyze mesh networks."""
    ctx.ensure_object(dict)
    ctx.obj["db_path"] = db


@cli.command()
@click.option(
    "--host",
    multiple=True,
    required=True,
    help="Gateway node IP address (can specify multiple).",
)
@click.option(
    "--port",
    default=4403,
    help="Meshtastic TCP port.",
)
@click.option(
    "--web/--no-web",
    default=False,
    help="Start web UI alongside collector.",
)
@click.option(
    "--web-port",
    default=8080,
    help="Web UI port.",
)
@click.option(
    "--debug/--no-debug",
    default=False,
    help="Enable debug logging.",
)
@click.pass_context
def start(ctx, host, port, web, web_port, debug):
    """Start monitoring gateway node(s).

    Examples:

        mesh-monitor start --host 192.168.1.100

        mesh-monitor start --host 192.168.1.100 --host 192.168.1.101

        mesh-monitor start --host 192.168.1.100 --web
    """
    if debug:
        logging.getLogger().setLevel(logging.DEBUG)

    db_path = ctx.obj["db_path"]
    db = Database(db_path)
    collector = MeshCollector(db)

    click.echo(f"Using database: {db_path}")

    # Connect to all gateways
    for h in host:
        click.echo(f"Connecting to {h}:{port}...")
        if not collector.connect(h, port):
            click.echo(f"Failed to connect to {h}:{port}", err=True)

    if not collector.interfaces:
        click.echo("No gateways connected. Exiting.", err=True)
        sys.exit(1)

    # Start web UI if requested
    web_thread = None
    if web:
        try:
            from web.app import create_app

            app = create_app(db_path)

            def run_web():
                app.run(host="0.0.0.0", port=web_port, debug=False, use_reloader=False)

            web_thread = threading.Thread(target=run_web, daemon=True)
            web_thread.start()
            click.echo(f"Web UI available at http://localhost:{web_port}")
        except ImportError as e:
            click.echo(f"Warning: Could not start web UI: {e}", err=True)

    click.echo("Monitoring started. Press Ctrl+C to stop.")

    try:
        collector.run(blocking=True)
    except KeyboardInterrupt:
        click.echo("\nStopping...")
    finally:
        collector.stop()
        click.echo("Monitoring stopped.")


@cli.command()
@click.option(
    "--port",
    default=8080,
    help="Web UI port.",
)
@click.option(
    "--debug/--no-debug",
    default=False,
    help="Enable debug mode.",
)
@click.pass_context
def web(ctx, port, debug):
    """Start web UI server only (view historical data)."""
    db_path = ctx.obj["db_path"]

    try:
        from web.app import create_app

        app = create_app(db_path)
        click.echo(f"Using database: {db_path}")
        click.echo(f"Web UI available at http://localhost:{port}")
        app.run(host="0.0.0.0", port=port, debug=debug)
    except ImportError as e:
        click.echo(f"Error: Could not start web UI: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.option(
    "--limit",
    default=50,
    help="Maximum number of nodes to display.",
)
@click.pass_context
def nodes(ctx, limit):
    """List all discovered mesh nodes."""
    db_path = ctx.obj["db_path"]
    db = Database(db_path)

    all_nodes = db.get_all_nodes(limit=limit)

    if not all_nodes:
        click.echo("No nodes found.")
        return

    click.echo(f"\n{'Node ID':<15} {'Name':<25} {'Hardware':<20} {'Last Seen':<20}")
    click.echo("-" * 80)

    for node in all_nodes:
        last_seen = _format_datetime(node.last_seen)
        click.echo(
            f"{node.node_id:<15} "
            f"{(node.long_name or 'Unknown'):<25} "
            f"{(node.hw_model or 'Unknown'):<20} "
            f"{last_seen:<20}"
        )

    click.echo(f"\nTotal: {len(all_nodes)} nodes")


@cli.command()
@click.argument("node_id")
@click.pass_context
def node(ctx, node_id):
    """Show details for a specific node."""
    db_path = ctx.obj["db_path"]
    db = Database(db_path)

    n = db.get_node(node_id)
    if not n:
        click.echo(f"Node {node_id} not found.", err=True)
        sys.exit(1)

    click.echo(f"\nNode: {n.node_id}")
    click.echo("-" * 40)
    click.echo(f"  Long Name:    {n.long_name or 'N/A'}")
    click.echo(f"  Short Name:   {n.short_name or 'N/A'}")
    click.echo(f"  Node Number:  {n.node_num or 'N/A'}")
    click.echo(f"  Hardware:     {n.hw_model or 'N/A'}")
    click.echo(f"  Firmware:     {n.firmware_version or 'N/A'}")
    click.echo(f"  MAC Address:  {n.mac_addr or 'N/A'}")
    click.echo(f"  First Seen:   {_format_datetime(n.first_seen)}")
    click.echo(f"  Last Seen:    {_format_datetime(n.last_seen)}")

    # Show latest metrics
    metrics = db.get_latest_device_metrics(node_id)
    if metrics:
        click.echo("\nLatest Metrics:")
        click.echo(f"  Battery:      {metrics.battery_level}%")
        click.echo(f"  Voltage:      {metrics.voltage}V")
        click.echo(f"  Channel Util: {metrics.channel_utilization}%")
        click.echo(f"  Air Util TX:  {metrics.air_util_tx}%")
        click.echo(f"  Uptime:       {_format_uptime(metrics.uptime_seconds)}")

    # Show latest position
    positions = db.get_positions(node_id, limit=1)
    if positions:
        pos = positions[0]
        click.echo("\nLatest Position:")
        click.echo(f"  Latitude:     {pos.latitude}")
        click.echo(f"  Longitude:    {pos.longitude}")
        click.echo(f"  Altitude:     {pos.altitude}m")
        click.echo(f"  Time:         {_format_datetime(pos.timestamp)}")


@cli.command()
@click.argument("node_id")
@click.option(
    "--limit",
    default=20,
    help="Maximum number of positions to display.",
)
@click.pass_context
def positions(ctx, node_id, limit):
    """Show position history for a node."""
    db_path = ctx.obj["db_path"]
    db = Database(db_path)

    pos_list = db.get_positions(node_id, limit=limit)

    if not pos_list:
        click.echo(f"No positions found for {node_id}.")
        return

    click.echo(f"\nPositions for {node_id}:")
    click.echo(f"{'Timestamp':<22} {'Latitude':<12} {'Longitude':<13} {'Altitude':<10}")
    click.echo("-" * 60)

    for pos in pos_list:
        ts = _format_datetime(pos.timestamp)
        lat = f"{pos.latitude:.6f}" if pos.latitude else "N/A"
        lon = f"{pos.longitude:.6f}" if pos.longitude else "N/A"
        alt = f"{pos.altitude}m" if pos.altitude else "N/A"
        click.echo(f"{ts:<22} {lat:<12} {lon:<13} {alt:<10}")


@cli.command()
@click.argument("node_id")
@click.option(
    "--limit",
    default=20,
    help="Maximum number of metrics to display.",
)
@click.pass_context
def metrics(ctx, node_id, limit):
    """Show device metrics history for a node."""
    db_path = ctx.obj["db_path"]
    db = Database(db_path)

    metrics_list = db.get_device_metrics(node_id, limit=limit)

    if not metrics_list:
        click.echo(f"No metrics found for {node_id}.")
        return

    click.echo(f"\nDevice Metrics for {node_id}:")
    click.echo(f"{'Timestamp':<22} {'Battery':<10} {'Voltage':<10} {'Ch Util':<10} {'Uptime':<15}")
    click.echo("-" * 70)

    for m in metrics_list:
        ts = _format_datetime(m.timestamp)
        batt = f"{m.battery_level}%" if m.battery_level is not None else "N/A"
        volt = f"{m.voltage:.2f}V" if m.voltage else "N/A"
        ch_util = f"{m.channel_utilization:.1f}%" if m.channel_utilization else "N/A"
        uptime = _format_uptime(m.uptime_seconds) if m.uptime_seconds else "N/A"
        click.echo(f"{ts:<22} {batt:<10} {volt:<10} {ch_util:<10} {uptime:<15}")


@cli.command()
@click.option(
    "--from",
    "from_node",
    help="Filter by sender node ID.",
)
@click.option(
    "--to",
    "to_node",
    help="Filter by recipient node ID.",
)
@click.option(
    "--limit",
    default=50,
    help="Maximum number of messages to display.",
)
@click.pass_context
def messages(ctx, from_node, to_node, limit):
    """Show message history."""
    db_path = ctx.obj["db_path"]
    db = Database(db_path)

    msg_list = db.get_messages(from_node=from_node, to_node=to_node, limit=limit)

    if not msg_list:
        click.echo("No messages found.")
        return

    click.echo(f"\n{'Timestamp':<22} {'From':<15} {'To':<15} {'Message':<40}")
    click.echo("-" * 95)

    for msg in msg_list:
        ts = _format_datetime(msg.timestamp)
        from_id = msg.from_node or "Unknown"
        to_id = msg.to_node or "Broadcast"
        text = (msg.text or "")[:40]
        click.echo(f"{ts:<22} {from_id:<15} {to_id:<15} {text:<40}")

    click.echo(f"\nTotal: {len(msg_list)} messages")


@cli.command()
@click.pass_context
def status(ctx):
    """Show connection and database statistics."""
    db_path = ctx.obj["db_path"]
    db = Database(db_path)

    stats = db.get_stats()
    gateways = db.get_all_gateways()

    click.echo("\nDatabase Statistics:")
    click.echo("-" * 30)
    click.echo(f"  Total Nodes:     {stats['total_nodes']}")
    click.echo(f"  Total Positions: {stats['total_positions']}")
    click.echo(f"  Total Metrics:   {stats['total_metrics']}")
    click.echo(f"  Total Messages:  {stats['total_messages']}")
    click.echo(f"  Total Gateways:  {stats['total_gateways']}")

    if gateways:
        click.echo("\nGateways:")
        click.echo("-" * 30)
        for gw in gateways:
            last_seen = _format_datetime(gw.last_seen)
            click.echo(f"  {gw.host}:{gw.port} - Last seen: {last_seen}")


@cli.command()
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["json", "csv"]),
    default="json",
    help="Output format.",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(),
    help="Output file path.",
)
@click.pass_context
def export(ctx, output_format, output):
    """Export collected data."""
    import json

    db_path = ctx.obj["db_path"]
    db = Database(db_path)

    data = {
        "nodes": [_node_to_dict(n) for n in db.get_all_nodes(limit=10000)],
        "stats": db.get_stats(),
        "exported_at": datetime.now().isoformat(),
    }

    if output_format == "json":
        result = json.dumps(data, indent=2, default=str)
    else:
        # CSV format - just nodes for now
        lines = ["node_id,long_name,short_name,hw_model,last_seen"]
        for n in data["nodes"]:
            lines.append(
                f"{n['node_id']},{n['long_name']},{n['short_name']},"
                f"{n['hw_model']},{n['last_seen']}"
            )
        result = "\n".join(lines)

    if output:
        with open(output, "w") as f:
            f.write(result)
        click.echo(f"Exported to {output}")
    else:
        click.echo(result)


# Helper functions


def _format_datetime(dt: Optional[datetime]) -> str:
    """Format a datetime for display."""
    if dt is None:
        return "N/A"
    if isinstance(dt, str):
        return dt
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _format_uptime(seconds: Optional[int]) -> str:
    """Format uptime seconds as human readable."""
    if seconds is None:
        return "N/A"

    days, remainder = divmod(seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, secs = divmod(remainder, 60)

    if days > 0:
        return f"{days}d {hours}h {minutes}m"
    elif hours > 0:
        return f"{hours}h {minutes}m"
    else:
        return f"{minutes}m {secs}s"


def _node_to_dict(node) -> dict:
    """Convert a Node dataclass to dict."""
    return {
        "node_id": node.node_id,
        "node_num": node.node_num,
        "long_name": node.long_name,
        "short_name": node.short_name,
        "hw_model": node.hw_model,
        "firmware_version": node.firmware_version,
        "mac_addr": node.mac_addr,
        "first_seen": str(node.first_seen) if node.first_seen else None,
        "last_seen": str(node.last_seen) if node.last_seen else None,
    }


if __name__ == "__main__":
    cli()
