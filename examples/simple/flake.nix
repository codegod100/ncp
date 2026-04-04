{
  description = "Simple NCP Example";
  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  
  outputs = { self, nixpkgs }: {
    # Export containers as nixosConfigurations for nixos-container --flake
    nixosConfigurations.backend = nixpkgs.lib.nixosSystem {
      system = "x86_64-linux";
      modules = [{
        boot.isContainer = true;
        networking.useDHCP = false;
        networking.firewall.enable = true;
        services.nginx = {
          enable = true;
          virtualHosts.default = {
            default = true;
            locations."/".return = builtins.readFile ./backend-response.txt;
          };
        };
      }];
    };
    
    nixosConfigurations.frontend = nixpkgs.lib.nixosSystem {
      system = "x86_64-linux";
      modules = [{
        boot.isContainer = true;
        networking.useDHCP = false;
        networking.firewall.enable = true;
        services.nginx = {
          enable = true;
          virtualHosts.default = {
            default = true;
            locations."/".return = builtins.readFile ./frontend.html;
          };
        };
      }];
    };
    
    # Also export ncp.containers for the API to read ports
    ncp.containers = {
      backend = { port = 9001; containerPort = 80; };
      frontend = { port = 9002; containerPort = 80; };
    };
  };
}
