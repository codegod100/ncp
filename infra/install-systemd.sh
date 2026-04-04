#!/usr/bin/env bash
# Generate and install systemd units for NixOS containers
# This allows running NixOS containers on any Linux with systemd

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONTAINER_NETWORK="10.100.0.0/16"
BRIDGE_NAME="ctrs"

# Container IPs
declare -A CTR_IPS=(
  [api-server]="10.100.1.10"
  [worker]="10.100.2.10"
  [postgres]="10.100.3.10"
)

declare -A CTR_PORTS=(
  [api-server]="8080:3000"
  [worker]="8081:3000"
  [postgres]="5432:5432"
)

cat <<'EOF'
=== NixOS Container Systemd Generator ===

This creates systemd units that run NixOS containers using systemd-nspawn
with proper cgroup v2 support.

EOF

# Check if running as root
if [ "$EUID" -ne 0 ]; then
  echo "This script needs to run commands as root. Some operations may fail."
fi

# Check deps
echo "Checking dependencies..."
if ! command -v systemd-nspawn &> /dev/null; then
  echo "❌ systemd-nspawn not found. Install: sudo apt-get install systemd-container"
  exit 1
fi

if ! command -v ip &> /dev/null; then
  echo "❌ ip command not found. Install: sudo apt-get install iproute2"
  exit 1
fi

echo "✓ Dependencies OK"
echo ""

# Create systemd unit directory
mkdir -p /etc/systemd/system/nixos-container@.service.d

# Create the template service unit
cat > /etc/systemd/system/nixos-container@.service <<'SYSTEMD'
[Unit]
Description=NixOS Container %i
Documentation=man:systemd-nspawn(1)
After=network.target nixos-container-bridge.service
Requires=nixos-container-bridge.service
Wants=network.target

[Service]
Type=notify
ExecStartPre=/usr/local/bin/nixos-container-setup %i
ExecStart=/usr/bin/systemd-nspawn \
  --quiet \
  --machine=%i \
  --directory=/var/lib/nixos-containers/%i \
  --boot \
  --network-bridge=ctrs \
  --bind=/nix/store:/nix/store:ro \
  --property=MemoryMax=512M \
  --property=CPUQuota=50%
ExecStop=/bin/machinectl poweroff %i
ExecStopPost=/usr/bin/rm -rf /var/lib/nixos-containers/%i
KillMode=mixed
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
SYSTEMD

# Create the setup script
mkdir -p /usr/local/bin
cat > /usr/local/bin/nixos-container-setup <<'SETUP'
#!/bin/bash
# Setup container root directory

CONTAINER=$1
CONTAINER_DIR="/var/lib/nixos-containers/$CONTAINER"
NIX_STORE="/nix/store"

# Get the system path from a symlink or argument
if [ -L "/home/nandi/code/infra/result-$CONTAINER" ]; then
  SYSTEM_PATH=$(readlink -f "/home/nandi/code/infra/result-$CONTAINER")
else
  echo "Container $CONTAINER not built. Build with:"
  echo "  nix build .#nixosConfigurations.container-$CONTAINER.config.system.build.toplevel"
  exit 1
fi

# Clean and create directory - systemd-nspawn will handle the bind mount
rm -rf "$CONTAINER_DIR"
mkdir -p "$CONTAINER_DIR"/{bin,sbin,etc,lib,lib64,proc,sys,dev,run,tmp,root,nix,var,usr}
mkdir -p "$CONTAINER_DIR/nix/store"
mkdir -p "$CONTAINER_DIR/usr/lib/systemd"

# Create os-release
cat > "$CONTAINER_DIR/etc/os-release" <<EOF
NAME="NixOS"
ID=nixos
PRETTY_NAME="NixOS Container $CONTAINER"
VERSION_ID="24.11"
HOME_URL="https://nixos.org"
EOF

touch "$CONTAINER_DIR/etc/machine-id"
touch "$CONTAINER_DIR/etc/resolv.conf"

# Create symlinks pointing to where the system will be bind-mounted
ln -sf "/run/current-system/init" "$CONTAINER_DIR/sbin/init"
ln -sf "/run/current-system/init" "$CONTAINER_DIR/init"
ln -sf "/run/current-system/sw/bin/systemd" "$CONTAINER_DIR/usr/lib/systemd/systemd"

mkdir -p "$CONTAINER_DIR/run/current-system"

echo "Container $CONTAINER prepared at $CONTAINER_DIR"
echo "System will be mounted at: /run/current-system"
echo "System path: $SYSTEM_PATH"
SETUP
chmod +x /usr/local/bin/nixos-container-setup

# Create bridge setup service
cat > /etc/systemd/system/nixos-container-bridge.service <<'BRIDGE'
[Unit]
Description=NixOS Container Network Bridge
Before=nixos-container@.service
Wants=network.target

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/local/bin/nixos-container-network-setup start
ExecStop=/usr/local/bin/nixos-container-network-setup stop

