# ncp - Nix Container Platform

A complete platform for deploying and managing NixOS containers via HTTP API and CLI.

## 🏗️ Monorepo Structure

```
ncp/
├── cli/           # Python CLI tool (client-side)
│   ├── ncp/       # CLI package
│   ├── README.md  # CLI documentation
│   └── setup.py   # CLI installation
├── infra/         # NixOS infrastructure (server-side)
│   ├── api/       # FastAPI service
│   ├── host/      # NixOS host configuration
│   ├── containers/# Container definitions
│   └── flake.nix  # Nix flake for deployment
└── README.md      # This file
```

## 🚀 Quick Start

### Server Setup (Hetzner)

The server is already running at `204.168.220.202` with:
- NixOS containers: api-server, worker, postgres
- Nix-Fly API at `https://nix.latha.org/fly`
- Caddy reverse proxy with TLS

```bash
# SSH to server
ssh nixos@204.168.220.202

# View infra code
cd /home/nixos/code/nixos-infra-host  # (or clone from this repo)

# Deploy changes
sudo nixos-rebuild switch --flake .#infra-host
```

### CLI Usage

```bash
# Install CLI locally
cd cli/
pip install -e .

# Or run directly
python -m ncp --help

# Deploy a container
ncp deploy-demo --name my-app --port 8082

# Check status
ncp list
ncp pending

# Apply changes (activate staged containers)
ncp apply
# Note: Currently requires manual nixos-rebuild on host
```

## 📦 Components

### CLI (`cli/`)

Python CLI tool that talks to the Nix-Fly API:
- `ncp list` - Show running containers
- `ncp deploy-demo` - Stage a demo nginx container  
- `ncp pending` - Show staged containers
- `ncp apply` - Activate staged containers
- `ncp logs` - Stream container logs
- `ncp destroy` - Mark container for destruction

See [cli/README.md](cli/README.md) for full CLI documentation.

### Infrastructure (`infra/`)

NixOS infrastructure code:
- **API** (`api/main.py`): FastAPI service for container management
- **Host** (`host/infra-host.nix`): NixOS host configuration
- **Containers** (`containers/`): Container definitions (api-server, worker, postgres)
- **Flake** (`flake.nix`): Complete system definition

See [infra/README.md](infra/README.md) for infrastructure details.

## 🌐 API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/containers` | GET | List all containers |
| `/api/v1/containers` | POST | Stage new container |
| `/api/v1/pending` | GET | List staged changes |
| `/api/v1/apply` | POST | Apply changes (rebuild) |
| `/api/v1/containers/{name}` | GET | Container details |
| `/api/v1/containers/{name}/restart` | POST | Restart container |
| `/api/v1/containers/{name}` | DELETE | Mark for destruction |
| `/api/v1/containers/{name}/logs` | GET | Stream logs |

## 🔗 Access Points

- **HTML UI**: `https://nix.latha.org/fly/docs-ui`
- **API Base**: `https://nix.latha.org/fly`
- **API Server Container**: `https://nix.latha.org/api/`
- **Worker Container**: `https://nix.latha.org/worker/`

## 🛠️ Development Workflow

### Modify Infrastructure

```bash
cd infra/
# Edit host/infra-host.nix, api/main.py, etc.
# Commit and push
git add -A
git commit -m "Update infrastructure"
git push origin main

# Deploy on server (SSH to 204.168.220.202)
sudo nixos-rebuild switch --flake .#infra-host
```

### Modify CLI

```bash
cd cli/
# Edit ncp/cli.py
# Test locally
python -m ncp list

# Commit
git add -A
git commit -m "Update CLI"
git push origin main

# Deploy to server
scp -r cli/ nixos@204.168.220.202:/home/nixos/code/ncp/
```

## 📋 Example: Deploy New Container

```bash
# 1. Stage container via CLI
ncp deploy-demo --name my-nginx --port 8082

# 2. SSH to server and rebuild
ssh nixos@204.168.220.202
sudo nixos-rebuild switch --flake /home/nixos/code/nixos-infra-host#infra-host

# 3. Back on local machine, verify
ncp list
# Should show my-nginx with status "up"

# 4. Test the deployment
curl http://204.168.220.202:8082
```

## 📝 Notes

- **Staging vs Apply**: Creating containers stages config files in `/etc/nix-fly/containers/`. The `apply` command (or manual rebuild) activates them.
- **Dynamic Imports**: The API generates Nix configs, but Nix flakes don't allow runtime imports. The `imports` mechanism is in place but requires the workaround above.
- **IP Allocation**: Auto-assigned from `10.100.10.x` range.
- **Port Forwarding**: Automatic iptables rules created for `host_port` → `container_port`.

## 🔮 Future Improvements

- [ ] Fix dynamic imports to enable `ncp apply` from anywhere
- [ ] Add authentication tokens
- [ ] Support custom NixOS configurations beyond nginx demo
- [ ] Container health checks and auto-restart
- [ ] Rolling deployments with zero downtime
- [ ] Automatic Caddy config for custom domains
- [ ] Multi-host container scheduling
- [ ] Container resource limits (CPU/memory)
- [ ] Volume persistence management

## 📄 License

MIT - This is a personal infrastructure project for learning NixOS and container management.

## 🤝 Contributing

This is primarily a personal project, but feel free to:
- Open issues for bugs or feature requests
- Submit PRs for improvements
- Fork for your own NixOS infrastructure
