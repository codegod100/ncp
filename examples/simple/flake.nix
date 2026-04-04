{
  description = "Simple NCP Example";
  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  
  outputs = { self, nixpkgs }: let
    # Backend server script
    backendScript = pkgs: pkgs.writeText "backend.py" ''
from http.server import BaseHTTPRequestHandler, HTTPServer
import json

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps({"message": "Hello from backend"}).encode())
    def log_message(self, *args): pass

HTTPServer(("", 80), Handler).serve_forever()
'';

    # Frontend server script  
    frontendScript = pkgs: pkgs.writeText "frontend.py" ''
from http.server import BaseHTTPRequestHandler, HTTPServer

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Type', 'text/html')
        self.end_headers()
        self.wfile.write(b"<h1>Hello from frontend</h1>")
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
