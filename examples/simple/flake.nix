{
  description = "Simple NCP Example Project";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs = { self, nixpkgs }: {
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
