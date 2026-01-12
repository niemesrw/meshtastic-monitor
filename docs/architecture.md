# Meshtastic Monitor - Architecture

## Overview

Meshtastic Monitor is a Python application that connects to Meshtastic nodes via the official Python SDK, collects mesh network data, stores it in SQLite for historical analysis, and provides both CLI and Web UI interfaces for data access and visualization.

## System Architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│                         Meshtastic Monitor                                │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌─────────────┐    ┌──────────────┐    ┌─────────────────┐             │
│  │   CLI       │───▶│  Collector   │───▶│    Database     │             │
│  │  (click)    │    │              │    │    (SQLite)     │             │
│  └─────────────┘    └──────────────┘    └─────────────────┘             │
│                            │                     ▲                       │
│                            ▼                     │                       │
│                     ┌──────────────┐             │                       │
│                     │  Meshtastic  │             │                       │
│                     │    SDK       │             │                       │
│                     └──────────────┘             │                       │
│                            │                     │                       │
│  ┌─────────────┐           │           ┌────────┴────────┐              │
│  │   Web UI    │───────────┼──────────▶│   REST API      │              │
│  │  (Flask)    │           │           │   (Flask)       │              │
│  └─────────────┘           │           └─────────────────┘              │
│        │                   │                                             │
│        ▼                   │                                             │
│  ┌─────────────┐           │                                             │
│  │  Frontend   │           │                                             │
│  │ Leaflet.js  │           │                                             │
│  │ Chart.js    │           │                                             │
│  └─────────────┘           │                                             │
│                            │                                             │
└────────────────────────────┼─────────────────────────────────────────────┘
                             │
                             ▼
              ┌──────────────────────────────┐
              │     Meshtastic Mesh Network   │
              │  ┌────────┐    ┌────────┐    │
              │  │ Node 1 │◀──▶│ Node 2 │    │
              │  │(gateway)│    │        │    │
              │  └────────┘    └────────┘    │
              │       ▲            ▲         │
              │       │            │         │
              │       ▼            ▼         │
              │  ┌────────┐    ┌────────┐    │
              │  │ Node 3 │◀──▶│ Node 4 │    │
              │  └────────┘    └────────┘    │
              └──────────────────────────────┘
```

## Core Components

### 1. CLI Layer (`cli.py`)

The command-line interface built with `click`. Provides two modes of operation:

**Daemon Mode:**
- `start` command launches continuous monitoring
- Connects to one or more gateway nodes
- Runs until interrupted (Ctrl+C)

**Query Mode:**
- `nodes` - List all discovered mesh nodes
- `node <id>` - Show details for a specific node
- `positions <id>` - View position history
- `metrics <id>` - View device metrics history
- `messages` - View message history
- `status` - Show connection and database stats
- `export` - Export data to JSON/CSV

### 2. Collector (`collector.py`)

Manages connections to Meshtastic nodes and handles incoming data.

**Responsibilities:**
- Establish TCP connections to gateway nodes via `meshtastic.tcp_interface.TCPInterface`
- Subscribe to Meshtastic pub/sub events
- Parse incoming packets and route to database layer
- Handle reconnection on connection loss
- Support multiple simultaneous gateway connections

**Event Subscriptions:**
| Event | Purpose |
|-------|---------|
| `meshtastic.connection.established` | Track gateway connections |
| `meshtastic.connection.lost` | Handle disconnections, trigger reconnect |
| `meshtastic.receive.position` | Store GPS position updates |
| `meshtastic.receive.text` | Store text messages |
| `meshtastic.receive.telemetry` | Store device/environment metrics |
| `meshtastic.receive.user` | Update node user info |
| `meshtastic.node.updated` | Catch node database changes |

### 3. Database Layer (`db.py`)

SQLite-based persistence layer for all mesh data.

**Responsibilities:**
- Schema creation and migration
- CRUD operations for all entity types
- Query functions with filtering and pagination
- Connection pooling for concurrent access

### 4. Models (`models.py`)

Data classes representing mesh entities (optional, for type safety).

### 5. Web UI (`web/`)

A Flask-based web interface for visualizing mesh network data.

**Backend (`web/app.py`):**
- Flask application serving REST API and static files
- Runs alongside or separately from the collector
- Endpoints for nodes, positions, metrics, messages

**Frontend (`web/static/`, `web/templates/`):**
- Single-page application with multiple views
- Leaflet.js for interactive maps
- Chart.js for metrics visualization
- Auto-refresh for live data updates

#### Web UI Views

**Dashboard (`/`)**
- Network overview stats (total nodes, active nodes, messages today)
- Recent activity feed
- Quick health indicators (nodes with low battery, offline nodes)

**Map View (`/map`)**
- Interactive map showing all node positions
- Node markers with popups showing details
- Position history trails (optional)
- Clickable markers linking to node details
- Layer controls for filtering

**Nodes List (`/nodes`)**
- Sortable/filterable table of all nodes
- Columns: Name, ID, Hardware, Battery, Last Heard, Status
- Click through to node detail page
- Status indicators (online/offline based on last_heard)

**Node Detail (`/nodes/<id>`)**
- Full node information
- Position history map (single node)
- Battery/voltage chart over time
- Channel utilization chart
- Recent messages to/from this node

**Messages (`/messages`)**
- Searchable message log
- Filter by sender, recipient, channel, date range
- Real-time updates for new messages

#### REST API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/nodes` | GET | List all nodes |
| `/api/nodes/<id>` | GET | Get single node details |
| `/api/nodes/<id>/positions` | GET | Get position history for node |
| `/api/nodes/<id>/metrics` | GET | Get metrics history for node |
| `/api/positions` | GET | Get all recent positions |
| `/api/messages` | GET | Get messages (with filters) |
| `/api/stats` | GET | Get network statistics |
| `/api/gateways` | GET | Get gateway connection status |

