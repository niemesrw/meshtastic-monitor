"""Meshtastic data collector.

Connects to Meshtastic nodes and collects mesh network data.
"""

import logging
import threading
import time
from datetime import datetime
from typing import Callable, Optional

from pubsub import pub

from mesh_monitor.db import Database

logger = logging.getLogger(__name__)


class MeshCollector:
    """Collects data from Meshtastic mesh networks.

    Connects to one or more gateway nodes via TCP and subscribes to
    mesh network events, storing data in the database.
    """

    def __init__(self, db: Database):
        """Initialize the collector.

        Args:
            db: Database instance for storing collected data.
        """
        self.db = db
        self.interfaces: dict[str, "meshtastic.tcp_interface.TCPInterface"] = {}
        self.gateway_ids: dict[str, int] = {}
        self._running = False
        self._lock = threading.Lock()
        self._on_connection_callback: Optional[Callable[[str], None]] = None
        self._on_disconnect_callback: Optional[Callable[[str], None]] = None

        # Subscribe to meshtastic events
        self._subscribe_events()

    def _subscribe_events(self) -> None:
        """Subscribe to all relevant meshtastic pub/sub events."""
        pub.subscribe(self._on_receive, "meshtastic.receive")
        pub.subscribe(self._on_connection, "meshtastic.connection.established")
        pub.subscribe(self._on_disconnect, "meshtastic.connection.lost")
        pub.subscribe(self._on_node_updated, "meshtastic.node.updated")

    def _unsubscribe_events(self) -> None:
        """Unsubscribe from meshtastic events."""
        pub.unsubscribe(self._on_receive, "meshtastic.receive")
        pub.unsubscribe(self._on_connection, "meshtastic.connection.established")
        pub.unsubscribe(self._on_disconnect, "meshtastic.connection.lost")
        pub.unsubscribe(self._on_node_updated, "meshtastic.node.updated")

    def connect(self, host: str, port: int = 4403) -> bool:
        """Connect to a gateway node.

        Args:
            host: Gateway hostname or IP address.
            port: Gateway TCP port.

        Returns:
            True if connection initiated successfully.
        """
        key = f"{host}:{port}"
        if key in self.interfaces:
            logger.warning(f"Already connected to {key}")
            return False

        try:
            # Import here to allow testing without meshtastic installed
            from meshtastic.tcp_interface import TCPInterface

            logger.info(f"Connecting to {host}:{port}...")
            interface = TCPInterface(hostname=host, portNumber=port)

            with self._lock:
                self.interfaces[key] = interface
                # Record gateway in database
                gateway_id = self.db.upsert_gateway(host, port)
                self.gateway_ids[key] = gateway_id

            return True

        except Exception as e:
            logger.error(f"Failed to connect to {host}:{port}: {e}")
            return False

    def disconnect(self, host: str, port: int = 4403) -> bool:
        """Disconnect from a gateway node.

        Args:
            host: Gateway hostname or IP address.
            port: Gateway TCP port.

        Returns:
            True if disconnected successfully.
        """
        key = f"{host}:{port}"

        with self._lock:
            if key not in self.interfaces:
                return False

            try:
                self.interfaces[key].close()
            except Exception as e:
                logger.warning(f"Error closing interface {key}: {e}")

            del self.interfaces[key]
            if key in self.gateway_ids:
                del self.gateway_ids[key]

        logger.info(f"Disconnected from {key}")
        return True

    def disconnect_all(self) -> None:
        """Disconnect from all gateways."""
        with self._lock:
            keys = list(self.interfaces.keys())

        for key in keys:
            host, port = key.split(":")
            self.disconnect(host, int(port))

    def run(self, blocking: bool = True) -> None:
        """Run the collector.

        Args:
            blocking: If True, block until stop() is called.
        """
        self._running = True
        logger.info("Collector started")

        if blocking:
            try:
                while self._running:
                    time.sleep(0.5)
            except KeyboardInterrupt:
                logger.info("Interrupted, stopping...")
                self.stop()

    def stop(self) -> None:
        """Stop the collector and disconnect from all gateways."""
        self._running = False
        self.disconnect_all()
        self._unsubscribe_events()
        logger.info("Collector stopped")

    def set_on_connection_callback(self, callback: Callable[[str], None]) -> None:
        """Set callback for when a connection is established."""
        self._on_connection_callback = callback

    def set_on_disconnect_callback(self, callback: Callable[[str], None]) -> None:
        """Set callback for when a connection is lost."""
        self._on_disconnect_callback = callback

    # Event handlers

    def _on_connection(self, interface, topic=pub.AUTO_TOPIC) -> None:
        """Handle connection established event."""
        try:
            host = getattr(interface, "hostname", "unknown")
            port = getattr(interface, "portNumber", 4403)
            key = f"{host}:{port}"

            logger.info(f"Connected to {key}")

            # Get node ID from interface if available
            node_id = None
            if hasattr(interface, "myInfo") and interface.myInfo:
                node_num = interface.myInfo.my_node_num
                node_id = f"!{node_num:08x}"

                # Update gateway with node_id
                self.db.upsert_gateway(host, port, node_id)

            # Sync initial node database
            self._sync_node_db(interface)

            if self._on_connection_callback:
                self._on_connection_callback(key)

        except Exception as e:
            logger.error(f"Error in connection handler: {e}")

    def _on_disconnect(self, interface, topic=pub.AUTO_TOPIC) -> None:
        """Handle connection lost event."""
        try:
            host = getattr(interface, "hostname", "unknown")
            port = getattr(interface, "portNumber", 4403)
            key = f"{host}:{port}"

            logger.warning(f"Connection lost to {key}")

            if self._on_disconnect_callback:
                self._on_disconnect_callback(key)

        except Exception as e:
            logger.error(f"Error in disconnect handler: {e}")

    def _on_receive(self, packet, interface) -> None:
        """Handle received packet."""
        try:
            self._process_packet(packet, interface)
        except Exception as e:
            logger.error(f"Error processing packet: {e}")

    def _on_node_updated(self, node, interface) -> None:
        """Handle node database update."""
        try:
            self._process_node_info(node)
        except Exception as e:
            logger.error(f"Error processing node update: {e}")

    def _process_packet(self, packet: dict, interface) -> None:
        """Process a received packet.

        Args:
            packet: The packet data.
            interface: The interface that received the packet.
        """
        port_num = packet.get("decoded", {}).get("portnum", "")

        if port_num == "TEXT_MESSAGE_APP":
            self._handle_text_message(packet, interface)
        elif port_num == "POSITION_APP":
            self._handle_position(packet)
        elif port_num == "TELEMETRY_APP":
            self._handle_telemetry(packet)
        elif port_num == "NODEINFO_APP":
            self._handle_nodeinfo(packet)

    def _handle_text_message(self, packet: dict, interface) -> None:
        """Handle a text message packet."""
        decoded = packet.get("decoded", {})
        text = decoded.get("text", "")

        from_id = packet.get("fromId")
        to_id = packet.get("toId")
        channel = packet.get("channel", 0)

        # Get gateway ID
        host = getattr(interface, "hostname", "unknown")
        port = getattr(interface, "portNumber", 4403)
        key = f"{host}:{port}"
        gateway_id = self.gateway_ids.get(key)

        # Ensure nodes exist
        if from_id:
            self.db.upsert_node(node_id=from_id)
        if to_id and to_id != "^all":
            self.db.upsert_node(node_id=to_id)

        self.db.insert_message(
            from_node=from_id,
            to_node=to_id if to_id != "^all" else None,
            channel=channel,
            text=text,
            port_num="TEXT_MESSAGE_APP",
            gateway_id=gateway_id,
        )

        logger.debug(f"Message from {from_id}: {text[:50]}...")

    def _handle_position(self, packet: dict) -> None:
        """Handle a position packet."""
        decoded = packet.get("decoded", {})
        position = decoded.get("position", {})

        from_id = packet.get("fromId")
        if not from_id:
            return

        # Ensure node exists
        self.db.upsert_node(node_id=from_id)

        # Position coordinates are in integer format (multiply by 1e-7)
        latitude_i = position.get("latitudeI")
        longitude_i = position.get("longitudeI")

        latitude = latitude_i * 1e-7 if latitude_i else None
        longitude = longitude_i * 1e-7 if longitude_i else None
        altitude = position.get("altitude")
        location_source = position.get("locationSource", "UNKNOWN")

        # Get timestamp from position or use current time
        pos_time = position.get("time")
        timestamp = datetime.fromtimestamp(pos_time) if pos_time else datetime.now()

        self.db.insert_position(
            node_id=from_id,
            latitude=latitude,
            longitude=longitude,
            altitude=altitude,
            location_source=location_source,
            timestamp=timestamp,
        )

        logger.debug(f"Position from {from_id}: {latitude}, {longitude}")

    def _handle_telemetry(self, packet: dict) -> None:
        """Handle a telemetry packet."""
        decoded = packet.get("decoded", {})
        telemetry = decoded.get("telemetry", {})

        from_id = packet.get("fromId")
        if not from_id:
            return

        # Device metrics
        device_metrics = telemetry.get("deviceMetrics", {})
        if device_metrics:
            # Ensure node exists
            self.db.upsert_node(node_id=from_id)

            self.db.insert_device_metrics(
                node_id=from_id,
                battery_level=device_metrics.get("batteryLevel"),
                voltage=device_metrics.get("voltage"),
                channel_utilization=device_metrics.get("channelUtilization"),
                air_util_tx=device_metrics.get("airUtilTx"),
                uptime_seconds=device_metrics.get("uptimeSeconds"),
            )

            logger.debug(
                f"Telemetry from {from_id}: battery={device_metrics.get('batteryLevel')}%"
            )

    def _handle_nodeinfo(self, packet: dict) -> None:
        """Handle a nodeinfo packet."""
        decoded = packet.get("decoded", {})
        user = decoded.get("user", {})

        node_id = user.get("id")
        if not node_id:
            return

        self.db.upsert_node(
            node_id=node_id,
            long_name=user.get("longName"),
            short_name=user.get("shortName"),
            hw_model=user.get("hwModel"),
            mac_addr=user.get("macaddr"),
        )

        logger.debug(f"NodeInfo: {node_id} - {user.get('longName')}")

    def _process_node_info(self, node: dict) -> None:
        """Process node info from node database update."""
        user = node.get("user", {})
        node_id = user.get("id")
        if not node_id:
            return

        self.db.upsert_node(
            node_id=node_id,
            node_num=node.get("num"),
            long_name=user.get("longName"),
            short_name=user.get("shortName"),
            hw_model=user.get("hwModel"),
            mac_addr=user.get("macaddr"),
        )

        # Process position if available
        position = node.get("position", {})
        if position:
            latitude_i = position.get("latitudeI")
            longitude_i = position.get("longitudeI")

            if latitude_i and longitude_i:
                self.db.insert_position(
                    node_id=node_id,
                    latitude=latitude_i * 1e-7,
                    longitude=longitude_i * 1e-7,
                    altitude=position.get("altitude"),
                    location_source=position.get("locationSource", "UNKNOWN"),
                )

        # Process device metrics if available
        device_metrics = node.get("deviceMetrics", {})
        if device_metrics:
            self.db.insert_device_metrics(
                node_id=node_id,
                battery_level=device_metrics.get("batteryLevel"),
                voltage=device_metrics.get("voltage"),
                channel_utilization=device_metrics.get("channelUtilization"),
                air_util_tx=device_metrics.get("airUtilTx"),
                uptime_seconds=device_metrics.get("uptimeSeconds"),
            )

    def _sync_node_db(self, interface) -> None:
        """Sync the node database from an interface.

        Args:
            interface: The meshtastic interface to sync from.
        """
        try:
            if not hasattr(interface, "nodes") or not interface.nodes:
                return

            for node_id, node in interface.nodes.items():
                self._process_node_info(node)

            logger.info(f"Synced {len(interface.nodes)} nodes from gateway")

        except Exception as e:
            logger.error(f"Error syncing node database: {e}")
