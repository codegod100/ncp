{
  description = "Simple NCP Example";
  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  
  outputs = { self, nixpkgs }: {
    nixosConfigurations.backend = nixpkgs.lib.nixosSystem {
      system = "x86_64-linux";
      modules = [({ pkgs, ... }: {
        boot.isContainer = true;
        networking.useDHCP = false;
        networking.firewall = {
          enable = true;
          allowedTCPPorts = [ 80 ];
        };
        services.nginx = {
          enable = true;
          virtualHosts.default = {
            default = true;
            locations."/" = {
              extraConfig = ''
                return 200 '{"message":"Hello from backend"}';
              '';
            };
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
        services.nginx = {
          enable = true;
          virtualHosts.default = {
            default = true;
            locations."/" = {
              extraConfig = ''
                return 200 '<h1>Hello from frontend</h1>';
              '';
            };
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
