# evaluate-project.nix
# Evaluates a project flake and outputs container definitions as JSON
# Usage: nix eval --impure --json -f evaluate-project.nix --arg projectPath ./myproject

{ projectPath }:

let
  flake = builtins.getFlake (toString projectPath);
  containers = flake.ncp.containers or {};
  
  # Import nixpkgs for pkgs and lib
  pkgs = import <nixpkgs> {};
  lib = pkgs.lib;
  
  # Evaluate a single container's config function
  evaluateConfig = container:
    let
      cfg = container.config or {};
    in
      if builtins.isFunction cfg then
        # Call the config function with required arguments
        cfg { 
          config = {}; 
          inherit pkgs lib;
          modulesPath = <nixpkgs/nixos/modules>;
        }
      else 
        cfg;
  
  # Convert evaluated config to a serializable format
  # We need to filter out non-serializable values
  serializeConfig = config:
    let
      # Recursively process config
      process = val:
        if builtins.isString val then { _type = "string"; value = val; }
        else if builtins.isInt val then { _type = "int"; value = val; }
        else if builtins.isBool val then { _type = "bool"; value = val; }
        else if builtins.isList val then { _type = "list"; value = map process val; }
        else if builtins.isAttrs val then 
          if val ? _type then val  # Already processed
          else { _type = "attrs"; value = lib.mapAttrs (n: process) val; }
        else { _type = "unknown"; value = ""; };
    in
      process config;
  
  # Build container info
  buildContainerInfo = name: container: {
    inherit name;
    port = container.port or null;
    containerPort = container.containerPort or 80;
    config = serializeConfig (evaluateConfig container);
  };
  
in
  lib.mapAttrs buildContainerInfo containers
