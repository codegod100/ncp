# API Server Container Configuration
# A simple HTTP API server using socat

{ config, pkgs, lib, ... }:

let
  apiServer = pkgs.writeShellScriptBin "api-server" ''
    #!${pkgs.bash}/bin/bash
    
    echo "[api-server] Starting API Server on 0.0.0.0:3000"
    
    handle_request() {
      IFS= read -r request
      
      if echo "$request" | grep -q "GET /health"; then
        echo -e "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n\r\n{\"status\":\"healthy\",\"service\":\"api-server\",\"timestamp\":\"$(date -Iseconds)\"}"
      else
        PG_STATUS="unreachable"
        WORKER_STATUS="unreachable"
        
        # Check postgres connectivity
        if bash -c 'cat < /dev/null > /dev/tcp/10.100.3.10/5432' 2>/dev/null; then
          PG_STATUS="reachable"
        fi
        
        # Check worker connectivity
        if bash -c 'cat < /dev/null > /dev/tcp/10.100.2.10/3000' 2>/dev/null; then
          WORKER_STATUS="reachable"
        fi
        
        echo -e "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n\r\n{\"service\":\"api-server\",\"network\":{\"postgres\":\"$PG_STATUS\",\"worker\":\"$WORKER_STATUS\"},\"timestamp\":\"$(date -Iseconds)\"}"
      fi
    }
    export -f handle_request
    
    while true; do
      ${pkgs.socat}/bin/socat TCP-LISTEN:3000,fork,reuseaddr EXEC:"${pkgs.bash}/bin/bash -c handle_request"
    done
  '';

in {
  networking.firewall = {
    enable = true;
    allowedTCPPorts = [ 3000 22 ];
  };

  environment.systemPackages = with pkgs; [
    apiServer
    bash
    socat
    coreutils
    curl
    jq
    iproute2
    inetutils
    postgresql
  ];

  systemd.services.api-server = {
    description = "Simple HTTP API Server";
    wantedBy = [ "multi-user.target" ];
    after = [ "network.target" ];
    
    serviceConfig = {
      Type = "simple";
      ExecStart = "${apiServer}/bin/api-server";
      Restart = "always";
      RestartSec = 2;
    };
  };

  networking.hostName = "api-server";
  system.stateVersion = "24.11";
}
