# Flake-Based Container Definitions

NCP supports defining containers as flake parts using the Nix module system.

## Architecture

```
my-project/
├── flake.nix          # Defines backend + frontend containers
├── flake.lock
└── ...
```

## Usage

### 1. Create a flake with NCP containers

```nix
# flake.nix
{
  description = "My Full-Stack App";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    ncp.url = "github:codegod100/ncp";
    flake-parts.url = "github:hercules-ci/flake-parts";
  };

  outputs = inputs@{ self, nixpkgs, ncp, flake-parts, ... }:
    flake-parts.lib.mkFlake { inherit inputs; } {
      imports = [ ncp.flakeModule ];
      systems = [ "x86_64-linux" ];

      ncp.containers = {
        backend = {
          name = "myapp-backend";
          port = 9001;
          
          config = { config, pkgs, lib, ... }: {
            services.nginx = {
              enable = true;
              virtualHosts.default = {
                default = true;
                locations."/".return = ''200 '{"msg":"Hello"}'';
              };
            };
            networking.firewall.allowedTCPPorts = [ 80 ];
          };
        };

        frontend = {
          name = "myapp-frontend";
          port = 9002;
          
          config = { config, pkgs, lib, ... }: {
            services.nginx.enable = true;
            # ... frontend config
          };
        };
      };
    };
}
```

### 2. Deploy with ncp CLI

```bash
# Deploy all containers defined in flake.ncp.containers
ncp deploy --flake

# Or deploy specific container
ncp deploy --flake .#backend
ncp deploy --flake .#frontend
```

## Benefits

1. **Single source of truth**: Backend + frontend defined in one flake
2. **Type safety**: `lib.mkOption` validates your config
3. **Composition**: Import other flakes, share configs
4. **Reproducibility**: flake.lock pins all dependencies

## Without Flake-Parts

You can also use the NCP module directly:

```nix
{
  inputs.ncp.url = "github:codegod100/ncp";
  
  outputs = { self, nixpkgs, ncp }:
    let
      system = "x86_64-linux";
      pkgs = nixpkgs.legacyPackages.${system};
      
      # Use ncp module to define containers
      containerModule = { config, ... }: {
        imports = [ ncp.flakeModule ];
        ncp.containers.backend = { ... };
      };
    in {
      # ...
    };
}
```

## Development Workflow

```bash
# 1. Create flake with your containers
cat > flake.nix << 'EOF'
{ inputs.ncp.url = "github:codegod100/ncp"; ... }
EOF

# 2. Test locally
nix build .#ncp-backend  # View generated config

# 3. Deploy
ncp login
ncp deploy --flake
```

## Reference

### `ncp.containers.<name>` options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `name` | str | required | Container name |
| `port` | int | required | External host port |
| `containerPort` | int | 80 | Internal container port |
| `config` | function | required | NixOS config function |

### CLI integration

The CLI will:
1. Read the flake
2. Extract `ncp.containers` definitions
3. Generate the NixOS config for each
4. Deploy to the NCP server

Coming soon: `ncp deploy --flake` support
