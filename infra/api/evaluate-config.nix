# evaluate-config.nix - Put this in the repo
{ flakePath, containerName }:

let
  flake = builtins.getFlake (toString flakePath);
  container = flake.ncp.containers.${containerName};
  
  # Call the config function with the required arguments
  evaluatedConfig = container.config {
    config = {};
    pkgs = import <nixpkgs> {};
    lib = (import <nixpkgs> {}).lib;
    modulesPath = <nixpkgs/nixos/modules>;
  };
  
in
  evaluatedConfig
