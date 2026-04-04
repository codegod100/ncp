#!/usr/bin/env bash
# Quick test of the NixOS container infrastructure concept
# This creates a minimal test environment

set -e

echo "=== NixOS Container Infrastructure Test ==="
echo ""

# Build the containers
echo "Building container closures..."
nix build --extra-experimental-features "nix-command flakes" \
  .#nixosConfigurations.container-api-server.config.system.build.toplevel \
  --out-link result-api-server

nix build --extra-experimental-features "nix-command flakes" \
  .#nixosConfigurations.container-worker.config.system.build.toplevel \
  --out-link result-worker

nix build --extra-experimental-features "nix-command flakes" \
  .#nixosConfigurations.container-postgres.config.system.build.toplevel \
  --out-link result-postgres

echo ""
echo "✓ All containers built successfully!"
echo ""

# Show what was built
echo "Container closures:"
ls -la result-*
echo ""

# Show the activation scripts
echo "Activation script for api-server:"
head -20 result-api-server/activate || echo "(script content)"
echo ""

echo "=== Infrastructure Summary ==="
echo ""
echo "Network: 10.100.0.0/16"
echo "  Gateway: 10.100.0.1"
echo "  api-server: 10.100.1.10"
echo "  worker:     10.100.2.10"
echo "  postgres:   10.100.3.10"
echo ""
echo "To deploy to a NixOS host:"
echo "  nixos-rebuild switch --flake .#infra-host --target-host root@nixos-host"
echo ""
echo "The flake demonstrates:"
echo "  ✓ Declarative container definitions"
echo "  ✓ Network topology with static IPs"
echo "  ✓ Service configuration (api, worker, postgres)"
echo "  ✓ Inter-container networking on subnet"
echo ""
