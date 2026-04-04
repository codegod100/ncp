# build-container.nix
# Builds a NixOS container system from a project flake
# Usage: nix build --impure -f build-container.nix --arg projectPath ./myproject --argstr containerName backend

{ projectPath, containerName }:

let
  flake = builtins.getFlake (toString projectPath);
  container = flake.ncp.containers.${containerName};
  
  pkgs = import <nixpkgs> {};
  lib = pkgs.lib;
  
  # Build the NixOS system for this container
  system = pkgs.nixos {
    configuration = { config, pkgs, lib, ... }:
      let
        cfg = container.config { inherit config pkgs lib; modulesPath = <nixpkgs/nixos/modules>; };
      in
        lib.mkMerge [
          {
            boot.isContainer = true;
            networking.useDHCP = false;
            networking.firewall.enable = true;
          }
          cfg
        ];
  };

in
  system.config.system.build.toplevel
