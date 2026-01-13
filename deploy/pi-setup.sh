#!/bin/bash
# Raspberry Pi Setup Script for Meshtastic Monitor
# This script installs and configures the Meshtastic Monitor collector and sync services.
#
# Usage: sudo ./pi-setup.sh [--with-sync]
#
# Options:
#   --with-sync   Also configure the sync service (requires sync.env configuration)

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Installation paths
INSTALL_DIR="/opt/meshtastic-monitor"
DATA_DIR="/var/lib/meshtastic-monitor"
CONFIG_DIR="/etc/meshtastic-monitor"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Parse arguments
WITH_SYNC=false
for arg in "$@"; do
    case $arg in
        --with-sync)
            WITH_SYNC=true
            shift
            ;;
    esac
done

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Meshtastic Monitor - Raspberry Pi Setup${NC}"
echo -e "${GREEN}========================================${NC}"
echo

# Check if running as root
if [[ $EUID -ne 0 ]]; then
   echo -e "${RED}Error: This script must be run as root (sudo)${NC}"
   exit 1
fi

# Detect architecture
ARCH=$(uname -m)
echo -e "Detected architecture: ${YELLOW}${ARCH}${NC}"

# Update system
echo -e "\n${GREEN}[1/7] Updating system packages...${NC}"
apt-get update
apt-get upgrade -y

# Install dependencies
echo -e "\n${GREEN}[2/7] Installing dependencies...${NC}"
apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    git \
    curl

# Install uv (fast Python package manager)
echo -e "\n${GREEN}[3/7] Installing uv package manager...${NC}"
if ! command -v uv &> /dev/null; then
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi

# Create meshtastic user
echo -e "\n${GREEN}[4/7] Creating meshtastic user...${NC}"
if ! id "meshtastic" &>/dev/null; then
    useradd --system --home-dir /opt/meshtastic-monitor --shell /usr/sbin/nologin meshtastic
    echo "Created user: meshtastic"
else
    echo "User meshtastic already exists"
fi

# Create directories
echo -e "\n${GREEN}[5/7] Creating directories...${NC}"
mkdir -p "$INSTALL_DIR"
mkdir -p "$DATA_DIR"
mkdir -p "$CONFIG_DIR"
chown meshtastic:meshtastic "$DATA_DIR"
chmod 750 "$DATA_DIR"

# Install meshtastic-monitor
echo -e "\n${GREEN}[6/7] Installing meshtastic-monitor...${NC}"

# Check if we're running from the source directory
if [[ -f "$SCRIPT_DIR/../pyproject.toml" ]]; then
    echo "Installing from local source..."
    cp -r "$SCRIPT_DIR/.." "$INSTALL_DIR/"
else
    echo "Cloning from GitHub..."
    git clone https://github.com/blanxlait/meshtastic-monitor.git "$INSTALL_DIR"
fi

cd "$INSTALL_DIR"

# Create virtual environment and install
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -e .

chown -R meshtastic:meshtastic "$INSTALL_DIR"

# Install systemd services
echo -e "\n${GREEN}[7/7] Installing systemd services...${NC}"

# Copy service files
cp "$INSTALL_DIR/deploy/meshtastic-collector.service" /etc/systemd/system/
cp "$INSTALL_DIR/deploy/meshtastic-sync.service" /etc/systemd/system/

# Copy example configs if not exist
if [[ ! -f "$CONFIG_DIR/collector.env" ]]; then
    cp "$INSTALL_DIR/deploy/collector.env.example" "$CONFIG_DIR/collector.env"
    echo -e "${YELLOW}Created $CONFIG_DIR/collector.env - please edit with your settings${NC}"
fi

if [[ ! -f "$CONFIG_DIR/sync.env" ]]; then
    cp "$INSTALL_DIR/deploy/sync.env.example" "$CONFIG_DIR/sync.env"
    echo -e "${YELLOW}Created $CONFIG_DIR/sync.env - please edit with your settings${NC}"
fi

chmod 600 "$CONFIG_DIR"/*.env
chown meshtastic:meshtastic "$CONFIG_DIR"/*.env

# Reload systemd
systemctl daemon-reload

# Enable collector service
systemctl enable meshtastic-collector.service

if [[ "$WITH_SYNC" == true ]]; then
    systemctl enable meshtastic-sync.service
    echo "Sync service enabled"
fi

echo
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Installation Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo
echo -e "Next steps:"
echo -e "  1. Edit ${YELLOW}$CONFIG_DIR/collector.env${NC}"
echo -e "     - Set MESHTASTIC_HOST to your device IP"
echo
if [[ "$WITH_SYNC" == true ]]; then
    echo -e "  2. Edit ${YELLOW}$CONFIG_DIR/sync.env${NC}"
    echo -e "     - Set MESHTASTIC_SYNC_API_URL"
    echo -e "     - Set MESHTASTIC_SYNC_API_KEY"
    echo
fi
echo -e "  3. Start the collector:"
echo -e "     ${YELLOW}sudo systemctl start meshtastic-collector${NC}"
echo
echo -e "  4. Check status:"
echo -e "     ${YELLOW}sudo systemctl status meshtastic-collector${NC}"
echo -e "     ${YELLOW}sudo journalctl -u meshtastic-collector -f${NC}"
echo
if [[ "$WITH_SYNC" == true ]]; then
    echo -e "  5. Start sync service:"
    echo -e "     ${YELLOW}sudo systemctl start meshtastic-sync${NC}"
    echo
fi
echo -e "Database location: ${YELLOW}$DATA_DIR/mesh.db${NC}"
echo
