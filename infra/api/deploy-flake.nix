{
  description = "NCP API Self-Deployment";
  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-24.11";
  
  outputs = { self, nixpkgs }: {
    nixosConfigurations.ncp-api = nixpkgs.lib.nixosSystem {
      system = "x86_64-linux";
      modules = [({ pkgs, ... }: {
        boot.isContainer = true;
        networking.useDHCP = false;
        networking.firewall.allowedTCPPorts = [ 8000 ];
        
        # Copy updated API code to container
        systemd.services.ncp-api-update = {
          description = "Update NCP API";
          wantedBy = [ "multi-user.target" ];
          after = [ "network.target" ];
          serviceConfig = {
            Type = "oneshot";
            ExecStart = pkgs.writeShellScript "update-api" ''
              # Copy updated files from deploy source
              SRC="/var/lib/nixos-containers/ncp-api/current-system/specialisation"
              if [ -d "$SRC" ]; then
                rsync -av "$SRC/" /home/nixos/code/ncp/infra/api/
              fi
              
              # Restart the API service
              systemctl restart ncp-api || true
            '';
          };
        };
      })];
    };
    
    ncp.containers = {
      ncp-api = { port = 8000; containerPort = 8000; };
    };
  };
}
