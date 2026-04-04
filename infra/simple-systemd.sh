#!/usr/bin/env bash
# Simple systemd units that don't use bind mounts

set -e

cat > /tmp/nixos-container-postgres.service <<'EOF'
[Unit]
Description=NixOS Container: PostgreSQL
After=network.target nixos-container-bridge.service
Requires=nixos-container-bridge.service

[Service]
Type=notify
Environment="PATH=/nix/var/nix/profiles/default/bin:/usr/bin:/bin"
ExecStartPre=-/bin/rm -rf /var/lib/nixos-containers/postgres
ExecStartPre=/bin/mkdir -p /var/lib/nixos-containers/postgres/nix/store
ExecStartPre=/nix/var/nix/profiles/default/bin/nix copy --to /var/lib/nixos-containers/postgres?include-srcs=false /home/nandi/code/infra/result-postgres
ExecStart=/usr/bin/systemd-nspawn \
  --quiet \
  --machine=postgres \
  --directory=/var/lib/nixos-containers/postgres \
  /home/nandi/code/infra/result-postgres/init
ExecStop=/bin/machinectl poweroff postgres
KillMode=mixed
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

sudo cp /tmp/nixos-container-postgres.service /etc/systemd/system/
sudo systemctl daemon-reload

echo "Service installed. Start with:"
echo "  sudo systemctl start nixos-container-postgres"
