#!/bin/bash
# Working systemd service for NixOS containers
# Uses correct systemd path from NixOS system

CONTAINER_NAME="${1:-postgres}"
SYSTEM_PATH="/home/nandi/code/infra/result-${CONTAINER_NAME}"
SERVICE_FILE="/etc/systemd/system/nixos-${CONTAINER_NAME}.service"

cat > "/tmp/setup-nixos-${CONTAINER_NAME}.sh" <<'SETUP'
#!/bin/bash
CONTAINER="$1"
DIR="/var/lib/nixos-containers/$CONTAINER"

# Clean
rm -rf "$DIR"
mkdir -p "$DIR"

# Create skeleton OS tree (required for systemd-nspawn)
mkdir -p "$DIR/usr/lib/systemd"
mkdir -p "$DIR/bin"
mkdir -p "$DIR/sbin"
mkdir -p "$DIR/etc"
mkdir -p "$DIR/proc"
mkdir -p "$DIR/sys"
mkdir -p "$DIR/dev"
mkdir -p "$DIR/run"
mkdir -p "$DIR/tmp"
mkdir -p "$DIR/root"
mkdir -p "$DIR/var"
mkdir -p "$DIR/nix/store"

# Create os-release
cat > "$DIR/etc/os-release" <<'EOF'
NAME="NixOS"
ID=nixos
PRETTY_NAME="NixOS Container"
VERSION_ID="24.11"
HOME_URL="https://nixos.org"
EOF

touch "$DIR/etc/machine-id"
SETUP

chmod +x "/tmp/setup-nixos-${CONTAINER_NAME}.sh"

cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=NixOS Container: ${CONTAINER_NAME}
After=network-online.target
Wants=network-online.target

[Service]
Type=simple

# Setup skeleton tree
ExecStartPre=/tmp/setup-nixos-${CONTAINER_NAME}.sh ${CONTAINER_NAME}

# Run with bind mounts - use correct systemd path
ExecStart=/usr/bin/systemd-nspawn \\
  --quiet \\
  --machine=${CONTAINER_NAME} \\
  --directory=/var/lib/nixos-containers/${CONTAINER_NAME} \\
  --bind=/nix/store:/nix/store \\
  --bind=${SYSTEM_PATH}:/run/current-system \\
  --bind=${SYSTEM_PATH}/systemd/lib/systemd/systemd:/usr/lib/systemd/systemd \\
  --boot

# Cleanup
ExecStopPost=-/bin/rm -rf /var/lib/nixos-containers/${CONTAINER_NAME}

Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

echo "Created $SERVICE_FILE"
echo ""
echo "To use:"
echo "  sudo systemctl daemon-reload"
echo "  sudo systemctl start nixos-${CONTAINER_NAME}"
echo "  sudo systemctl status nixos-${CONTAINER_NAME}"
