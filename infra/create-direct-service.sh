#!/bin/bash
# Service without --boot, running init directly

CONTAINER_NAME="${1:-postgres}"
SYSTEM_PATH="/home/nandi/code/infra/result-${CONTAINER_NAME}"
SERVICE_FILE="/etc/systemd/system/nixos-${CONTAINER_NAME}.service"

cat > "/tmp/setup-nixos-${CONTAINER_NAME}.sh" <<'SETUP'
#!/bin/bash
CONTAINER="$1"
DIR="/var/lib/nixos-containers/$CONTAINER"

rm -rf "$DIR"
mkdir -p "$DIR"

# Create skeleton OS tree
mkdir -p "$DIR/usr/lib/systemd" "$DIR/bin" "$DIR/sbin" "$DIR/etc"
mkdir -p "$DIR/proc" "$DIR/sys" "$DIR/dev" "$DIR/run" "$DIR/tmp"
mkdir -p "$DIR/root" "$DIR/var" "$DIR/nix/store"

# Create os-release
cat > "$DIR/etc/os-release" <<'EOF'
NAME="NixOS"
ID=nixos
PRETTY_NAME="NixOS Container"
VERSION_ID="24.11"
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

# Run without --boot, execute init directly
# --bind=/sys/fs/cgroup passes host cgroup v2 to container
ExecStart=/usr/bin/systemd-nspawn \\
  --quiet \\
  --machine=${CONTAINER_NAME} \\
  --directory=/var/lib/nixos-containers/${CONTAINER_NAME} \\
  --bind=/nix/store:/nix/store \\
  --bind=${SYSTEM_PATH}:/run/current-system \\
  --bind=/sys/fs/cgroup:/sys/fs/cgroup \\
  --capability=all \\
  /run/current-system/init

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
