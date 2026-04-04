# Simple NCP Examples

Standalone `.nix` files for quick container deployment.

## Files

| File | Purpose | Port |
|------|---------|------|
| `backend-api.nix` | JSON API with CORS | 9001 |
| `frontend-app.nix` | Frontend that calls backend | 9002 |
| `todo-api.nix` | REST API with multiple endpoints | 9003 |
| `todo-frontend.nix` | Styled todo UI | 9004 |

## Usage

### 1. Login

```bash
ncp login
# Enter username and password
```

### 2. Deploy a container

```bash
# Deploy by service name (looks for {name}.nix)
ncp deploy backend-api
ncp deploy frontend-app
```

The CLI reads `ncp.port` and `ncp.name` from comments in the file:

```nix
# ncp.port = 9001;
# ncp.name = "backend-api";
```

### 3. Test

```bash
# Backend returns JSON
curl http://204.168.220.202:9001/

# Frontend shows HTML with "Fetch from Backend" button
open http://204.168.220.202:9002/
```

### 4. Cleanup

```bash
ncp destroy backend-api
ncp destroy frontend-app
```

## Deploy Script

Use `deploy-pair.sh` to deploy both:

```bash
./deploy-pair.sh
```

## How It Works

1. **Service name** → `backend-api` looks for `backend-api.nix`
2. **Port** → Read from `# ncp.port = 9001;` comment
3. **Name** → Read from `# ncp.name = "backend-api";` comment
4. **Config** → Everything else sent to API

The metadata comments are stripped before sending to the server.
