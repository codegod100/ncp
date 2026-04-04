#!/bin/bash
# Quick deploy script for frontend+backend example pair
# Usage: export TOKEN=your_jwt_token && ./deploy-pair.sh

set -e

API_URL="https://nix.latha.org/api/v1"
HOST_IP="204.168.220.202"  # Change to your server's IP

if [ -z "$TOKEN" ]; then
    echo "Error: Set TOKEN environment variable"
    echo "Get token: curl -X POST $API_URL/auth/login -d '{\"username\":\"...\",\"password\":\"...\"}'"
    exit 1
fi

echo "=== Deploying Backend (port 9101) ==="
curl -s -X POST "$API_URL/containers" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "example-backend",
    "host_port": 9101,
    "nix_config": "services.nginx.enable = true; services.nginx.virtualHosts.default = { default = true; extraConfig = '' add_header Access-Control-Allow-Origin * always; add_header Access-Control-Allow-Methods \\"GET, POST, OPTIONS\\" always; add_header Access-Control-Allow-Headers \\"Content-Type\\" always; if (\\$request_method = OPTIONS) { return 204; } ''; locations.\\"/\\" = { return = \\"200 '{\\\\\\"message\\\\\\": \\\\\\"Hello from backend\\\\\\", \\\\\\"service\\\\\\": \\\\\\"api\\\\\\", \\\\\\"timestamp\\\\\\": \\\\\\"${builtins.toString builtins.currentTime}\\\\\\"}'\\"; }; }; networking.firewall.allowedTCPPorts = [ 80 ];"
  }'

echo ""
echo "=== Deploying Frontend (port 9102) ==="

# Create frontend config with backend URL embedded
BACKEND_URL="http://${HOST_IP}:9101"
FRONTEND_HTML="<!DOCTYPE html><html><head><meta charset=utf-8><title>Example Frontend</title><style>body{font-family:sans-serif;max-width:800px;margin:40px auto;padding:20px;background:#f5f5f5}.box{background:white;padding:20px;border-radius:8px;box-shadow:0 2px 4px rgba(0,0,0,0.1)}h1{color:#333;border-bottom:3px solid #007acc}pre{background:#1e1e1e;color:#0f0;padding:15px;border-radius:4px}button{padding:10px 20px;background:#007acc;color:white;border:none;border-radius:4px;cursor:pointer;margin:5px}</style></head><body><h1>🚀 Example Frontend</h1><div class=box><h3>Backend Connection</h3><p>Backend: ${BACKEND_URL}</p><button onclick=fetchData()>Fetch from Backend</button><button onclick=clearData()>Clear</button><h4>Response:</h4><pre id=output>Click to fetch...</pre></div><p><a href=${BACKEND_URL} target=_blank>Direct backend link</a></p><script>async function fetchData(){const o=document.getElementById('output');o.textContent='Loading...';try{const r=await fetch('${BACKEND_URL}');const d=await r.json();o.textContent=JSON.stringify(d,null,2)}catch(e){o.textContent='Error: '+e}}function clearData(){document.getElementById('output').textContent='Click to fetch...'}</script></body></html>"

curl -s -X POST "$API_URL/containers" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"name\": \"example-frontend\",
    \"host_port\": 9102,
    \"nix_config\": \"system.activationScripts.createHtml = '' mkdir -p /var/www; echo '${FRONTEND_HTML}' > /var/www/index.html ''; services.nginx.enable = true; services.nginx.virtualHosts.default = { default = true; root = \\"/var/www\\"; extraConfig = \\"charset utf-8; default_type text/html;\\"; }; networking.firewall.allowedTCPPorts = [ 80 ];\"
  }"

echo ""
echo "=== Done ==="
echo "Backend: http://${HOST_IP}:9101/"
echo "Frontend: http://${HOST_IP}:9102/"
