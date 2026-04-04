# Nix Container Infrastructure

**Part of [ncp - Nix Container Platform](../README.md)**

NixOS infrastructure for running native containers (systemd-nspawn) with private networking. Includes the Nix-Fly API for container management.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         infra-host (VM/Host)                    │
│                    Gateway: 10.100.0.1/16                       │
│                    Bridge: ctrs                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                 Container Subnet 10.100.0.0/16           │   │
│  │                                                         │   │
│  │  ┌──────────────┐      ┌──────────┐      ┌──────────┐   │   │
│  │  │ api-server   │◄────►│  worker  │◄────►│ postgres │   │   │
│  │  │ 10.100.1.10 │      │10.100.2.10      │10.100.3.10   │   │
│  │  │ :3000        │      │ :3000    │      │ :5432    │   │   │
│  │  └──────┬───────┘      └──────────┘      └──────────┘   │   │
│  │         │                                               │   │
│  └─────────┼───────────────────────────────────────────────┘   │
│            │                                                     │
│            ▼                                                     │
│      Host Port 8080                                              │
│      (Forwarded)                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## Quick Start

### Deploy to Hetzner Server

```bash
# SSH to the server
ssh nixos@204.168.220.202

# The infra code is at
cd /home/nixos/code/nixos-infra-host

# Deploy changes
sudo nixos-rebuild switch --flake .#infra-host
```

## Components

### API (`api/`)

FastAPI service at `https://nix.latha.org/fly`:
- Container CRUD operations
- Staging/apply workflow
- Auto IP allocation
- Log streaming

See [api/main.py](api/main.py) for implementation.

### Host (`host/`)

NixOS configuration:
- Container definitions
- Network bridge setup
- Firewall rules
- Caddy reverse proxy

See [host/infra-host.nix](host/infra-host.nix) for configuration.

### Containers (`containers/`)

Individual container definitions:
- `api-server.nix` - HTTP API container
- `worker.nix` - Background worker
- `postgres.nix` - PostgreSQL database

## Network Topology

| Container | IP Address | Host Port | Service |
|-----------|-----------|-----------|---------|
| api-server | 10.100.1.10 | 8080 | HTTP API |
| worker | 10.100.2.10 | 8081 | Health check |
| postgres | 10.100.3.10 | 5432 | PostgreSQL |

## Container Management

Once the host is running, use these commands:

```bash
# Check status of all containers and networking
infra status

# Enter a container shell
infra shell api-server

# View container logs
infra logs api-server

# List running containers
ctrs
```

## Networking Features

### Subnet Routing
All containers are on the `10.100.0.0/16` subnet:
- Full Layer 3 connectivity between containers
- Each container can reach others by IP or hostname
- DNS resolution via dnsmasq on the host

### NAT & External Access
- Containers can reach the internet via NAT through the host
- Host ports forwarded to container services
- Firewall rules automatically managed

### Container-to-Container Communication
```bash
# From api-server container, reach postgres
nixos-container run api-server -- psql -h 10.100.3.10 -U app -d app

# From worker, curl api-server
nixos-container run worker -- curl http://10.100.1.10:3000
```

## API Integration

The Nix-Fly API stages container configs in `/etc/nix-fly/containers/`:

```bash
# Via CLI (from anywhere)
ncp deploy-demo --name my-app --port 8082

# Config is written to
/etc/nix-fly/containers/my-app.nix

# Rebuild to activate
sudo nixos-rebuild switch --flake .#infra-host
```

## Advanced Usage

### Adding a New Container

1. Create container config in `containers/new-service.nix`
2. Add entry to `flake.nix` in the `containerNetwork` attrset
3. Add container definition to `host/infra-host.nix`
4. Rebuild: `sudo nixos-rebuild switch --flake .#infra-host`

### Modifying Network Subnet

Edit in `flake.nix`:
```nix
containerNetwork = {
  subnet = "10.100.0.0/16";
  gateway = "10.100.0.1";
  # ... container IPs
};
```

## Troubleshooting

### Containers can't reach each other
```bash
# Check firewall rules
sudo iptables -L -v -n
sudo iptables -t nat -L -v -n

# Verify bridge is up
ip link show ctrs

# Check IP forwarding
cat /proc/sys/net/ipv4/ip_forward  # Should be 1
```

### Container won't start
```bash
# Check systemd status
systemctl status container@api-server

# View container logs
nixos-container run api-server -- journalctl -xe
```

## Production Considerations

1. **Secrets**: Use `agenix` or `sops-nix` for database passwords and API keys
2. **TLS**: Caddy handles TLS with Let's Encrypt
3. **Monitoring**: Add `prometheus` + `grafana` for metrics
4. **Backups**: PostgreSQL data in `/var/lib/containers/postgres/var/lib/postgresql/`
5. **Resource Limits**: Add systemd resource controls (CPU, memory limits)

## Development

From the monorepo root:

```bash
# Edit infrastructure
cd infra/
# Modify api/main.py, host/infra-host.nix, etc.

# Deploy
git add -A
git commit -m "Update infra"
scp -r infra/ nixos@204.168.220.202:/home/nixos/code/nixos-infra-host/
ssh nixos@204.168.220.202 "cd /home/nixos/code/nixos-infra-host && sudo nixos-rebuild switch --flake .#infra-host"
```

See the main [README.md](../README.md) for full platform documentation.

## Resources

- [NixOS Containers](https://nixos.org/manual/nixos/stable/#sec-nixos-containers)
- [systemd-nspawn](https://systemd.io/CONTAINER_INTERFACE/)
- [NixOS Networking](https://nixos.org/manual/nixos/stable/#sec-networking)
