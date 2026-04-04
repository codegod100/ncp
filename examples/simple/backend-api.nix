# Backend API Container
# 
# A simple JSON API with CORS headers enabled.
# Frontend containers can fetch() from this backend.

# ncp.port = 9001;
# ncp.name = "backend-api";

{ config, pkgs, ... }:

{
  # Enable nginx web server
  services.nginx.enable = true;
  
  # Configure default virtual host
  services.nginx.virtualHosts.default = {
    default = true;
    
    # Add CORS headers so browsers allow cross-origin requests
    extraConfig = ''
      add_header Access-Control-Allow-Origin * always;
      add_header Access-Control-Allow-Methods "GET, POST, OPTIONS" always;
      add_header Access-Control-Allow-Headers "Content-Type" always;
      
      # Handle preflight OPTIONS requests
      if ($request_method = OPTIONS) {
        return 204;
      }
    '';
    
    # Return JSON for all requests
    locations."/" = {
      return = ''200 '{"message": "Hello from backend", "service": "api", "version": "1.0"}';
    };
  };
  
  # Allow HTTP traffic through firewall
  networking.firewall.allowedTCPPorts = [ 80 ];
}