[Install]
WantedBy=multi-user.target
BRIDGE

# Create network setup script
cat > /usr/local/bin/nixos-container-network-setup <<'NETWORK'
#!/bin/bash
ACTION=$1
BRIDGE="ctrs"
NETWORK="10.100.0.0/16"

case "$ACTION" in
  start)
    # Create bridge if not exists
    if ! ip link show "$BRIDGE" 2>/dev/null; then
      ip link add "$BRIDGE" type bridge
      ip addr add "10.100.0.1/16" dev "$BRIDGE"
      ip link set "$BRIDGE" up
      echo 1 > /proc/sys/net/ipv4/ip_forward
      iptables -t nat -A POSTROUTING -s "$NETWORK" ! -d "$NETWORK" -j MASQUERADE 2>/dev/null || true
      iptables -A FORWARD -i "$BRIDGE" -o "$BRIDGE" -j ACCEPT 2>/dev/null || true
      echo "Bridge $BRIDGE created"
    fi
    ;;
  stop)
    ip link del "$BRIDGE" 2>/dev/null || true
    iptables -t nat -D POSTROUTING -s "$NETWORK" ! -d "$NETWORK" -j MASQUERADE 2>/dev/null || true
    echo "Bridge $BRIDGE removed"
    ;;
esac
NETWORK
chmod +x /usr/local/bin/nixos-container-network-setup

# Create individual service instances
cat > /etc/systemd/system/nixos-container-api-server.service <<'API'
[Unit]
Description=NixOS Container: API Server
Documentation=man:systemd-nspawn(1)
After=network.target nixos-container-bridge.service
Requires=nixos-container-bridge.service

[Service]
Type=notify
Environment="SYSTEMD_NSPAWN_UNIFIED_HIERARCHY=1"
Environment="SYSTEMD_NSPAWN_USE_CGNS=1"
ExecStartPre=/usr/local/bin/nixos-container-setup api-server
ExecStart=/usr/bin/systemd-nspawn \
  --quiet \
  --machine=api-server \
  --directory=/var/lib/nixos-containers/api-server \
  --network-bridge=ctrs \
  --bind=/nix/store:/nix/store \
  --bind=/home/nandi/code/infra/result-api-server:/run/current-system \
  --property=MemoryMax=512M \
  /run/current-system/init
ExecStop=/bin/machinectl poweroff api-server
KillMode=mixed
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
API

cat > /etc/systemd/system/nixos-container-worker.service <<'WORKER'
[Unit]
Description=NixOS Container: Worker
After=network.target nixos-container-bridge.service nixos-container-postgres.service
Requires=nixos-container-bridge.service
Wants=nixos-container-postgres.service

[Service]
Type=notify
Environment="SYSTEMD_NSPAWN_UNIFIED_HIERARCHY=1"
ExecStartPre=/usr/local/bin/nixos-container-setup worker
ExecStart=/usr/bin/systemd-nspawn \
  --quiet \
  --machine=worker \
  --directory=/var/lib/nixos-containers/worker \
  --network-bridge=ctrs \
  --bind=/nix/store:/nix/store \
  --bind=/home/nandi/code/infra/result-worker:/run/current-system \
  --property=MemoryMax=512M \
  /run/current-system/init
ExecStop=/bin/machinectl poweroff worker
KillMode=mixed
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
WORKER

cat > /etc/systemd/system/nixos-container-postgres.service <<'POSTGRES'
[Unit]
Description=NixOS Container: PostgreSQL
After=network.target nixos-container-bridge.service
Requires=nixos-container-bridge.service

[Service]
Type=notify
Environment="SYSTEMD_NSPAWN_UNIFIED_HIERARCHY=1"
ExecStartPre=/usr/local/bin/nixos-container-setup postgres
ExecStart=/usr/bin/systemd-nspawn \
  --quiet \
  --machine=postgres \
  --directory=/var/lib/nixos-containers/postgres \
  --network-bridge=ctrs \
  --bind=/nix/store:/nix/store \
  --bind=/home/nandi/code/infra/result-postgres:/run/current-system \
  --property=MemoryMax=512M \
  /run/current-system/init
ExecStop=/bin/machinectl poweroff postgres
KillMode=mixed
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
POSTGRES

echo "Systemd units created!"
echo ""
echo "To enable and start:"
echo "  sudo systemctl daemon-reload"
echo "  sudo systemctl enable --now nixos-container-postgres"
echo "  sudo systemctl enable --now nixos-container-worker"
echo "  sudo systemctl enable --now nixos-container-api-server"
echo ""
echo "To check status:"
echo "  sudo systemctl status nixos-container-api-server"
echo "  sudo machinectl list"
echo ""
echo "To test networking:"
echo "  sudo machinectl shell api-server -- curl http://10.100.2.10:3000"
echo ""
