#!/bin/bash
# Working systemd service for NixOS containers

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
WorkingDirectory=/var/lib/nixos-containers

# Clean and setup container root
ExecStartPre=-/bin/rm -rf /var/lib/nixos-containers/${CONTAINER_NAME}
ExecStartPre=/bin/mkdir -p /var/lib/nixos-containers/${CONTAINER_NAME}

# Copy the system closure
ExecStartPre=/bin/cp -r ${SYSTEM_PATH} /var/lib/nixos-containers/${CONTAINER_NAME}/system

# Create required directories
ExecStartPre=/bin/mkdir -p /var/lib/nixos-containers/${CONTAINER_NAME}/proc
ExecStartPre=/bin/mkdir -p /var/lib/nixos-containers/${CONTAINER_NAME}/sys
ExecStartPre=/bin/mkdir -p /var/lib/nixos-containers/${CONTAINER_NAME}/dev
ExecStartPre=/bin/mkdir -p /var/lib/nixos-containers/${CONTAINER_NAME}/run
ExecStartPre=/bin/mkdir -p /var/lib/nixos-containers/${CONTAINER_NAME}/tmp
ExecStartPre=/bin/mkdir -p /var/lib/nixos-containers/${CONTAINER_NAME}/etc
ExecStartPre=/bin/mkdir -p /var/lib/nixos-containers/${CONTAINER_NAME}/var

# Create minimal environment
ExecStartPre=/bin/sh -c 'echo "NAME=\\"NixOS\\"" > /var/lib/nixos-containers/${CONTAINER_NAME}/etc/os-release'
ExecStartPre=/bin/touch /var/lib/nixos-containers/${CONTAINER_NAME}/etc/machine-id

# Run the container - use bash to run activation then systemd
ExecStart=/usr/bin/systemd-nspawn \\
  --quiet \\
  --machine=${CONTAINER_NAME} \\
  --directory=/var/lib/nixos-containers/${CONTAINER_NAME} \\
  --bind=/nix/store:/nix/store \\
  --as-pid2 \\
  /var/lib/nixos-containers/${CONTAINER_NAME}/system/sw/bin/bash -c \\
    '/var/lib/nixos-containers/${CONTAINER_NAME}/system/activate && exec /var/lib/nixos-containers/${CONTAINER_NAME}/system/sw/bin/systemd --system'

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
echo "  sudo machinectl status ${CONTAINER_NAME}"
