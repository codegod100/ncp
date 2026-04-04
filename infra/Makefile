# Nix Native Container Infrastructure Makefile

.PHONY: help build setup start stop destroy status test shell logs vm setup-nspawn

# Nix experimental features
NIX_FLAGS = --extra-experimental-features "nix-command flakes"

help: ## Show this help message
	@echo "Nix Native Container Infrastructure"
	@echo "===================================="
	@echo ""
	@echo "For NixOS hosts:"
	@echo "  make setup-nixos   - Use nixos-container (best)"
	@echo ""
	@echo "For non-NixOS (Ubuntu/etc):"
	@echo "  make setup-nspawn  - Use systemd-nspawn"
	@echo ""
	@echo "Available commands:"
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  %-15s %s\n", $$1, $$2}' $(MAKEFILE_LIST)
	@echo ""
	@echo "Network: 10.100.0.0/16"
	@echo "Containers: api-server (10.100.1.10), worker (10.100.2.10), postgres (10.100.3.10)"

# NixOS-native (requires NixOS)
setup-nixos: ## Setup using nixos-container (NixOS only)
	@echo "Using nixos-container (requires NixOS)..."
	sudo ./run.sh setup

# Ubuntu/non-NixOS compatible
setup-nspawn: ## Setup using systemd-nspawn (works on any Linux)
	@echo "Using systemd-nspawn (Ubuntu compatible)..."
	sudo ./run-nspawn.sh setup

build: ## Build all container closures
	nix build $(NIX_FLAGS) \
		.#nixosConfigurations.container-api-server.config.system.build.toplevel \
		.#nixosConfigurations.container-worker.config.system.build.toplevel \
		.#nixosConfigurations.container-postgres.config.system.build.toplevel

start: ## Start all containers (requires sudo)
	sudo ./run-nspawn.sh start

stop: ## Stop all containers (requires sudo)
	sudo ./run-nspawn.sh stop

status: ## Show container status
	sudo ./run-nspawn.sh status

test: ## Test inter-container networking
	sudo ./run-nspawn.sh test

shell-%: ## Open root shell in container (e.g., make shell-api-server)
	sudo ./run-nspawn.sh shell $*

logs-%: ## Follow logs in container (e.g., make logs-api-server)
	sudo ./run-nspawn.sh logs $*

vm: ## Run the infra host in a QEMU VM
	nix run $(NIX_FLAGS) .#nixosConfigurations.infra-host.config.system.build.vm

check: ## Check the flake for errors
	nix flake check $(NIX_FLAGS)

fmt: ## Format all nix files
	nix fmt $(NIX_FLAGS)

develop: ## Enter development shell
	nix develop $(NIX_FLAGS)

net-debug: ## Show network debugging info
	@echo "=== Bridge Status ==="
	@ip addr show ctrs 2>/dev/null || echo "Bridge 'ctrs' not found"
	@echo ""
	@echo "=== IP Forwarding ==="
	@cat /proc/sys/net/ipv4/ip_forward
	@echo ""
	@echo "=== NAT Rules ==="
	@sudo iptables -t nat -L POSTROUTING -v -n 2>/dev/null | grep -v "0 0" || echo "No NAT rules"
	@echo ""
	@echo "=== Container Processes ==="
	@pgrep -a systemd-nspawn 2>/dev/null || echo "No running containers"
