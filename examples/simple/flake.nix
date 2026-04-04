{
  description = "Simple NCP Example with Frontend-Backend Communication";
  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  
  outputs = { self, nixpkgs }: let
    # Backend server script - returns JSON
    backendScript = pkgs: pkgs.writeText "backend.py" ''
from http.server import BaseHTTPRequestHandler, HTTPServer
import json

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps({"message": "Hello from backend", "status": "running"}).encode())
    def log_message(self, *args): pass

HTTPServer(("", 80), Handler).serve_forever()
'';

    # Frontend server script - returns HTML with JS that fetches from backend
    frontendScript = pkgs: pkgs.writeText "frontend.py" ''
from http.server import BaseHTTPRequestHandler, HTTPServer

HTML_CONTENT = b"""<!DOCTYPE html>
<html>
<head>
    <title>Frontend</title>
    <style>
        body {{ font-family: system-ui, sans-serif; max-width: 600px; margin: 2rem auto; padding: 1rem; }}
        h1 {{ color: #333; border-bottom: 2px solid #5277c3; padding-bottom: 0.5rem; }}
        #data {{ background: #f5f5f5; padding: 1rem; border-radius: 8px; margin-top: 1rem; }}
        .loading {{ color: #666; }}
        .error {{ color: #d32f2f; }}
        .success {{ color: #388e3c; }}
    </style>
</head>
<body>
    <h1>Hello from Frontend</h1>
    <p>This page fetches data from the backend container.</p>
    <div id="data"><span class="loading">Loading from backend...</span></div>
    
    <script>
        async function fetchFromBackend() {{
            const dataDiv = document.getElementById('data');
            try {{
                // Backend is at 10.100.0.2 (via container network)
                const response = await fetch('http://10.100.0.2:80/');
                if (!response.ok) throw new Error('HTTP ' + response.status);
                const data = await response.json();
                dataDiv.innerHTML = '<span class="success">Backend says:</span> <pre>' + JSON.stringify(data, null, 2) + '</pre>';
            }} catch (err) {{
                dataDiv.innerHTML = '<span class="error">Error fetching from backend:</span> ' + err.message;
            }}
        }}
        
        fetchFromBackend();
    </script>
</body>
</html>"""

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Type', 'text/html')
        self.end_headers()
        self.wfile.write(HTML_CONTENT)
    def log_message(self, *args): pass

HTTPServer(("", 80), Handler).serve_forever()
'';
  in {
    nixosConfigurations.backend = nixpkgs.lib.nixosSystem {
      system = "x86_64-linux";
      modules = [({ pkgs, ... }: {
        boot.isContainer = true;
        networking.useDHCP = false;
        networking.firewall = {
          enable = true;
          allowedTCPPorts = [ 80 ];
        };
        
        systemd.services.backend = {
          description = "Backend API Server";
          wantedBy = [ "multi-user.target" ];
          after = [ "network.target" ];
          serviceConfig = {
            ExecStart = "${pkgs.python3}/bin/python3 ${backendScript pkgs}";
            Restart = "always";
          };
        };
      })];
    };
    
    nixosConfigurations.frontend = nixpkgs.lib.nixosSystem {
      system = "x86_64-linux";
      modules = [({ pkgs, ... }: {
        boot.isContainer = true;
        networking.useDHCP = false;
        networking.firewall = {
          enable = true;
          allowedTCPPorts = [ 80 ];
        };
        
        systemd.services.frontend = {
          description = "Frontend Web Server";
          wantedBy = [ "multi-user.target" ];
          after = [ "network.target" ];
          serviceConfig = {
            ExecStart = "${pkgs.python3}/bin/python3 ${frontendScript pkgs}";
            Restart = "always";
          };
        };
      })];
    };
    
    ncp.containers = {
      backend = { port = 9001; containerPort = 80; };
      frontend = { port = 9002; containerPort = 80; };
    };
  };
}
