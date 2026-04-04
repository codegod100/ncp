#!/bin/bash
# Quick deploy script for frontend+backend example pair using ncp CLI
# Usage: ncp login --server https://nix.latha.org && ./deploy-pair.sh

set -e

HOST_IP="204.168.220.202"  # Change to your server's IP

echo "=== Deploying Example Backend + Frontend ==="
echo ""

# Check if logged in
if ! ncp token >/dev/null 2>&1; then
    echo "Error: Not logged in. Run: ncp login --server https://nix.latha.org"
    exit 1
fi

echo "Deploying backend (example-backend:9101)..."
ncp deploy --name example-backend --port 9101 --config backend-api.nix

echo ""
echo "Deploying frontend (example-frontend:9102)..."
echo "Note: Edit frontend-app.nix first to set backendUrl if needed"
ncp deploy --name example-frontend --port 9102 --config frontend-app.nix

echo ""
echo "=== Done ==="
echo "Backend: http://${HOST_IP}:9101/"
echo "Frontend: http://${HOST_IP}:9102/"
echo ""
echo "Test it:"
echo "  curl http://${HOST_IP}:9101/"
echo "  # Then open frontend in browser and click 'Fetch from Backend'"
