# NCP Flake Module
# 
# This module defines the ncp.containers option for use in flake-parts or standard flakes.

{ lib, config, ... }:

let
  cfg = config.ncp;
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

  config = {};
}
