#!/usr/bin/env python3
"""Seed the database with realistic mock data for screenshots/demos."""

import random
from datetime import datetime, timedelta
from pathlib import Path
import sys

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from mesh_monitor.db import Database


# Realistic node data
MOCK_NODES = [
    {
        "node_id": "!435a7b70",
        "node_num": 1130003312,
        "long_name": "Base Station Alpha",
        "short_name": "BSA",
        "hw_model": "LILYGO_TBEAM_S3_CORE",
        "firmware_version": "2.7.15.567b8ea",
        "lat": 39.1148,
        "lon": -84.5124,
        "alt": 284,
    },
    {
        "node_id": "!a3f82c91",
        "node_num": 2751536273,
        "long_name": "Mobile Unit 1",
        "short_name": "MU1",
        "hw_model": "HELTEC_V3",
        "firmware_version": "2.7.14.abc123",
        "lat": 39.1032,
        "lon": -84.5089,
        "alt": 256,
    },
    {
        "node_id": "!b7c43d52",
        "node_num": 3083501906,
        "long_name": "Hilltop Relay",
        "short_name": "HTR",
        "hw_model": "RAK_WISBLOCK",
        "firmware_version": "2.7.15.567b8ea",
        "lat": 39.1285,
        "lon": -84.4892,
        "alt": 412,
    },
    {
        "node_id": "!c9d54e63",
        "node_num": 3385180771,
        "long_name": "Downtown Node",
        "short_name": "DT1",
        "hw_model": "LILYGO_TBEAM_S3_CORE",
        "firmware_version": "2.7.12.def456",
        "lat": 39.0998,
        "lon": -84.5167,
        "alt": 198,
    },
    {
        "node_id": "!d1e65f74",
        "node_num": 3521847156,
        "long_name": "River Watch",
        "short_name": "RVW",
        "hw_model": "HELTEC_V3",
        "firmware_version": "2.7.15.567b8ea",
        "lat": 39.0876,
        "lon": -84.5234,
        "alt": 145,
    },
    {
        "node_id": "!e2f76085",
        "node_num": 3808018565,
        "long_name": "Park Ranger",
        "short_name": "PRK",
        "hw_model": "RAK_WISBLOCK",
        "firmware_version": "2.7.14.abc123",
        "lat": 39.1156,
        "lon": -84.4756,
        "alt": 301,
    },
    {
        "node_id": "!f3087196",
        "node_num": 4077359510,
        "long_name": "Emergency Ops",
        "short_name": "EOP",
        "hw_model": "LILYGO_TBEAM_S3_CORE",
        "firmware_version": "2.7.15.567b8ea",
        "lat": 39.1089,
        "lon": -84.5301,
        "alt": 267,
    },
    {
        "node_id": "!041982a7",
        "node_num": 68682407,
        "long_name": "School Net",
        "short_name": "SCH",
        "hw_model": "HELTEC_V3",
        "firmware_version": "2.7.13.xyz789",
        "lat": 39.1234,
        "lon": -84.5012,
        "alt": 289,
    },
]

MOCK_MESSAGES = [
    ("!435a7b70", None, "Good morning mesh! Base station is online."),
    ("!a3f82c91", "!435a7b70", "Mobile 1 checking in, heading downtown."),
    ("!b7c43d52", None, "Hilltop relay seeing good traffic today."),
    ("!c9d54e63", "!a3f82c91", "Meet at the coffee shop?"),
    ("!a3f82c91", "!c9d54e63", "Sounds good, be there in 10."),
    ("!d1e65f74", None, "River levels looking normal."),
    ("!e2f76085", None, "Trail conditions: dry and clear."),
    ("!f3087196", None, "EOC test - all stations please respond."),
    ("!435a7b70", None, "Base Alpha responding to EOC test."),
    ("!b7c43d52", None, "Hilltop responding."),
    ("!041982a7", None, "School net online for afternoon session."),
    ("!a3f82c91", None, "Mobile 1 back at base."),
    ("!c9d54e63", None, "Anyone tried the new firmware yet?"),
    ("!435a7b70", "!c9d54e63", "Running 2.7.15, very stable so far."),
    ("!e2f76085", None, "Sunset hike group heading out, will relay."),
]


