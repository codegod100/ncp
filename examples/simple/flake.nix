{
  description = "Simple NCP Example Project";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-parts.url = "github:hercules-ci/flake-parts";
    ncp.url = "github:codegod100/ncp";
  };

  outputs = inputs@{ self, nixpkgs, flake-parts, ncp }:
    flake-parts.lib.mkFlake { inherit inputs; } {
      imports = [ ncp.flakeModule ];
      
      systems = [ "x86_64-linux" ];
      
      ncp.containers = {
        backend = {
          port = 9001;
          containerPort = 80;
          config = { config, pkgs, ... }: {
            services.nginx = {
              enable = true;
              virtualHosts.default = {
                default = true;
                locations."/".return = builtins.readFile ./backend-response.txt;
              };
            };
            networking.firewall.allowedTCPPorts = [ 80 ];
          };
        };
        
        frontend = {
          port = 9002;
          containerPort = 80;
          config = { config, pkgs, ... }: {
            services.nginx = {
              enable = true;
              virtualHosts.default = {
                default = true;
                locations."/".return = builtins.readFile ./frontend.html;
              };
            };
            networking.firewall.allowedTCPPorts = [ 80 ];
          };
        };
      };
    };
}
