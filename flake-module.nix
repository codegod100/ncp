# NCP Flake Module
# 
# This module can be imported into your flake to define NCP containers
# using the flake-parts module system.

{ lib, config, ... }:

let
  cfg = config.ncp;
  
  # Generate a NixOS configuration for each container
  mkNixosConfig = name: containerDef: { config, pkgs, lib, ... }: {
    # Base container settings
    boot.isContainer = true;
    networking.useDHCP = false;
    networking.firewall.enable = true;
    
    # Container-specific config
    networking.hostName = lib.mkDefault name;
    
    # Apply user's config
    imports = [
      (containerDef.config { inherit config pkgs lib; })
    ];
  };
in
{
  options.ncp = {
    containers = lib.mkOption {
      type = lib.types.attrsOf (lib.types.submodule {
        options = {
          port = lib.mkOption {
            type = lib.types.int;
            description = "External host port for this container";
          };
          
          containerPort = lib.mkOption {
            type = lib.types.int;
            default = 80;
            description = "Internal container port";
          };
          
          config = lib.mkOption {
            type = lib.types.functionTo lib.types.attrs;
            description = "NixOS configuration function: { config, pkgs, ... }: { ... }";
          };
        };
      });
      default = {};
      description = "NCP containers to deploy";
    };
  };

  config = lib.mkIf (cfg.containers != {}) {
    # Export as nixosConfigurations for nixos-container --flake
    nixosConfigurations = lib.mapAttrs (name: containerDef:
      lib.nixosSystem {
        system = "x86_64-linux";
        modules = [ (mkNixosConfig name containerDef) ];
      }
    ) cfg.containers;
  };
}
