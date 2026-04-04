#!/bin/bash
# Quick deploy script for frontend+backend example pair using ncp CLI
# Usage: ncp login && ./deploy-pair.sh

set -e

HOST_IP="204.168.220.202"  # Change to your server's IP

echo "=== Deploying Example Backend + Frontend ==="
echo ""

# Check auth status
if ! ncp status 2>/dev/null | grep -q "Authenticated"; then
    echo "❌ Not authenticated. Please run: ncp login"
    exit 1
fi

echo "✅ Authenticated"
echo ""

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
