-- PostgreSQL schema for Meshtastic Monitor central database
-- This schema is used on the Synology NAS to aggregate data from all collectors.

-- Collectors table - tracks all remote collectors
CREATE TABLE IF NOT EXISTS collectors (
    collector_id TEXT PRIMARY KEY,
    first_seen TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_seen TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    record_count INTEGER DEFAULT 0,
    name TEXT,
    location TEXT
);

CREATE INDEX IF NOT EXISTS idx_collectors_last_seen ON collectors(last_seen);

-- Gateways table - direct connection points (per collector)
CREATE TABLE IF NOT EXISTS gateways (
    id SERIAL PRIMARY KEY,
    host TEXT NOT NULL,
    port INTEGER DEFAULT 4403,
    node_id TEXT,
    first_seen TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_seen TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    collector_id TEXT NOT NULL,
    synced_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(host, port, collector_id)
);

CREATE INDEX IF NOT EXISTS idx_gateways_collector ON gateways(collector_id);
CREATE INDEX IF NOT EXISTS idx_gateways_last_seen ON gateways(last_seen);

-- Nodes table - all discovered mesh nodes
CREATE TABLE IF NOT EXISTS nodes (
    node_id TEXT PRIMARY KEY,
    node_num INTEGER,
    long_name TEXT,
    short_name TEXT,
    hw_model TEXT,
    firmware_version TEXT,
    mac_addr TEXT,
    first_seen TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_seen TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    collector_id TEXT,
    synced_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_nodes_last_seen ON nodes(last_seen);
CREATE INDEX IF NOT EXISTS idx_nodes_collector ON nodes(collector_id);

-- Positions table - GPS position history
CREATE TABLE IF NOT EXISTS positions (
    id SERIAL PRIMARY KEY,
    node_id TEXT NOT NULL REFERENCES nodes(node_id) ON DELETE CASCADE,
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    altitude INTEGER,
    location_source TEXT,
    collector_id TEXT,
    synced_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    -- Unique constraint to prevent duplicates from multiple collectors
    UNIQUE(node_id, timestamp, collector_id)
);

CREATE INDEX IF NOT EXISTS idx_positions_node_id ON positions(node_id);
CREATE INDEX IF NOT EXISTS idx_positions_timestamp ON positions(timestamp);
CREATE INDEX IF NOT EXISTS idx_positions_collector ON positions(collector_id);

-- Device metrics table - telemetry history
CREATE TABLE IF NOT EXISTS device_metrics (
    id SERIAL PRIMARY KEY,
    node_id TEXT NOT NULL REFERENCES nodes(node_id) ON DELETE CASCADE,
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    battery_level INTEGER,
    voltage DOUBLE PRECISION,
    channel_utilization DOUBLE PRECISION,
    air_util_tx DOUBLE PRECISION,
    uptime_seconds INTEGER,
    collector_id TEXT,
    synced_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    -- Unique constraint to prevent duplicates
    UNIQUE(node_id, timestamp, collector_id)
);

CREATE INDEX IF NOT EXISTS idx_device_metrics_node_id ON device_metrics(node_id);
CREATE INDEX IF NOT EXISTS idx_device_metrics_timestamp ON device_metrics(timestamp);
CREATE INDEX IF NOT EXISTS idx_device_metrics_collector ON device_metrics(collector_id);

-- Messages table - text messages
CREATE TABLE IF NOT EXISTS messages (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    from_node TEXT,
    to_node TEXT,
    channel INTEGER,
    text TEXT,
    port_num TEXT,
    collector_id TEXT,
    synced_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    -- Unique constraint based on content hash
    UNIQUE(timestamp, from_node, to_node, collector_id)
);

CREATE INDEX IF NOT EXISTS idx_messages_timestamp ON messages(timestamp);
CREATE INDEX IF NOT EXISTS idx_messages_from_node ON messages(from_node);
CREATE INDEX IF NOT EXISTS idx_messages_collector ON messages(collector_id);

-- Useful views

-- View: Latest position for each node
CREATE OR REPLACE VIEW latest_positions AS
SELECT DISTINCT ON (node_id)
    p.id, p.node_id, p.timestamp, p.latitude, p.longitude, p.altitude,
    p.location_source, p.collector_id, n.long_name, n.short_name
FROM positions p
JOIN nodes n ON p.node_id = n.node_id
ORDER BY p.node_id, p.timestamp DESC;

-- View: Latest metrics for each node
CREATE OR REPLACE VIEW latest_metrics AS
SELECT DISTINCT ON (node_id)
    m.id, m.node_id, m.timestamp, m.battery_level, m.voltage,
    m.channel_utilization, m.air_util_tx, m.uptime_seconds,
    m.collector_id, n.long_name, n.short_name
FROM device_metrics m
JOIN nodes n ON m.node_id = n.node_id
ORDER BY m.node_id, m.timestamp DESC;

-- View: Active nodes (seen in last hour)
CREATE OR REPLACE VIEW active_nodes AS
SELECT *
FROM nodes
WHERE last_seen > NOW() - INTERVAL '1 hour';

-- View: Collector health
CREATE OR REPLACE VIEW collector_health AS
SELECT
    c.collector_id,
    c.name,
    c.location,
    c.last_seen,
    c.record_count,
    CASE
        WHEN c.last_seen > NOW() - INTERVAL '10 minutes' THEN 'healthy'
        WHEN c.last_seen > NOW() - INTERVAL '1 hour' THEN 'warning'
        ELSE 'offline'
    END AS status,
    (SELECT COUNT(*) FROM nodes WHERE collector_id = c.collector_id) AS node_count,
    (SELECT COUNT(*) FROM positions WHERE collector_id = c.collector_id) AS position_count,
    (SELECT COUNT(*) FROM device_metrics WHERE collector_id = c.collector_id) AS metric_count,
    (SELECT COUNT(*) FROM messages WHERE collector_id = c.collector_id) AS message_count
FROM collectors c
ORDER BY c.last_seen DESC;
