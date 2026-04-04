#!/bin/bash
# Check what's wrong with the service

echo "=== Service Status ==="
sudo systemctl status nixos-postgres --no-pager

echo ""
echo "=== Recent Logs ==="
sudo journalctl -xu nixos-postgres --no-pager -n 30

echo ""
echo "=== Container Directory ==="
ls -la /var/lib/nixos-containers/postgres/ 2>/dev/null || echo "Directory not found"

echo ""
echo "=== System Link ==="
ls -la /var/lib/nixos-containers/postgres/system 2>/dev/null || echo "System not copied"

echo ""
echo "=== Manual Test ==="
echo "Try running manually:"
echo "  sudo systemd-nspawn --machine=test --directory=/var/lib/nixos-containers/postgres --as-pid2 /bin/bash"
