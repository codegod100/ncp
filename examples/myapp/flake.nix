{
  description = "NCP Example App - Backend + Frontend";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    ncp.url = "github:codegod100/ncp";
    flake-parts.url = "github:hercules-ci/flake-parts";
  };

  outputs = inputs@{ self, nixpkgs, ncp, flake-parts, ... }:
    flake-parts.lib.mkFlake { inherit inputs; } {
      imports = [ ncp.flakeModule ];

      systems = [ "x86_64-linux" ];

      # Define containers as flake parts
      ncp.containers = {
        backend = {
          name = "example-backend";
          port = 9001;
          
          config = { config, pkgs, lib, ... }: {
            # Backend API with CORS
            services.nginx = {
              enable = true;
              virtualHosts.default = {
                default = true;
                extraConfig = ''
                  add_header Access-Control-Allow-Origin * always;
                  add_header Access-Control-Allow-Methods "GET, POST, OPTIONS" always;
                  if ($request_method = OPTIONS) { return 204; }
                '';
                locations."/".return = ''200 '{"message": "Hello from backend"}';
              };
            };
            networking.firewall.allowedTCPPorts = [ 80 ];
          };
        };

        frontend = {
          name = "example-frontend";
          port = 9002;
          
          config = { config, pkgs, lib, ... }: {
            # Frontend that calls backend
            system.activationScripts.createHtml = ''
              mkdir -p /var/www
              cat > /var/www/index.html << 'EOF'
<!DOCTYPE html>
<html>
<head><title>Frontend</title></head>
<body>
  <h1>Frontend</h1>
  <button onclick="fetchData()">Fetch from Backend</button>
  <pre id="output"></pre>
  <script>
    async function fetchData() {
      const r = await fetch('http://204.168.220.202:9001/');
      const d = await r.json();
      document.getElementById('output').textContent = JSON.stringify(d);
    }
  </script>
</body>
</html>
EOF
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
