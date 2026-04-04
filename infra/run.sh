#!/usr/bin/env bash
# Container runtime script for the infrastructure flake
# Usage: ./run.sh [command]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONTAINER_NETWORK="10.100.0.0/16"
BRIDGE_NAME="ctrs"

# Nix experimental features for flakes
export NIX_CONFIG="experimental-features = nix-command flakes"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log() {
  echo -e "${BLUE}[infra]${NC} $1"
}

log_ok() {
  echo -e "${GREEN}[infra]${NC} $1"
}

log_warn() {
  echo -e "${YELLOW}[infra]${NC} $1"
}

log_error() {
  echo -e "${RED}[infra]${NC} $1"
}

check_root() {
  if [ "$EUID" -ne 0 ]; then
    log_error "This command requires root privileges"
    exit 1
  fi
}

cmd_build() {
  log "Building container closures..."
  nix build --extra-experimental-features "nix-command flakes" --no-link \
    ".#nixosConfigurations.container-api-server.config.system.build.toplevel" \
    ".#nixosConfigurations.container-worker.config.system.build.toplevel" \
    ".#nixosConfigurations.container-postgres.config.system.build.toplevel"
  log_ok "Build complete"
}

cmd_network_setup() {
  check_root
  
  log "Setting up container network..."
  
  # Create bridge if it doesn't exist
  if ! ip link show "$BRIDGE_NAME" 2>/dev/null; then
    log "Creating bridge: $BRIDGE_NAME"
    ip link add "$BRIDGE_NAME" type bridge
    ip addr add "10.100.0.1/16" dev "$BRIDGE_NAME"
    ip link set "$BRIDGE_NAME" up
    log_ok "Bridge created"
  else
    log_warn "Bridge $BRIDGE_NAME already exists"
  fi
  
  # Enable IP forwarding
  if [ "$(cat /proc/sys/net/ipv4/ip_forward)" != "1" ]; then
    echo 1 > /proc/sys/net/ipv4/ip_forward
    log_ok "IP forwarding enabled"
  fi
  
  # Setup NAT (idempotent)
  if ! iptables -t nat -C POSTROUTING -s "$CONTAINER_NETWORK" ! -d "$CONTAINER_NETWORK" -j MASQUERADE 2>/dev/null; then
    iptables -t nat -A POSTROUTING -s "$CONTAINER_NETWORK" ! -d "$CONTAINER_NETWORK" -j MASQUERADE
    log_ok "NAT rules added"
  fi
  
  # Allow forwarding between containers
  iptables -A FORWARD -i "$BRIDGE_NAME" -o "$BRIDGE_NAME" -j ACCEPT 2>/dev/null || true
  
  log_ok "Network setup complete"
}

cmd_create() {
  check_root
  cmd_network_setup
  
  log "Creating containers..."
  
  # Create containers with static IPs
  if [ ! -d "/var/lib/nixos-containers/api-server" ]; then
    log "Creating api-server (10.100.1.10)"
    nixos-container create api-server \
      --bridge "$BRIDGE_NAME" \
      --host-address 10.100.0.1 \
      --local-address 10.100.1.10 \
      --config-file "$SCRIPT_DIR/containers/api-server.nix"
  else
    log_warn "api-server already exists"
  fi
  
  if [ ! -d "/var/lib/nixos-containers/worker" ]; then
    log "Creating worker (10.100.2.10)"
    nixos-container create worker \
      --bridge "$BRIDGE_NAME" \
      --host-address 10.100.0.1 \
      --local-address 10.100.2.10 \
      --config-file "$SCRIPT_DIR/containers/worker.nix"
  else
    log_warn "worker already exists"
  fi
  
  if [ ! -d "/var/lib/nixos-containers/postgres" ]; then
    log "Creating postgres (10.100.3.10)"
    nixos-container create postgres \
      --bridge "$BRIDGE_NAME" \
      --host-address 10.100.0.1 \
      --local-address 10.100.3.10 \
      --config-file "$SCRIPT_DIR/containers/postgres.nix"
  else
    log_warn "postgres already exists"
  fi
  
  log_ok "All containers created"
}

cmd_start() {
  check_root
  log "Starting containers..."
  
  nixos-container start api-server || log_warn "api-server failed to start"
  sleep 1
  nixos-container start worker || log_warn "worker failed to start"
  sleep 1
  nixos-container start postgres || log_warn "postgres failed to start"
  
  log_ok "Start commands issued"
  cmd_status
}

cmd_stop() {
  check_root
  log "Stopping containers..."
  
  nixos-container stop postgres 2>/dev/null || true
  nixos-container stop worker 2>/dev/null || true
  nixos-container stop api-server 2>/dev/null || true
  
  log_ok "Containers stopped"
}

cmd_destroy() {
  check_root
  cmd_stop
  
  log "Destroying containers..."
  
  nixos-container destroy postgres 2>/dev/null || true
  nixos-container destroy worker 2>/dev/null || true
  nixos-container destroy api-server 2>/dev/null || true
  
  log_ok "Containers destroyed"
}

