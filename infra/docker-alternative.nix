# Docker-based NixOS Containers
# More portable alternative to systemd-nspawn

{ pkgs ? import <nixpkgs> {} }:

let
  # Helper to create container configs
  mkContainer = name: configModule: 
    pkgs.dockerTools.buildLayeredImage {
      inherit name;
      tag = "latest";
      
      contents = [
        # Create a minimal init that starts systemd
        (pkgs.writeShellScriptBin "init" ''
          #!/bin/sh
          export PATH=/run/current-system/sw/bin:/run/current-system/sw/sbin
          exec /run/current-system/init
        '')
      ];
      
      config = {
        # NixOS uses its own init, not docker's default
        Cmd = [ "/init" ];
        # Expose ports (can be overridden)
        ExposedPorts = {
          "3000/tcp" = {};
          "5432/tcp" = {};
        };
      };
      
      # Build from the NixOS system closure
      fromImage = null;
      maxLayers = 100;
    };

  # Alternative: Use the full NixOS system as base
  mkFullContainer = name: systemPath: 
    pkgs.dockerTools.buildLayeredImage {
      inherit name;
      tag = "latest";
      
      contents = [ 
        pkgs.coreutils 
        pkgs.bash
      ];
      
      extraCommands = ''
        # Create base directories
        mkdir -p nix/store
        mkdir -p run/current-system
        mkdir -p etc
        
        # Copy nix store paths
        cp -r ${systemPath}/. nix/store/ 2>/dev/null || true
        
        # Create init wrapper
        cat > init <<'EOF'
        #!/bin/sh
        exec /run/current-system/init
        EOF
        chmod +x init
        
        # Minimal os-release
        cat > etc/os-release <<'EOF'
        NAME="NixOS"
        ID=nixos
        VERSION_ID="24.11"
        EOF
      '';
      
      config = {
        Cmd = [ "/init" ];
        WorkingDir = "/";
      };
    };

in {
  # Simple docker-compose setup
  shellHook = ''
    echo "Docker-based NixOS Containers"
    echo "============================="
    echo ""
    echo "To use this infrastructure:"
    echo "  1. Build images: nix build .#dockerImages.api-server"
    echo "  2. Load: docker load < result"
    echo "  3. Run: docker-compose up"
    echo ""
    echo "Or use the simpler Docker Compose in docker-compose.yml"
  '';
}
