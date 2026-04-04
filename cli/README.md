# ncp CLI

Python CLI tool for the Nix Container Platform.

## Installation

```bash
# From the monorepo root
cd cli/
pip install -e .

# Or run without installing
python -m ncp --help
```

## Configuration

Environment variables:
- `NCP_API_URL`: API endpoint (default: https://nix.latha.org/fly)
- `NCP_TOKEN`: Authentication token (if required)

## Usage

```bash
# Show help
ncp --help

# List all containers
ncp list

# Deploy a demo nginx container
ncp deploy-demo --name my-app --port 8082

# Quick deploy (demo-web on port 8082)
ncp demo

# Show container details
ncp info my-app

# Stream container logs
ncp logs my-app --follow

# Restart a container
ncp restart my-app

# Mark container for destruction
ncp destroy my-app

# Check staged containers
ncp pending

# Apply staged changes (activates containers)
ncp apply
```

## Architecture

The CLI is a thin client that talks to the Nix-Fly API:

```
ncp CLI → HTTPS → nix.latha.org/fly → Nix-Fly API → /etc/nix-fly/containers/
                                                      ↓
                                            nixos-rebuild switch
                                                      ↓
                                            Running NixOS Containers
```

## Known Limitations

**`ncp apply` requires host access** - Due to Nix flake purity, the API cannot trigger rebuilds that include runtime-generated configs. Workaround:

```bash
# After staging with ncp deploy-demo:
ncp pending  # Shows staged containers

# SSH to host and rebuild
ssh nixos@204.168.220.202 \
  "cd /home/nixos/code/nixos-infra-host && \
   sudo nixos-rebuild switch --flake .#infra-host"

# Verify
ncp list
```

## Demo Container

The `deploy-demo` command creates:
- NixOS container with nginx
- Port 80 internally
- Mapped to your specified external port
- Accessible at `http://204.168.220.202:PORT`

## Development

```bash
# Edit cli/ncp/cli.py
# Test changes
python -m ncp list

# Deploy to server
scp -r cli/ nixos@204.168.220.202:/home/nixos/code/ncp/
```

See the main [README.md](../README.md) for full platform documentation.
