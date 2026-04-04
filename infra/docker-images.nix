# OCI/Docker Container Images for NixOS Infrastructure
# Builds portable containers that work on any container runtime

{ pkgs ? import <nixpkgs> {}, lib ? pkgs.lib }:

let
  # Helper to create OCI images from NixOS closures
  mkOCIContainer = name: configModule:
    let
      # Build the NixOS system
      system = (pkgs.nixos {
        imports = [
          configModule
          {
            boot.isContainer = true;
            networking.useDHCP = false;
            networking.useHostResolvConf = lib.mkForce true;  # Use host DNS
            # Disable resolved to avoid conflict with useHostResolvConf
            services.resolved.enable = lib.mkForce false;
            systemd.network.enable = true;
            system.stateVersion = "24.11";
          }
        ];
      }).config.system.build.toplevel;
      
    in pkgs.dockerTools.buildLayeredImage {
      inherit name;
      tag = "latest";
      
      contents = [ system pkgs.coreutils pkgs.bash ];
      
      config = {
        # Entrypoint runs NixOS activation then init
        Entrypoint = [ "${system}/init" ];
        Cmd = [];
        
        # Expose service ports
        ExposedPorts = {
          "3000/tcp" = {};   # api-server, worker
          "5432/tcp" = {};   # postgres
          "22/tcp" = {};     # ssh
        };
        
        Env = [
          "PATH=${system}/sw/bin:${system}/sw/sbin:/usr/bin:/bin"
          "NIX_PATH=nixpkgs=${pkgs.path}"
        ];
      };
      
      maxLayers = 120;
    };

in {
  api-server = mkOCIContainer "api-server" ./containers/api-server.nix;
  worker = mkOCIContainer "worker" ./containers/worker.nix;
  postgres = mkOCIContainer "postgres" ./containers/postgres.nix;
}