#### Frontend Libraries

| Library | Version | Purpose |
|---------|---------|---------|
| Leaflet.js | 1.9.x | Interactive maps |
| Chart.js | 4.x | Metrics charts |
| Bootstrap | 5.x | UI framework, responsive layout |
| (Optional) Socket.IO | 4.x | Real-time updates via WebSocket |

## Database Schema

### Entity Relationship Diagram

```
┌─────────────┐       ┌─────────────────┐
│  gateways   │       │     nodes       │
├─────────────┤       ├─────────────────┤
│ id (PK)     │       │ node_id (PK)    │
│ host        │       │ node_num        │
│ port        │       │ long_name       │
│ node_id     │──────▶│ short_name      │
│ first_seen  │       │ hw_model        │
│ last_seen   │       │ firmware_version│
└─────────────┘       │ mac_addr        │
      │               │ first_seen      │
      │               │ last_seen       │
      │               └─────────────────┘
      │                    │    │    │
      │                    │    │    │
      ▼                    ▼    │    ▼
┌─────────────┐    ┌──────────┐ │ ┌────────────────┐
│  messages   │    │positions │ │ │ device_metrics │
├─────────────┤    ├──────────┤ │ ├────────────────┤
│ id (PK)     │    │ id (PK)  │ │ │ id (PK)        │
│ timestamp   │    │ node_id  │◀┘ │ node_id        │◀┘
│ from_node   │◀───│ timestamp│   │ timestamp      │
│ to_node     │    │ latitude │   │ battery_level  │
│ channel     │    │ longitude│   │ voltage        │
│ text        │    │ altitude │   │ channel_util   │
│ port_num    │    │ loc_src  │   │ air_util_tx    │
│ gateway_id  │    └──────────┘   │ uptime_seconds │
└─────────────┘                   └────────────────┘
```

### Table Definitions

#### `gateways`
Tracks the Meshtastic nodes we connect to directly as data collection points.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key |
| host | TEXT | IP address or hostname |
| port | INTEGER | TCP port (default 4403) |
| node_id | TEXT | Meshtastic node ID (e.g., `!435a7b70`) |
| first_seen | TIMESTAMP | When gateway was first connected |
| last_seen | TIMESTAMP | Last successful connection |

#### `nodes`
All mesh nodes discovered through any gateway.

| Column | Type | Description |
|--------|------|-------------|
| node_id | TEXT | Primary key, e.g., `!435a7b70` |
| node_num | INTEGER | Numeric node identifier |
| long_name | TEXT | User-configured long name |
| short_name | TEXT | 4-character short name |
| hw_model | TEXT | Hardware model (e.g., `LILYGO_TBEAM_S3_CORE`) |
| firmware_version | TEXT | Firmware version string |
| mac_addr | TEXT | MAC address |
| first_seen | TIMESTAMP | When node was first discovered |
| last_seen | TIMESTAMP | Last packet received from node |

#### `positions`
GPS position history for each node.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key |
| node_id | TEXT | Foreign key to nodes |
| timestamp | TIMESTAMP | When position was received |
| latitude | REAL | Latitude in degrees |
| longitude | REAL | Longitude in degrees |
| altitude | INTEGER | Altitude in meters |
| location_source | TEXT | Source (e.g., `LOC_INTERNAL`, `LOC_MANUAL`) |

#### `device_metrics`
Device telemetry history.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key |
| node_id | TEXT | Foreign key to nodes |
| timestamp | TIMESTAMP | When metrics were received |
| battery_level | INTEGER | Battery percentage (0-100) |
| voltage | REAL | Battery voltage |
| channel_utilization | REAL | Channel utilization percentage |
| air_util_tx | REAL | Airtime utilization TX percentage |
| uptime_seconds | INTEGER | Device uptime in seconds |

#### `messages`
Text messages sent over the mesh.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key |
| timestamp | TIMESTAMP | When message was received |
| from_node | TEXT | Sender node ID |
| to_node | TEXT | Recipient node ID (or broadcast) |
| channel | INTEGER | Channel index |
| text | TEXT | Message content |
| port_num | TEXT | Port number/type |
| gateway_id | INTEGER | Which gateway received this message |

