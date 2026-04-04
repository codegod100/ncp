{
  description = "Nix Native Container Infrastructure - Railway/Fly-like container hosting with Nix";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-24.11";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    let
      # Container network configuration
      containerNetwork = {
        subnet = "10.100.0.0/16";
        gateway = "10.100.0.1";
        containers = {
          api-server = {
            ip = "10.100.1.10";
            hostPort = 8080;
          };
          worker = {
            ip = "10.100.2.10";
            hostPort = 8081;
          };
          postgres = {
            ip = "10.100.3.10";
            hostPort = 5432;
          };
        };
      };

      # Base container configuration module
      containerBase = { config, pkgs, lib, name, ip, ... }: {
        boot.isContainer = true;
        networking.useDHCP = false;
        networking.useHostResolvConf = false;
        
        systemd.network.enable = true;
        services.resolved.enable = true;
        
        boot.kernelParams = lib.mkForce [ "systemd.unified_cgroup_hierarchy=1" ];
        
        networking.interfaces.eth0 = {
          ipv4.addresses = [{
            address = ip;
            prefixLength = 16;
          }];
        };
        networking.defaultGateway = containerNetwork.gateway;
        networking.nameservers = [ "8.8.8.8" "1.1.1.1" ];
        
        services.openssh.enable = true;
        users.users.root.initialPassword = "root";
        
        system.stateVersion = "24.11";
      };

    in flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
      in {
        packages = {
          # Container closures
          container-api-server = (nixpkgs.lib.nixosSystem {
            inherit system;
            modules = [
              (args: containerBase {
                config = args.config;
                pkgs = args.pkgs;
                lib = args.lib;
                name = "api-server";
                ip = containerNetwork.containers.api-server.ip;
              })
              ./containers/api-server.nix
            ];
          }).config.system.build.toplevel;

          container-worker = (nixpkgs.lib.nixosSystem {
            inherit system;
            modules = [
              (args: containerBase {
                config = args.config;
                pkgs = args.pkgs;
                lib = args.lib;
                name = "worker";
                ip = containerNetwork.containers.worker.ip;
              })
              ./containers/worker.nix
            ];
          }).config.system.build.toplevel;

          container-postgres = (nixpkgs.lib.nixosSystem {
            inherit system;
            modules = [
              (args: containerBase {
                config = args.config;
                pkgs = args.pkgs;
                lib = args.lib;
                name = "postgres";
                ip = containerNetwork.containers.postgres.ip;
              })
              ./containers/postgres.nix
            ];
          }).config.system.build.toplevel;
          
          all-containers = pkgs.linkFarm "all-containers" {
            api-server = self.packages.${system}.container-api-server;
            worker = self.packages.${system}.container-worker;
            postgres = self.packages.${system}.container-postgres;
          };
        };

        devShells.default = pkgs.mkShell {
          buildInputs = with pkgs; [
            nixos-rebuild
            systemd
            iproute2
            iptables
            bridge-utils
            jq
          ];
        };
      }) // {
        # NixOS configurations
        nixosConfigurations = {
          # Infrastructure host that runs all containers
          infra-host = nixpkgs.lib.nixosSystem {
            system = "x86_64-linux";
            specialArgs = { inherit containerNetwork; };
            modules = [
              ./host/infra-host.nix
            ];
          };

          container-api-server = nixpkgs.lib.nixosSystem {
            system = "x86_64-linux";
            modules = [
              (args: containerBase {
                config = args.config;
                pkgs = args.pkgs;
                lib = args.lib;
                name = "api-server";
                ip = containerNetwork.containers.api-server.ip;
              })
              ./containers/api-server.nix
            ];
          };

          container-worker = nixpkgs.lib.nixosSystem {
            system = "x86_64-linux";
            modules = [
              (args: containerBase {
                config = args.config;
                pkgs = args.pkgs;
                lib = args.lib;
                name = "worker";
                ip = containerNetwork.containers.worker.ip;
              })
              ./containers/worker.nix
            ];
          };

          container-postgres = nixpkgs.lib.nixosSystem {
            system = "x86_64-linux";
            modules = [
              (args: containerBase {
                config = args.config;
                pkgs = args.pkgs;
                lib = args.lib;
                name = "postgres";
                ip = containerNetwork.containers.postgres.ip;
              })
              ./containers/postgres.nix
            ];
          };
        };
      };
}
