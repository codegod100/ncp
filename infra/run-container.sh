#!/bin/bash
# Minimal working NixOS container with systemd-nspawn
# This copies the closure into the container instead of bind mounting

CONTAINER=$1
SYSTEM_PATH=$2

if [ -z "$CONTAINER" ] || [ -z "$SYSTEM_PATH" ]; then
  echo "Usage: $0 <container-name> <system-path>"
  echo "Example: $0 postgres /home/nandi/code/infra/result-postgres"
  exit 1
fi

CTR_DIR="/var/lib/nixos-containers/$CONTAINER"

echo "Setting up $CONTAINER..."

# Clean up
rm -rf "$CTR_DIR"
mkdir -p "$CTR_DIR"

# Copy the essential files
cp -r "$SYSTEM_PATH" "$CTR_DIR/nixos-system"

# Create required directories
mkdir -p "$CTR_DIR"/{proc,sys,dev,run,tmp,etc,var}
mkdir -p "$CTR_DIR/nix/store"

# Create minimal os-release
cat > "$CTR_DIR/etc/os-release" <<EOF
NAME="NixOS"
ID=nixos
VERSION_ID="24.11"
EOF

touch "$CTR_DIR/etc/machine-id"

# Run the init directly
exec systemd-nspawn \
  --machine="$CONTAINER" \
  --directory="$CTR_DIR" \
  --bind=/nix/store:/nix/store \
  --as-pid2 \
  "$CTR_DIR/nixos-system/init"
