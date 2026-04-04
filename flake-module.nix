# NCP Flake Module
# 
# This module can be imported into your flake to define NCP containers
# using the flake-parts module system.
#
# Example usage in your flake.nix:
#   imports = [ ncp.flakeModule ];
#   
#   ncp.containers.backend = {
#     name = "my-backend";
#     port = 9001;
#     config = { config, pkgs, ... }: {
#       services.nginx.enable = true;
#     };
#   };

{ lib, config, ... }:

let
  cfg = config.ncp;
  
  # Helper to generate container metadata JSON
  mkContainerPackage = name: containerDef: 
    builtins.toJSON {
      inherit name;
      containerName = containerDef.name;
      hostPort = containerDef.port;
      containerPort = containerDef.containerPort;
    };
in
{
  options.ncp = {
    containers = lib.mkOption {
      type = lib.types.attrsOf (lib.types.submodule {
        options = {
          name = lib.mkOption {
            type = lib.types.str;
            description = "Container name";
          };
          
          port = lib.mkOption {
            type = lib.types.int;
            description = "External host port";
          };
          
          containerPort = lib.mkOption {
            type = lib.types.int;
            default = 80;
            description = "Internal container port";
          };
          
          config = lib.mkOption {
            type = lib.types.raw;
            description = "NixOS configuration function";
          };
        };
      });
      default = {};
      description = "NCP containers to deploy";
    };
  };

  config = lib.mkIf (cfg.containers != {}) {
    # Expose container metadata as packages
    # The CLI can use these to get deployment info
    perSystem = { system, pkgs, ... }: {
      packages = lib.mapAttrs' (name: containerDef:
        lib.nameValuePair "ncp-${name}" (mkContainerPackage name containerDef)
      ) cfg.containers;
    };
  };
}
