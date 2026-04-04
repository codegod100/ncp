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
              locations."/".return = ''200 '{"message":"Hello from backend"}';
            };
          };
          networking.firewall.allowedTCPPorts = [ 80 ];
        };
      };
      
      frontend = {
        port = 9002;
        containerPort = 80;
        config = { config, pkgs, ... }: {
          system.activationScripts.createHtml = ''
            mkdir -p /var/www
            echo '<h1>Frontend</h1><button onclick="fetch(\'http://204.168.220.202:9001/\').then(r=>r.json()).then(d=>alert(JSON.stringify(d)))">Test</button>' > /var/www/index.html
          '';
          services.nginx = {
            enable = true;
            virtualHosts.default = {
              default = true;
              root = "/var/www";
            };
          };
          networking.firewall.allowedTCPPorts = [ 80 ];
        };
      };
    };
  };
}