## Data Flow

### Collection Flow

```
1. User runs: mesh-monitor start --host 192.168.10.190

2. Collector creates TCPInterface connection to gateway

3. On connection established:
   - Record gateway in database
   - Initial node database sync from gateway
   - Subscribe to all relevant events

4. For each received packet:
   ┌─────────────────┐
   │ Packet Received │
   └────────┬────────┘
            │
            ▼
   ┌─────────────────┐
   │ Identify Type   │
   └────────┬────────┘
            │
   ┌────────┴────────┬─────────────┬──────────────┐
   ▼                 ▼             ▼              ▼
┌──────┐      ┌──────────┐  ┌───────────┐  ┌─────────┐
│ User │      │ Position │  │ Telemetry │  │  Text   │
│ Info │      │          │  │           │  │ Message │
└──┬───┘      └────┬─────┘  └─────┬─────┘  └────┬────┘
   │               │              │              │
   ▼               ▼              ▼              ▼
┌──────┐      ┌──────────┐  ┌───────────┐  ┌─────────┐
│Update│      │  Insert  │  │  Insert   │  │ Insert  │
│nodes │      │ positions│  │  metrics  │  │messages │
└──────┘      └──────────┘  └───────────┘  └─────────┘
```

### Query Flow

```
1. User runs: mesh-monitor nodes

2. CLI parses command and options

3. Database layer queries SQLite:
   SELECT * FROM nodes ORDER BY last_seen DESC

4. Results formatted and displayed to user
```

## Connection Management

### Single Gateway Mode
Connect to one Meshtastic node that has visibility into the mesh.

```python
collector = MeshCollector(db_path="mesh.db")
collector.connect("192.168.10.190")
collector.run()  # Blocks until interrupted
```

### Multiple Gateway Mode
Connect to multiple nodes for broader mesh visibility.

```python
collector = MeshCollector(db_path="mesh.db")
collector.connect("192.168.10.190")
collector.connect("192.168.10.191")
collector.run()  # Manages all connections
```

### Reconnection Strategy
- On connection loss, attempt reconnect with exponential backoff
- Start at 1 second, max 60 seconds between attempts
- Log reconnection attempts and failures

## Technology Stack

| Component | Technology | Rationale |
|-----------|------------|-----------|
| Language | Python 3.9+ | Meshtastic SDK is Python |
| CLI Framework | click | Clean, composable commands |
| Database | SQLite | Zero setup, portable, sufficient for this use case |
| Meshtastic | meshtastic (pip) | Official SDK with pub/sub events |
| Web Framework | Flask | Lightweight, simple, good for REST APIs |
| Maps | Leaflet.js | Open source, easy to use, OpenStreetMap tiles |
| Charts | Chart.js | Simple, responsive charts |
| CSS Framework | Bootstrap 5 | Responsive layout, clean components |

## File Structure

```
meshtastic-monitor/
├── mesh_monitor/
│   ├── __init__.py
│   ├── __main__.py           # Entry point
│   ├── cli.py                # Click CLI commands
│   ├── db.py                 # SQLite database layer
│   ├── collector.py          # Meshtastic event collection
│   └── models.py             # Data classes
├── web/
│   ├── __init__.py
│   ├── app.py                # Flask application
│   ├── api.py                # REST API routes
│   ├── templates/
│   │   ├── base.html         # Base template with nav
│   │   ├── dashboard.html    # Dashboard view
│   │   ├── map.html          # Map view
│   │   ├── nodes.html        # Nodes list
│   │   ├── node_detail.html  # Single node view
│   │   └── messages.html     # Messages view
│   └── static/
│       ├── css/
│       │   └── style.css     # Custom styles
│       └── js/
│           ├── map.js        # Map initialization and markers
│           ├── charts.js     # Chart configurations
│           └── app.js        # Common JS utilities
├── docs/
│   └── architecture.md
├── requirements.txt
├── setup.py
└── README.md
```

## Running the Application

### Collector + Web UI Together (Recommended)

```bash
# Start both collector and web server
mesh-monitor start --host 192.168.10.190 --web

# Access web UI at http://localhost:8080
```

### Separate Processes

```bash
# Terminal 1: Run collector
mesh-monitor start --host 192.168.10.190

# Terminal 2: Run web UI only (reads from same database)
mesh-monitor web --port 8080
```

### Web UI Only (View Historical Data)

```bash
# Just browse existing data without live collection
mesh-monitor web --db mesh.db --port 8080
```

## Future Considerations

Potential enhancements (not in initial scope):
- Environment metrics table (temperature, humidity, pressure)
- Air quality metrics table
- MQTT bridge support
- Data retention policies / automatic cleanup
- Real-time WebSocket updates (Socket.IO)
- Export to GPX/KML for position data
- Dark mode theme
- Mobile-responsive PWA
