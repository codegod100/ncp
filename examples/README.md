# NCP Container Examples

Example NixOS container configurations for the ncp (Nix Container Platform).

## Quick Start

1. **Login with ncp CLI:**
```bash
ncp login --server https://nix.latha.org
# Enter your username and password
```

2. **Deploy an example:**
```bash
ncp deploy --name my-backend --port 9001 --config backend-api.nix
```

## Examples

### Simple Backend + Frontend Pair

**Files:** `backend-api.nix`, `frontend-app.nix`

A minimal example showing cross-container communication.

**Deploy:**
```bash
# Deploy backend
ncp deploy --name my-backend --port 9001 --config backend-api.nix

# Edit frontend-app.nix to set your backend URL, then:
ncp deploy --name my-frontend --port 9002 --config frontend-app.nix
```

**Access:**
- Backend: `http://YOUR_HOST:9001/` → JSON API with CORS
- Frontend: `http://YOUR_HOST:9002/` → HTML with "Fetch from Backend" button

**One-liner for both:**
```bash
export NCP_TOKEN=$(ncp token)  # or login first
./deploy-pair.sh
```

---

### Todo App (Full-Stack)

**Files:** `todo-api.nix`, `todo-frontend.nix`

A more polished example with a styled todo interface.

**Features:**
- Backend: REST API with `/todos`, `/health` endpoints
- Frontend: Modern UI with gradient, styled list, interactive
- Demonstrates proper CORS for PUT/POST methods

**Deploy:**
```bash
# 1. Edit todo-frontend.nix: Set backendUrl to your backend IP:port
# 2. Deploy both
ncp deploy --name todo-api --port 9003 --config todo-api.nix
ncp deploy --name todo-app --port 9004 --config todo-frontend.nix
```

---

### Individual Components

#### backend-api.nix
Simple JSON API server with CORS headers.

**What it does:**
- Nginx serving JSON
- `Access-Control-Allow-Origin: *` (allows any frontend to fetch)
- Response: `{"message": "Hello from backend", "service": "api", "version": "1.0"}`

#### frontend-app.nix
Generic frontend that can fetch from any backend.

**What it does:**
- Creates HTML file via activation script
- JavaScript `fetch()` to call backend
- Two buttons: "Fetch from Backend" and "Clear"
- Displays JSON response formatted

**To customize:** Edit the `backendUrl` variable in the .nix file

---

## How It Works

### Networking Between Containers

```
┌─────────────────┐      ┌─────────────────┐
│   Frontend      │      │    Backend      │
│   (10.100.1.2)  │──────│   (10.100.1.1)  │
│                 │      │                 │
│  JavaScript     │fetch │  JSON API       │
│  fetch()        │──────│  + CORS         │
│                 │      │                 │
└─────────────────┘      └─────────────────┘
         │                        │
         └──────────┬───────────┘
                    │
              Host (nix.latha.org)
              proxy_arp enabled
              Port forwarding via iptables
```

**Two ways containers communicate:**

1. **External (through host):**
   - `http://204.168.220.202:9101/`
   - Goes through host's port forwarding (iptables DNAT)
   - Works from browser (cross-origin)
   - **Requires CORS headers on backend**

2. **Internal (container-to-container):**
   - `http://10.100.1.1:80/`
   - Direct routing via container subnet (10.100.0.0/16)
   - Host has `proxy_arp` enabled for routing
   - **Doesn't require CORS** (same-origin in browser context)

### Key NixOS Patterns Used

| Pattern | Example | Purpose |
|---------|---------|---------|
| `services.nginx.enable` | All examples | Web server |
| `system.activationScripts` | `frontend-app.nix` | Create files at boot |
| `pkgs.writeText` | `todo-frontend.nix` | Generate config files |
| `networking.firewall` | All examples | Open port 80 |
| CORS headers | `backend-api.nix` | Cross-origin requests |

## Deployment Methods

### Option 1: ncp CLI (Recommended)
```bash
# Login once
ncp login --server https://nix.latha.org

# Deploy
ncp deploy --name my-container --port 9001 --config backend-api.nix

# List your containers
ncp list

# Destroy
ncp destroy my-container
```

### Option 2: Bash quick deploy (`deploy-pair.sh`)
```bash
# Make sure you're logged in first
ncp login --server https://nix.latha.org

# Deploy both backend and frontend
./deploy-pair.sh
```

### Option 3: Manual curl with JSON
```bash
# Get token
TOKEN=$(ncp token)

# Deploy via curl
curl -X POST https://nix.latha.org/api/v1/containers \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d @backend-api.json
```

## ncp CLI Commands

| Command | Description |
|---------|-------------|
| `ncp login --server URL` | Authenticate and save token |
| `ncp token` | Show current auth token |
| `ncp deploy --name X --port Y --config FILE.nix` | Deploy container |
| `ncp list` | List your containers |
| `ncp destroy NAME` | Remove container |
| `ncp logs NAME` | View container logs |

## Troubleshooting

**CORS errors in browser:**
- Backend needs: `add_header Access-Control-Allow-Origin * always;`
- Check backend headers: `curl -I http://HOST:PORT/`

**Can't fetch from backend:**
- Verify backend is running: `curl http://HOST:PORT/`
- Check frontend's `backendUrl` matches actual backend
- Ensure `proxy_arp` is enabled on host

**Container won't start:**
- Check config syntax: `nix-instantiate --eval myconfig.nix`
- Check firewall port is open: `networking.firewall.allowedTCPPorts = [ 80 ];`
- View logs: `ncp logs my-container`

**ncp CLI not found:**
- Install from repo: `cd /path/to/ncp && pip install -e cli/`
- Or use nix develop: `nix develop --command ncp --help`

## More Examples Coming

- [ ] postgres.nix - PostgreSQL database
- [ ] redis.nix - Redis cache
- [ ] nodejs-app.nix - Node.js + npm app
- [ ] python-api.nix - Python Flask/FastAPI
- [ ] static-site.nix - Hugo/Jekyll generated site
