#!/bin/bash
# Working systemd service for NixOS containers
# Uses --volatile=yes to skip OS tree validation

CONTAINER_NAME="${1:-postgres}"
SYSTEM_PATH="/home/nandi/code/infra/result-${CONTAINER_NAME}"
SERVICE_FILE="/etc/systemd/system/nixos-${CONTAINER_NAME}.service"

cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=NixOS Container: ${CONTAINER_NAME}
After=network-online.target
Wants=network-online.target

[Service]
Type=simple

# Use volatile overlay to skip OS tree validation
ExecStart=/usr/bin/systemd-nspawn \\
  --quiet \\
  --machine=${CONTAINER_NAME} \\
  --volatile=yes \\
  --directory=/ \\
  --bind=/nix/store:/nix/store \\
  --bind=${SYSTEM_PATH}:/run/current-system \\
  --property=DeviceAllow=/dev/null rw \\
  /run/current-system/init

# Can't cleanup volatile easily, but it's in /var/tmp
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
echo "  sudo machinectl status ${CONTAINER_NAME}"
echo ""
echo "Note: Using --volatile=yes to bypass OS tree validation"