def seed_database(db_path: str = "mesh.db"):
    """Seed the database with mock data."""
    print(f"Seeding database: {db_path}")
    db = Database(db_path)

    now = datetime.now()

    # Add gateway
    print("Adding gateway...")
    db.upsert_gateway("192.168.10.190", 4403, "!435a7b70")

    # Add nodes with varying "last seen" times
    print("Adding nodes...")
    for i, node in enumerate(MOCK_NODES):
        # Vary last seen - some recent, some older
        minutes_ago = random.randint(1, 120) if i < 5 else random.randint(200, 1000)

        db.upsert_node(
            node_id=node["node_id"],
            node_num=node["node_num"],
            long_name=node["long_name"],
            short_name=node["short_name"],
            hw_model=node["hw_model"],
            firmware_version=node["firmware_version"],
        )

    # Add positions with some movement/history
    print("Adding positions...")
    for node in MOCK_NODES:
        # Add multiple position reports over the last 24 hours
        for hours_ago in range(0, 24, 2):
            # Add some random drift to positions
            lat = node["lat"] + random.uniform(-0.002, 0.002)
            lon = node["lon"] + random.uniform(-0.002, 0.002)
            alt = node["alt"] + random.randint(-10, 10)

            db.insert_position(
                node_id=node["node_id"],
                latitude=lat,
                longitude=lon,
                altitude=alt,
                location_source="LOC_INTERNAL",
                timestamp=now - timedelta(hours=hours_ago, minutes=random.randint(0, 30)),
            )

    # Add device metrics with realistic battery drain
    print("Adding device metrics...")
    for node in MOCK_NODES:
        base_battery = random.randint(60, 100)
        base_voltage = 3.7 + (base_battery / 100) * 0.5  # 3.7-4.2V range

        for hours_ago in range(0, 48, 1):
            # Simulate battery drain
            battery = max(20, base_battery - (hours_ago * 0.5) + random.randint(-2, 2))
            voltage = 3.7 + (battery / 100) * 0.5

            db.insert_device_metrics(
                node_id=node["node_id"],
                battery_level=int(battery),
                voltage=round(voltage, 3),
                channel_utilization=round(random.uniform(5, 25), 2),
                air_util_tx=round(random.uniform(1, 5), 2),
                uptime_seconds=hours_ago * 3600 + random.randint(0, 3600),
                timestamp=now - timedelta(hours=hours_ago),
            )

    # Add messages spread over the last few hours
    print("Adding messages...")
    for i, (from_node, to_node, text) in enumerate(MOCK_MESSAGES):
        minutes_ago = i * 15 + random.randint(0, 10)
        db.insert_message(
            from_node=from_node,
            to_node=to_node,
            text=text,
            channel=0,
            port_num="TEXT_MESSAGE_APP",
            gateway_id=1,
            timestamp=now - timedelta(minutes=minutes_ago),
        )

    # Print stats
    stats = db.get_stats()
    print("\nDatabase seeded successfully!")
    print(f"  Nodes: {stats['total_nodes']}")
    print(f"  Positions: {stats['total_positions']}")
    print(f"  Metrics: {stats['total_metrics']}")
    print(f"  Messages: {stats['total_messages']}")
    print(f"  Gateways: {stats['total_gateways']}")

    print(f"\nTo view the UI, run:")
    print(f"  uv run mesh-monitor web --db {db_path}")
    print(f"  Then open http://localhost:8080")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Seed database with mock data")
    parser.add_argument("--db", default="demo.db", help="Database path (default: demo.db)")
    args = parser.parse_args()

    seed_database(args.db)
