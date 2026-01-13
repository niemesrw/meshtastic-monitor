# CLAUDE.md

This file provides guidance for Claude when working with the Meshtastic Monitor codebase.

## Project Overview

Meshtastic Monitor is a Python application for real-time monitoring and historical analysis of Meshtastic mesh networks. It connects to gateway nodes via TCP, collects network data (nodes, positions, messages, telemetry), stores data in SQLite, and provides both CLI and Web UI interfaces.

## Common Commands

### Testing
```bash
# Run all tests with coverage
pytest

# Run tests with verbose output
pytest -v

# Run specific test file
pytest tests/test_cli.py
```

### Code Quality
```bash
# Format code (100 char line length, Python 3.9+)
black mesh_monitor/

# Lint
ruff check mesh_monitor/
```

### Installation
```bash
# Install dependencies
pip install -r requirements.txt

# Install in development mode
pip install -e .

# Install with dev dependencies
pip install -e ".[dev]"
```

### Running the Application
```bash
# Start monitoring with web UI
mesh-monitor start --host <gateway-ip> --web

# View historical data (web UI only)
mesh-monitor web

# List nodes, view messages, export data
mesh-monitor nodes
mesh-monitor messages
mesh-monitor export --format json
```

## Project Structure

```
mesh_monitor/           # Core application package
├── cli.py             # Click CLI commands
├── collector.py       # Meshtastic event collector (TCP connections, pub/sub)
└── db.py              # SQLite database layer

web/                   # Flask web application
├── app.py             # Flask routes and API
└── templates/         # Jinja2 HTML templates

tests/                 # Test suite (pytest)
```

## Key Technologies

- **Python 3.9+**
- **meshtastic** - Official SDK for mesh network communication
- **click** - CLI framework
- **flask** - Web framework
- **SQLite** - Data persistence
- **pytest** - Testing framework
- **black/ruff** - Code formatting and linting

## Architecture Patterns

- **Pub/Sub Event System**: Uses meshtastic's pub/sub for handling mesh network events
- **SQLite Connection Pooling**: Thread-safe database access
- **Multi-threaded**: Web UI runs in daemon thread alongside collector
- **Click Decorators**: Hierarchical CLI command structure

## Data Models

- **Nodes**: ID, names, hardware model, firmware, MAC, timestamps
- **Positions**: Latitude, longitude, altitude, location source
- **DeviceMetrics**: Battery, voltage, channel utilization, airtime TX, uptime
- **Messages**: Sender, recipient, channel, text, timestamp
- **Gateways**: Connection details and activity timestamps
