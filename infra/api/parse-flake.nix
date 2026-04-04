# Nix flake parser for NCP
# Usage from Python: write flakePath to a temp file, then:
# nix eval --impure --json --expr 'import ./parse-flake.nix { flakePath = ./examples/simple; }'

{ flakePath }:

let
  flake = builtins.getFlake (toString flakePath);
  containers = flake.ncp.containers or {};

  # Extract serializable fields
  extractContainer = name: container: {
    inherit name;
    port = container.port or null;
    containerPort = container.containerPort or 80;
    hasConfig = container ? config;
  };

in
  builtins.mapAttrs extractContainer containers
