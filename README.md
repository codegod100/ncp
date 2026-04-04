# ncp - Nix Container Platform

A CLI tool for deploying and managing NixOS containers via the Nix-Fly API.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  ncp CLI (Your Machine)                                     │
│  └─ Deploys containers via HTTPS API                        │
└────────────────────┬──────────────────────────────────────────┘
                     │
          ┌──────────▼──────────┐
          │  nix.latha.org:443  │
          │  Caddy Reverse Proxy │
          └──────────┬──────────┘
                     │
┌────────────────────▼──────────────────────────────────────────┐
│  Nix-Fly API (on Hetzner host)                              │
│  ├─ Stages container configs to /etc/nix-fly/containers/   │
│  └─ Triggers nixos-rebuild (manual or API-driven)           │
└────────────────────┬──────────────────────────────────────────┘
                     │
┌────────────────────▼──────────────────────────────────────────┐
│  NixOS Containers (Declarative)                               │
│  ├─ api-server (10.100.1.10)                                │
│  ├─ worker (10.100.2.10)                                    │
│  ├─ postgres (10.100.3.10)                                  │
│  └─ Your new containers (API-created)                       │
└───────────────────────────────────────────────────────────────┘
```

## Installation

```bash
cd /home/nandi/code/ncp  # or wherever you cloned it
pip install -e .
# or run directly:
python -m ncp --help
```

On the server:
```bash
cd /home/nixos/code/ncp
python3 -m ncp --help
```

## Usage

### Basic Workflow

```bash
# 1. List all containers
ncp list

# 2. Stage a new container (creates config, doesn't activate)
ncp deploy-demo --name my-webapp --port 8082

# 3. Check pending changes
ncp pending

# 4. Apply changes (activates staged containers)
ncp apply

# 5. View running containers  
ncp list
```

### Container Management

```bash
# Quick deploy demo container
ncp demo

# Show container info
ncp info my-webapp

# Stream logs
ncp logs my-webapp --follow

# Restart container
ncp restart my-webapp

# Mark for destruction
ncp destroy my-webapp

# Complete destruction
ncp apply
```

## Known Limitations

**The `ncp apply` command currently requires manual intervention.**

Because Nix flakes are pure and don't allow runtime-modified imports, the API cannot directly trigger a rebuild that includes staged containers. 

### Workaround

After staging containers with `ncp deploy-demo`, run the rebuild manually on the host:

```bash
ssh nixos@204.168.220.202 \
  "cd /home/nixos/code/nixos-infra-host && \
   sudo nixos-rebuild switch --flake .#infra-host"
```

Or from the host itself:
```bash
ncp deploy-demo --name my-app --port 8082
sudo nixos-rebuild switch --flake /home/nixos/code/nixos-infra-host#infra-host
ncp list
```

## Environment Variables

- `NCP_API_URL` - API endpoint (default: https://nix.latha.org/fly)
- `NCP_TOKEN` - API authentication token (if required)

## Demo Container

The `deploy-demo` command creates a simple nginx container:
- NixOS configuration with nginx enabled
- Port 80 exposed internally
- Mapped to external port (default 8082)
- Accessible at http://204.168.220.202:PORT

## API Endpoints

The CLI talks to these HTTPS endpoints:

| Endpoint | Description |
|----------|-------------|
| `GET /api/v1/containers` | List containers |
| `POST /api/v1/containers` | Stage new container |
| `GET /api/v1/pending` | List staged changes |
| `POST /api/v1/apply` | Apply changes (rebuild) |
| `POST /api/v1/containers/{name}/restart` | Restart container |
| `DELETE /api/v1/containers/{name}` | Mark for destruction |
| `GET /api/v1/containers/{name}/logs` | Stream logs |

## Future Improvements

- [ ] Fix `ncp apply` to work remotely (modify flake files directly)
- [ ] Add authentication tokens
- [ ] Support custom NixOS configurations
- [ ] Container health checks
- [ ] Rolling deployments
- [ ] Domain/Caddy integration for automatic HTTPS
