# NCP Examples

Example projects showing how to use NCP (Nix Container Platform).

## Project Structure

```
examples/
├── myapp/          # Full-stack app with flake-parts
│   ├── flake.nix   # Defines backend + frontend containers
│   └── README.md
│
└── simple/         # Simple standalone .nix files
    ├── backend-api.nix
    ├── frontend-app.nix
    └── README.md
```

## Quick Start

### Modern Flake-Based Approach (Recommended)

The `myapp/` example shows the modern approach using Nix flakes and flake-parts:

```bash
cd examples/myapp

# View what's defined
nix flake show

# Deploy all containers
ncp deploy --flake

# Or deploy individually
ncp deploy --flake .#backend
ncp deploy --flake .#frontend
```

Benefits:
- **Type-safe**: Uses `lib.mkOption` for config validation
- **Composable**: Share configs between projects
- **Reproducible**: flake.lock pins all dependencies
- **Single source of truth**: Backend + frontend in one file

### Simple Standalone Files

The `simple/` folder contains standalone `.nix` files:

```bash
cd examples/simple

# Deploy using ncp CLI
ncp deploy backend-api
ncp deploy frontend-app
```

Good for:
- Quick testing
- Learning NixOS containers
- Simple single-container deployments

## Choosing an Approach

| Approach | Best For | Complexity |
|----------|----------|------------|
| **Flake-based** | Production apps, multi-container projects | Medium |
| **Simple .nix** | Learning, quick tests, single containers | Low |

## Common Workflow

```bash
# 1. Login (one time)
ncp login

# 2. Deploy
ncp deploy myapp          # simple approach
# or
ncp deploy --flake        # flake approach

# 3. Check status
ncp status
ncp list

# 4. View logs
ncp logs myapp-backend

# 5. Cleanup
ncp destroy myapp-backend
```

See individual project READMEs for details.