cmd_status() {
  log "Container Status:"
  printf "%-15s %-10s %-20s\n" "NAME" "STATUS" "IP"
  printf "%-15s %-10s %-20s\n" "----" "------" "--"
  
  for ctr in api-server worker postgres; do
    if [ -d "/var/lib/nixos-containers/$ctr" ]; then
      # Check if running by looking for process
      if pgrep -f "systemd-nspawn.*$ctr" > /dev/null; then
        status="${GREEN}running${NC}"
        # Try to get IP
        ip=$(nixos-container run $ctr -- hostname -I 2>/dev/null | awk '{print $1}' || echo "unknown")
      else
        status="${YELLOW}stopped${NC}"
        ip="-"
      fi
      printf "%-15b %-10b %-20b\n" "$ctr" "$status" "$ip"
    else
      printf "%-15s %-10b %-20s\n" "$ctr" "${RED}missing${NC}" "-"
    fi
  done
}

cmd_test() {
  check_root
  log "Testing inter-container networking..."
  
  echo ""
  log "1. Testing api-server → postgres (10.100.3.10:5432)"
  result=$(nixos-container run api-server -- bash -c 'timeout 3 bash -c "cat < /dev/null > /dev/tcp/10.100.3.10/5432" 2>/dev/null && echo "OK" || echo "FAIL"' 2>/dev/null)
  if [ "$result" = "OK" ]; then
    log_ok "api-server can reach postgres"
  else
    log_error "api-server cannot reach postgres"
  fi
  
  echo ""
  log "2. Testing worker → postgres (10.100.3.10:5432)"
  result=$(nixos-container run worker -- bash -c 'timeout 3 bash -c "cat < /dev/null > /dev/tcp/10.100.3.10/5432" 2>/dev/null && echo "OK" || echo "FAIL"' 2>/dev/null)
  if [ "$result" = "OK" ]; then
    log_ok "worker can reach postgres"
  else
    log_error "worker cannot reach postgres"
  fi
  
  echo ""
  log "3. Testing api-server → worker (10.100.2.10:3000)"
  result=$(nixos-container run api-server -- bash -c 'timeout 3 bash -c "cat < /dev/null > /dev/tcp/10.100.2.10/3000" 2>/dev/null && echo "OK" || echo "FAIL"' 2>/dev/null)
  if [ "$result" = "OK" ]; then
    log_ok "api-server can reach worker"
  else
    log_error "api-server cannot reach worker"
  fi
  
  echo ""
  log "4. Testing worker → api-server (10.100.1.10:3000)"
  result=$(nixos-container run worker -- bash -c 'timeout 3 bash -c "cat < /dev/null > /dev/tcp/10.100.1.10/3000" 2>/dev/null && echo "OK" || echo "FAIL"' 2>/dev/null)
  if [ "$result" = "OK" ]; then
    log_ok "worker can reach api-server"
  else
    log_error "worker cannot reach api-server"
  fi
  
  echo ""
  log "5. Testing host → all containers (ping)"
  for ip in 10.100.1.10 10.100.2.10 10.100.3.10; do
    if ping -c 1 -W 2 "$ip" > /dev/null 2>&1; then
      log_ok "Host can ping $ip"
    else
      log_error "Host cannot ping $ip"
    fi
  done
}

cmd_logs() {
  if [ -z "$2" ]; then
    log_error "Usage: $0 logs <container-name>"
    exit 1
  fi
  nixos-container run "$2" -- journalctl -f
}

cmd_shell() {
  if [ -z "$2" ]; then
    log_error "Usage: $0 shell <container-name>"
    exit 1
  fi
  nixos-container root-login "$2"
}

cmd_info() {
  echo ""
  echo "  Nix Native Container Infrastructure"
  echo "  ===================================="
  echo ""
  echo "  Network: $CONTAINER_NETWORK"
  echo "  Bridge:  $BRIDGE_NAME"
  echo "  Gateway: 10.100.0.1"
  echo ""
  echo "  Containers:"
  echo "    api-server  10.100.1.10  HTTP API service"
  echo "    worker      10.100.2.10  Background worker"
  echo "    postgres    10.100.3.10  PostgreSQL database"
  echo ""
  echo "  Commands:"
  echo "    setup    - Setup network and create containers"
  echo "    start    - Start all containers"
  echo "    stop     - Stop all containers"
  echo "    destroy  - Remove all containers"
  echo "    status   - Show container status"
  echo "    test     - Test inter-container networking"
  echo "    logs <c> - Follow container logs"
  echo "    shell <c> - Root shell in container"
  echo ""
}

# Main command dispatcher
case "${1:-info}" in
  build) cmd_build ;;
  setup)
    cmd_build
    cmd_create
    cmd_start
    ;;
  create) cmd_create ;;
  start) cmd_start ;;
  stop) cmd_stop ;;
  destroy) cmd_destroy ;;
  status) cmd_status ;;
  test) cmd_test ;;
  logs) cmd_logs "$@" ;;
  shell) cmd_shell "$@" ;;
  info) cmd_info ;;
  *)
    echo "Unknown command: $1"
    echo ""
    cmd_info
    exit 1
    ;;
esac
