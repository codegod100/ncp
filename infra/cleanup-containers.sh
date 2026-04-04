#!/bin/bash
# Clean up stuck containers and mounts

echo "Stopping containers..."
sudo systemctl stop nixos-container-postgres nixos-container-worker nixos-container-api-server 2>/dev/null || true

echo "Killing any running nspawn processes..."
sudo killall systemd-nspawn 2>/dev/null || true

echo "Unmounting bind mounts..."
for mnt in $(mount | grep nixos-containers | awk '{print $3}'); do
  sudo umount -f "$mnt" 2>/dev/null || sudo umount -l "$mnt" 2>/dev/null || echo "Could not unmount $mnt"
done

echo "Removing container directories..."
sudo rm -rf /var/lib/nixos-containers/* 2>/dev/null || true

echo "Cleaning up systemd machines..."
sudo machinectl terminate postgres 2>/dev/null || true
sudo machinectl terminate worker 2>/dev/null || true
sudo machinectl terminate api-server 2>/dev/null || true

echo "Done!"
