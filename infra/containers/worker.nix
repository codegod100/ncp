# Worker Container Configuration
# Background worker with health check endpoint

{ config, pkgs, lib, ... }:

let
  # Health response handler script
  healthHandler = pkgs.writeShellScript "health-handler" ''
    echo -e "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n\r\n{\"status\":\"healthy\",\"service\":\"worker\",\"timestamp\":\"$(date -Iseconds)\"}"
  '';

  healthServer = pkgs.writeShellScriptBin "health-server" ''
    #!${pkgs.bash}/bin/bash
    # Use socat with SYSTEM to run the handler for each connection
    ${pkgs.socat}/bin/socat TCP-LISTEN:3000,reuseaddr,fork SYSTEM:"${healthHandler}"
  '';

  worker = pkgs.writeShellScriptBin "worker" ''
    #!${pkgs.bash}/bin/bash
    
    echo "[worker] Starting background worker"
    
    # Start health server in background
    ${healthServer}/bin/health-server &
    
    # Main worker loop
    while true; do
      echo "[worker] $(date): Checking dependencies..."
      
      # Check postgres
      if ${pkgs.bash}/bin/bash -c 'cat < /dev/null > /dev/tcp/10.100.3.10/5432' 2>/dev/null; then
        echo "[worker] PostgreSQL is reachable"
      else
        echo "[worker] PostgreSQL is not reachable yet"
      fi
      
      # Check api-server
      if ${pkgs.bash}/bin/bash -c 'cat < /dev/null > /dev/tcp/10.100.1.10/3000' 2>/dev/null; then
        echo "[worker] API Server is reachable"
      else
        echo "[worker] API Server is not reachable yet"
      fi
      
      echo "[worker] Processing job batch..."
      sleep 10
    done
  '';

in {
  networking.firewall = {
    enable = true;
    allowedTCPPorts = [ 3000 22 ];
  };

  environment.systemPackages = with pkgs; [
    worker
    healthServer
    bash
    socat
    coreutils
    curl
    jq
    iproute2
    inetutils
  ];

  systemd.services.worker = {
    description = "Background Worker Service";
    wantedBy = [ "multi-user.target" ];
    after = [ "network.target" ];
    
    serviceConfig = {
      Type = "simple";
      ExecStart = "${worker}/bin/worker";
      Restart = "always";
      RestartSec = 2;
      StandardOutput = "journal";
      StandardError = "journal";
    };
  };

  networking.hostName = "worker";
  system.stateVersion = "24.11";
}
