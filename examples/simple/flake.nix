{
  description = "Simple NCP Example with Frontend-Backend Communication";
  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  
  outputs = { self, nixpkgs }: {
    nixosConfigurations.backend = nixpkgs.lib.nixosSystem {
      system = "x86_64-linux";
      modules = [({ pkgs, ... }: 
        let
          backendScript = pkgs.writeText "backend.py" (builtins.readFile ./backend.py);
        in {
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
              ExecStart = "${pkgs.python3}/bin/python3 ${backendScript}";
              Restart = "always";
            };
          };
        }
      )];
    };
    
    nixosConfigurations.frontend = nixpkgs.lib.nixosSystem {
      system = "x86_64-linux";
      modules = [({ pkgs, ... }:
        let
          frontendScript = pkgs.writeText "frontend.py" (builtins.readFile ./frontend.py);
        in {
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
              ExecStart = "${pkgs.python3}/bin/python3 ${frontendScript}";
              Restart = "always";
            };
          };
        }
      )];
    };
    
    ncp.containers = {
      backend = { port = 9001; containerPort = 80; };
      frontend = { port = 9002; containerPort = 80; };
    };
  };
}
