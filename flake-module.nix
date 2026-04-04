# flake-module.nix - Exports ncp.containers as nixosConfigurations
{ lib, config, ... }:
let
  cfg = config.ncp;
in
{
  options.ncp.containers = lib.mkOption {
    type = lib.types.attrsOf (lib.types.submodule {
      options = {
        port = lib.mkOption { type = lib.types.int; description = "External port"; };
        containerPort = lib.mkOption { type = lib.types.int; default = 80; };
        config = lib.mkOption { 
          type = lib.types.functionTo lib.types.attrs;
          description = "NixOS config: { config, pkgs, ... }: { ... }";
        };
      };
    });
    default = {};
  };

  config = lib.mkIf (cfg.containers != {}) {
    nixosConfigurations = lib.mapAttrs (name: c:
      lib.nixosSystem {
        system = "x86_64-linux";
        modules = [{
          boot.isContainer = true;
          networking.useDHCP = false;
          networking.firewall.enable = true;
          imports = [ (c.config { inherit config pkgs lib; modulesPath = <nixpkgs/nixos/modules>; }) ];
        }];
      }
    ) cfg.containers;
  };
}
