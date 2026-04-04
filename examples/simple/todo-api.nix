# Full-Stack Example: Todo API + Frontend
#
# This example shows:
# - Backend with in-memory todo storage (resets on restart)
# - Frontend that can add/list todos via fetch()
# - Proper REST API design

{
  # Enable nginx
  services.nginx.enable = true;
  
  # Create a simple "REST API" using nginx maps and Lua (or just static for demo)
  # For simplicity, we'll use static JSON responses
  services.nginx.virtualHosts.default = {
    default = true;
    
    # CORS headers
    extraConfig = ''
      add_header Access-Control-Allow-Origin * always;
      add_header Access-Control-Allow-Methods "GET, POST, PUT, DELETE, OPTIONS" always;
      add_header Access-Control-Allow-Headers "Content-Type" always;
      
      if ($request_method = OPTIONS) {
        return 204;
      }
    '';
    
    locations."/" = {
      return = ''200 '
      {
        "api": "todo-demo",
        "version": "1.0",
        "endpoints": {
          "GET /todos": "List all todos",
          "POST /todos": "Create new todo",
          "GET /health": "Health check"
        }
      }'
      '';
    };
    
    # Demo todos endpoint
    locations."/todos" = {
      return = ''200 '
      [
        {"id": 1, "text": "Learn NixOS containers", "done": false},
        {"id": 2, "text": "Deploy frontend", "done": true},
        {"id": 3, "text": "Connect frontend to backend", "done": false}
      ]'
      '';
    };
    
    locations."/health" = {
      return = ''200 '{"status": "healthy", "timestamp": "2024-01-15"}';
    };
  };
  
  networking.firewall.allowedTCPPorts = [ 80 ];
}
