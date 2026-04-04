#!/usr/bin/env bash
# Run NixOS containers on non-NixOS Linux using systemd-nspawn
# Based on: https://gist.github.com/Thesola10/999b4e6d1eca84b9ce1d380ced2934dd

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BRIDGE_NAME="ctrs"
CONTAINER_NETWORK="10.100.0.0/16"

# Container IPs
declare -A CTR_IPS=(
  [api-server]="10.100.1.10"
  [worker]="10.100.2.10"
  [postgres]="10.100.3.10"
)

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log() { echo -e "${BLUE}[nspawn]${NC} $1"; }
log_ok() { echo -e "${GREEN}[nspawn]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[nspawn]${NC} $1"; }
log_error() { echo -e "${RED}[nspawn]${NC} $1"; }

check_root() {
  if [ "$EUID" -ne 0 ]; then
    log_error "This command requires root privileges"
    exit 1
  fi
}

check_deps() {
  if ! command -v systemd-nspawn &> /dev/null; then
    log_error "systemd-nspawn not found!"
    echo ""
    echo "On Ubuntu/Debian, install it with:"
    echo "  sudo apt-get install systemd-container"
    echo ""
    echo "On other distros:"
    echo "  sudo pacman -S systemd (Arch)"
    echo "  sudo dnf install systemd-container (Fedora)"
    exit 1
  fi
  
  if ! command -v machinectl &> /dev/null; then
    log_error "machinectl not found! Install systemd-container package."
    exit 1
  fi
}

# Setup a minimal OS root directory for the container
cmd_setup_overlay() {
  local container=$1
  local overlay_dir="/var/lib/nixos-containers/$container"
  
  # Create the directory structure systemd-nspawn expects
  # Do this step by step to avoid issues
  for dir in bin sbin etc lib lib64 proc sys dev run tmp root nix var usr; do
    mkdir -p "$overlay_dir/$dir"
  done
  mkdir -p "$overlay_dir/nix/store"
  mkdir -p "$overlay_dir/nix/var/nix/db"
  mkdir -p "$overlay_dir/usr/lib/systemd"
  
  # Create minimal /etc/os-release using echo (more reliable than heredoc in function)
  mkdir -p "$overlay_dir/etc"
  printf 'NAME="NixOS"\nID=nixos\nPRETTY_NAME="NixOS (Container)"\nVERSION_ID="24.11"\nHOME_URL="https://nixos.org"\n' > "$overlay_dir/etc/os-release"

  # Create /etc/machine-id (will be overwritten)
  touch "$overlay_dir/etc/machine-id"
  
  # Create minimal skeleton files
  touch "$overlay_dir/etc/resolv.conf"
  
  # Create symlinks for systemd (NixOS uses /run/current-system/sw/bin/systemd)
  ln -sf "/run/current-system/sw/bin/systemd" "$overlay_dir/usr/lib/systemd/systemd" 2>/dev/null || true
  
  # Also create standard init symlinks
  ln -sf "/run/current-system/init" "$overlay_dir/sbin/init" 2>/dev/null || true
  ln -sf "/run/current-system/init" "$overlay_dir/init" 2>/dev/null || true
  
  echo "$overlay_dir"
}

# Build a NixOS system closure using the flake
cmd_build_container() {
  local name=$1
  log "Building $name container from flake..."
  
  nix build --extra-experimental-features "nix-command flakes" \
    --out-link "$SCRIPT_DIR/result-$name" \
    ".#nixosConfigurations.container-$name.config.system.build.toplevel"
  
  log_ok "$name built: $SCRIPT_DIR/result-$name"
}

# Setup network bridge
cmd_network_setup() {
  check_root
  
  if ! ip link show "$BRIDGE_NAME" 2>/dev/null; then
    log "Creating bridge $BRIDGE_NAME..."
    ip link add "$BRIDGE_NAME" type bridge
    ip addr add "10.100.0.1/16" dev "$BRIDGE_NAME"
    ip link set "$BRIDGE_NAME" up
    log_ok "Bridge created"
  fi
  
  # Enable IP forwarding
  echo 1 > /proc/sys/net/ipv4/ip_forward
  
  # NAT for containers to reach internet
  if ! iptables -t nat -C POSTROUTING -s "$CONTAINER_NETWORK" ! -d "$CONTAINER_NETWORK" -j MASQUERADE 2>/dev/null; then
    iptables -t nat -A POSTROUTING -s "$CONTAINER_NETWORK" ! -d "$CONTAINER_NETWORK" -j MASQUERADE
    log_ok "NAT enabled"
  fi
  
  # Allow forwarding
  iptables -A FORWARD -i "$BRIDGE_NAME" -o "$BRIDGE_NAME" -j ACCEPT 2>/dev/null || true
}

