from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import urllib.request
import os

# Try to get container name from environment or default
CONTAINER_NAME = os.environ.get('NCP_CONTAINER_NAME', 'backend')
NCP_API_URL = os.environ.get('NCP_API_URL', 'http://nix.latha.org/api/v1')

def get_container_info():
    """Query NCP API for this container's info."""
    try:
        req = urllib.request.Request(f"{NCP_API_URL}/containers/{CONTAINER_NAME}")
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        return {"error": str(e)}

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        
        # Query our own hostname from API
        info = get_container_info()
        hostname = info.get('hostname') if 'hostname' in info else None
        
        response = {
            "message": "Hello from backend",
            "status": "running",
            "container_name": CONTAINER_NAME,
            "hostname": hostname,
            "url": f"https://{hostname}/" if hostname else None
        }
        self.wfile.write(json.dumps(response, indent=2).encode())
    
    def log_message(self, *args): 
        pass

HTTPServer(("", 80), Handler).serve_forever()
