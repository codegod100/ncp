# NCP Container Examples

Example NixOS container configurations for the ncp (Nix Container Platform).

## Quick Start

1. **Get your API token:**
```bash
export TOKEN=$(curl -s -X POST https://nix.latha.org/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"youruser","password":"yourpass"}' \
  | grep -o '"access_token":"[^"]*"' | cut -d'"' -f4)
```

2. **Deploy an example:**
```bash
# Quick deploy both backend + frontend
export TOKEN=your_token_here
./deploy-pair.sh
```

## Examples

### Simple Backend + Frontend Pair

**Files:** `backend-api.nix`, `frontend-app.nix`

A minimal example showing cross-container communication.

**Deploy:**
```bash
# Deploy backend first
python3 deploy.py backend-api.nix my-backend 9001

# Deploy frontend (edit backend-api.nix first to set the URL)
python3 deploy.py frontend-app.nix my-frontend 9002
```

**Access:**
- Backend: `http://YOUR_HOST:9001/` → JSON API with CORS
- Frontend: `http://YOUR_HOST:9002/` → HTML with "Fetch from Backend" button

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
python3 deploy.py todo-api.nix todo-api 9003
python3 deploy.py todo-frontend.nix todo-app 9004
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

## Deployment Scripts

### Option 1: Python helper (`deploy.py`)
```bash
export NCP_TOKEN=your_token
python3 deploy.py backend-api.nix my-api 9001
```

### Option 2: Bash quick deploy (`deploy-pair.sh`)
```bash
export TOKEN=your_token
./deploy-pair.sh  # Deploys example-backend + example-frontend
```

### Option 3: Manual curl with JSON
```bash
# Create payload first
cat > payload.json << 'EOF'
{
  "name": "my-container",
  "host_port": 9001,
  "nix_config": "services.nginx.enable = true; ..."
}
EOF

# Deploy
curl -X POST https://nix.latha.org/api/v1/containers \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d @payload.json
```

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

## More Examples Coming

- [ ] postgres.nix - PostgreSQL database
- [ ] redis.nix - Redis cache
- [ ] nodejs-app.nix - Node.js + npm app
- [ ] python-api.nix - Python Flask/FastAPI
- [ ] static-site.nix - Hugo/Jekyll generated site