# Start a container
cmd_start_container() {
  local name=$1
  check_root
  check_deps
  
  # Check if already running
  if machinectl show "$name" 2>/dev/null | grep -q "State=running"; then
    log_warn "$name is already running"
    return
  fi
  
  log "Starting $name on ${CTR_IPS[$name]}..."
  
  # Build if not exists
  if [ ! -L "$SCRIPT_DIR/result-$name" ]; then
    cmd_build_container "$name"
  fi
  
  local system_path=$(readlink -f "$SCRIPT_DIR/result-$name")
  local overlay_dir="/var/lib/nixos-containers/$name"
  
  # Create directory structure explicitly
  log "Creating container root at $overlay_dir..."
  rm -rf "$overlay_dir"  # Clean start
  mkdir -p "$overlay_dir"/{bin,sbin,etc,lib,lib64,proc,sys,dev,run,tmp,root,nix,var,usr}
  mkdir -p "$overlay_dir/nix/store" "$overlay_dir/nix/var/nix/db"
  mkdir -p "$overlay_dir/usr/lib/systemd"
  
  # Create os-release
  echo 'NAME="NixOS"' > "$overlay_dir/etc/os-release"
  echo 'ID=nixos' >> "$overlay_dir/etc/os-release"
  echo 'PRETTY_NAME="NixOS (Container)"' >> "$overlay_dir/etc/os-release"
  echo 'VERSION_ID="24.11"' >> "$overlay_dir/etc/os-release"
  echo 'HOME_URL="https://nixos.org"' >> "$overlay_dir/etc/os-release"
  
  # Create other required files
  touch "$overlay_dir/etc/machine-id"
  touch "$overlay_dir/etc/resolv.conf"
  
  # Create init symlinks
  ln -sf "/run/current-system/init" "$overlay_dir/sbin/init" 2>/dev/null || true
  ln -sf "/run/current-system/init" "$overlay_dir/init" 2>/dev/null || true
  ln -sf "/run/current-system/sw/bin/systemd" "$overlay_dir/usr/lib/systemd/systemd" 2>/dev/null || true
  
  log_ok "Container root created"
  
  # Start with systemd-nspawn WITHOUT --boot
  # Run the NixOS activation and init directly
  # This avoids the cgroup detection issue
  systemd-nspawn \
    --machine="$name" \
    --directory="$overlay_dir" \
    --network-bridge="$BRIDGE_NAME" \
    --bind="$system_path:/run/current-system" \
    --bind=/nix/store:/nix/store \
    --bind=/sys/fs/cgroup:/sys/fs/cgroup \
    --capability=all \
    /run/current-system/init &
  
  log_ok "$name started (PID: $!)"
  
  # Give it a moment
  sleep 3
}

# Commands
cmd_build() {
  for ctr in api-server worker postgres; do
    cmd_build_container "$ctr"
  done
  log_ok "All containers built!"
}

cmd_setup() {
  check_root
  check_deps
  cmd_network_setup
  cmd_build
  
  log "Starting all containers..."
  for ctr in api-server worker postgres; do
    cmd_start_container "$ctr"
    sleep 2
  done
  
  cmd_status
}

cmd_start() {
  check_root
  check_deps
  for ctr in api-server worker postgres; do
    cmd_start_container "$ctr"
  done
}

cmd_stop() {
  check_root
  log "Stopping containers..."
  for ctr in api-server worker postgres; do
    machinectl poweroff "$ctr" 2>/dev/null || true
    machinectl terminate "$ctr" 2>/dev/null || true
  done
}

cmd_status() {
  log "Container status:"
  machinectl list 2>/dev/null || echo "No running machines"
  
  echo ""
  log "Bridge status:"
  ip addr show "$BRIDGE_NAME" 2>/dev/null | grep "inet\|state" || echo "Bridge not found"
}

cmd_test() {
  check_root
  check_deps
  log "Testing inter-container connectivity..."
  
  # Wait for services
  sleep 5
  
  log "api-server -> postgres (10.100.3.10:5432)"
  machinectl shell api-server /bin/sh -c "timeout 3 bash -c 'cat < /dev/null > /dev/tcp/10.100.3.10/5432'" 2>/dev/null && log_ok "Reachable" || log_error "Unreachable"
  
  log "worker -> postgres (10.100.3.10:5432)"
  machinectl shell worker /bin/sh -c "timeout 3 bash -c 'cat < /dev/null > /dev/tcp/10.100.3.10/5432'" 2>/dev/null && log_ok "Reachable" || log_error "Unreachable"
  
  log "api-server -> worker (10.100.2.10:3000)"
  machinectl shell api-server /bin/sh -c "timeout 3 bash -c 'cat < /dev/null > /dev/tcp/10.100.2.10/3000'" 2>/dev/null && log_ok "Reachable" || log_error "Unreachable"
}

cmd_shell() {
  if [ -z "$2" ]; then
    log_error "Usage: $0 shell <container>"
    exit 1
  fi
  machinectl shell "$2"
}

cmd_logs() {
  if [ -z "$2" ]; then
    log_error "Usage: $0 logs <container>"
    exit 1
  fi
  journalctl -M "$2" -f
}

cmd_info() {
  cat <<EOF

NixOS Containers via systemd-nspawn (Ubuntu-compatible)
========================================================

Network: $CONTAINER_NETWORK
Bridge:  $BRIDGE_NAME
Gateway: 10.100.0.1

Containers:
  api-server  ${CTR_IPS[api-server]}  HTTP API
  worker      ${CTR_IPS[worker]}      Background worker  
  postgres    ${CTR_IPS[postgres]}    PostgreSQL

Commands:
  setup   - Build and start everything
  build   - Build container closures only
  start   - Start containers
  stop    - Stop containers
  status  - Show status
  test    - Test networking
  shell <c> - Enter container
  logs <c>  - View container logs

EOF
}

# Main
case "${1:-info}" in
  setup) cmd_setup ;;
  build) cmd_build ;;
  start) cmd_start ;;
  stop) cmd_stop ;;
  status) cmd_status ;;
  test) cmd_test ;;
  shell) cmd_shell "$@" ;;
  logs) cmd_logs "$@" ;;
  info) cmd_info ;;
  *)
    echo "Unknown command: $1"
    cmd_info
    exit 1
    ;;
esac
