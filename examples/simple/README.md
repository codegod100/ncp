# Simple NCP Example

A minimal NCP project showing flake-based container deployment.

## Structure

```
simple/
├── flake.nix      # Defines backend + frontend containers
└── README.md      # This file
```

## Deploy

```bash
# Login to NCP
ncp login

# Deploy the entire project
ncp deploy simple
```

This deploys both containers defined in `flake.nix`:
- `simple-backend` (port 9001)
- `simple-frontend` (port 9002)

## Test

```bash
# Backend API
curl http://204.168.220.202:9001/

# Frontend (open in browser)
open http://204.168.220.202:9002/
```

## How It Works

1. **flake.nix** defines containers in `ncp.containers`
2. **CLI** sends the entire project to server
3. **Server** evaluates flake and creates containers
4. **Containers** get names like `simple-backend`, `simple-frontend`

## Flake Structure

```nix
{
  ncp.containers = {
    backend = {
      port = 9001;           # External port
      containerPort = 80;    # Internal port (default: 80)
      config = { ... }: {    # NixOS configuration
        services.nginx.enable = true;
        # ...
      };
    };
    
    frontend = {
      port = 9002;
      config = { ... }: {
        # ... frontend config
      };
    };
  };
}
```

## Cleanup

```bash
ncp destroy simple-backend
ncp destroy simple-frontend
```
