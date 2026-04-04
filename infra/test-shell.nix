# Lightweight Container Test Setup
# 
# This creates containers directly using nixos-container without a full host config.
# Useful for testing on any NixOS system.

{ pkgs ? import <nixpkgs> {} }:

let
  # Helper to create a container closure
  mkContainer = name: configModule: 
    (pkgs.nixos {
      imports = [
        configModule
        {
          boot.isContainer = true;
          networking.useDHCP = false;
          networking.useHostResolvConf = false;
          
          # Container network - will be overridden by nixos-container
          networking.interfaces.eth0 = {
            useDHCP = true;
          };
          
          services.openssh.enable = true;
          users.users.root.initialPassword = "root";
          
          system.stateVersion = "24.11";
        }
      ];
    }).config.system.build.toplevel;

  # Container definitions
  containers = {
    api-server = mkContainer "api-server" ./containers/api-server.nix;
    worker = mkContainer "worker" ./containers/worker.nix;
    postgres = mkContainer "postgres" ./containers/postgres.nix;
  };

  # Setup script for manual container creation
  setupScript = pkgs.writeShellScriptBin "setup-containers" ''
    set -e
    
    CONTAINER_DIR="/var/lib/nixos-containers"
    
    echo "Setting up Nix Native Containers..."
    echo "===================================="
    
    # Create network bridge if it doesn't exist
    if ! ip link show ctrs 2>/dev/null; then
      echo "Creating bridge: ctrs"
      ip link add ctrs type bridge
      ip addr add 10.100.0.1/16 dev ctrs
      ip link set ctrs up
    fi
    
    # Enable IP forwarding
    echo 1 > /proc/sys/net/ipv4/ip_forward
    
    # Setup NAT
    iptables -t nat -A POSTROUTING -s 10.100.0.0/16 ! -d 10.100.0.0/16 -j MASQUERADE 2>/dev/null || true
    
    # Create containers
    for ctr in api-server worker postgres; do
      if [ -d "$CONTAINER_DIR/$ctr" ]; then
        echo "Container $ctr already exists, skipping..."
      else
        echo "Creating container: $ctr"
        
        # Determine IP based on container name
        case $ctr in
          api-server) IP="10.100.1.10" ;;
          worker) IP="10.100.2.10" ;;
          postgres) IP="10.100.3.10" ;;
        esac
        
        nixos-container create $ctr \
          --bridge ctrs \
          --host-address 10.100.0.1 \
          --local-address $IP
      fi
    done
    
    echo ""
    echo "Starting containers..."
    for ctr in api-server worker postgres; do
      echo "Starting: $ctr"
      nixos-container start $ctr || true
    done
    
    echo ""
    echo "Setup complete! Containers:"
    nixos-container list
    echo ""
    echo "Network status:"
    ip addr show ctrs
  '';

  # Test script
  testScript = pkgs.writeShellScriptBin "test-containers" ''
    echo "=== Container Status ==="
    nixos-container list
    
    echo ""
    echo "=== Testing Inter-Container Networking ==="
    
    # Wait a moment for services to start
    sleep 2
    
    echo ""
    echo "1. Testing api-server -> postgres (10.100.3.10:5432)..."
    nixos-container run api-server -- bash -c 'timeout 5 bash -c "cat < /dev/null > /dev/tcp/10.100.3.10/5432" 2>/dev/null && echo "SUCCESS: api-server can reach postgres" || echo "FAILED: api-server cannot reach postgres"' 2>/dev/null
    
    echo ""
    echo "2. Testing worker -> postgres (10.100.3.10:5432)..."
    nixos-container run worker -- bash -c 'timeout 5 bash -c "cat < /dev/null > /dev/tcp/10.100.3.10/5432" 2>/dev/null && echo "SUCCESS: worker can reach postgres" || echo "FAILED: worker cannot reach postgres"' 2>/dev/null
    
    echo ""
    echo "3. Testing api-server -> worker (10.100.2.10:3000)..."
    nixos-container run api-server -- bash -c 'timeout 5 bash -c "cat < /dev/null > /dev/tcp/10.100.2.10/3000" 2>/dev/null && echo "SUCCESS: api-server can reach worker" || echo "FAILED: api-server cannot reach worker"' 2>/dev/null
    
    echo ""
    echo "4. Testing worker -> api-server (10.100.1.10:3000)..."
    nixos-container run worker -- bash -c 'timeout 5 bash -c "cat < /dev/null > /dev/tcp/10.100.1.10/3000" 2>/dev/null && echo "SUCCESS: worker can reach api-server" || echo "FAILED: worker cannot reach api-server"' 2>/dev/null
    
    echo ""
    echo "=== Container IPs ==="
    for ctr in api-server worker postgres; do
      IP=$(nixos-container run $ctr -- hostname -I 2>/dev/null | tr -d '\n')
      echo "$ctr: $IP"
    done
  '';

in pkgs.stdenv.mkDerivation {
  name = "nix-native-containers";
  
  buildInputs = with pkgs; [
    setupScript
    testScript
    nixos-container
    iproute2
    iptables
    bridge-utils
    curl
    jq
  ];
  
  shellHook = ''
    echo "Nix Native Container Test Environment"
    echo "===================================="
    echo ""
    echo "Commands available:"
    echo "  setup-containers  - Create bridge and start all containers"
    echo "  test-containers   - Test inter-container networking"
    echo "  nixos-container   - Manage individual containers"
    echo ""
    echo "Container network: 10.100.0.0/16"
    echo "  api-server: 10.100.1.10"
    echo "  worker:     10.100.2.10"
    echo "  postgres:   10.100.3.10"
    echo ""
    echo "Quick start:"
    echo "  1. Run: setup-containers"
    echo "  2. Run: test-containers"
    echo ""
    alias setup='setup-containers'
    alias test-net='test-containers'
    alias ctr-shell='nixos-container root-login'
  '';
}
