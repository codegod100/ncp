#!/usr/bin/env python3
"""
NCP Container Management API - With User Authentication
"""

import subprocess
import json
import os
import re
import tempfile
import shutil
import hashlib
import secrets
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.responses import HTMLResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import uvicorn
from datetime import datetime, timedelta

# JWT support
try:
    import jwt
    JWT_AVAILABLE = True
except ImportError:
    JWT_AVAILABLE = False
    print("Warning: PyJWT not available, using simple token fallback")

app = FastAPI(title="NCP API", version="3.0.0")
security = HTTPBearer(auto_error=False)

# Data storage
DATA_DIR = "/var/lib/ncp"
CONTAINERS_DB_FILE = f"{DATA_DIR}/containers.json"
USERS_DB_FILE = f"{DATA_DIR}/users.json"

NETWORK_CONFIG = {
    "subnet": "10.100.0.0/16",
    "gateway": "10.100.0.1",
}

# JWT settings
JWT_SECRET = os.environ.get("NCP_JWT_SECRET", secrets.token_hex(32))
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 24

# Models
class UserRegister(BaseModel):
    username: str
    password: str
    email: Optional[str] = None

class UserLogin(BaseModel):
    username: str
    password: str

class UserInfo(BaseModel):
    username: str
    email: Optional[str] = None
    created_at: str

class ContainerSpec(BaseModel):
    name: str
    description: Optional[str] = None
    ip: Optional[str] = None
    host_port: Optional[int] = None
    container_port: int = 80
    nix_config: str
    auto_start: bool = True

class ContainerInfo(BaseModel):
    name: str
    status: str
    ip: Optional[str] = None
    host_port: Optional[int] = None
    created_at: str
    owner: Optional[str] = None

# Database functions
def load_db(filepath: str) -> Dict[str, Any]:
    if os.path.exists(filepath):
        try:
            with open(filepath, 'r') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_db(filepath: str, db: Dict[str, Any]):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(filepath, 'w') as f:
        json.dump(db, f, indent=2)

def hash_password(password: str) -> str:
    """Hash a password using SHA-256 with salt"""
    salt = secrets.token_hex(16)
    pwdhash = hashlib.sha256((password + salt).encode()).hexdigest()
    return f"{salt}${pwdhash}"

def verify_password(password: str, hashed: str) -> bool:
    """Verify a password against its hash"""
    try:
        salt, stored_hash = hashed.split('$')
        pwdhash = hashlib.sha256((password + salt).encode()).hexdigest()
        return pwdhash == stored_hash
    except:
        return False

def create_token(username: str) -> str:
    """Create JWT token for user"""
    if JWT_AVAILABLE:
        payload = {
            "sub": username,
            "exp": datetime.utcnow() + timedelta(hours=JWT_EXPIRATION_HOURS),
            "iat": datetime.utcnow(),
        }
        return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    else:
        # Simple fallback token
        return f"ncp_{username}_{secrets.token_hex(16)}"

def verify_token(token: str) -> Optional[str]:
    """Verify token and return username"""
    if not token:
        return None
    
    if JWT_AVAILABLE:
        try:
            # Remove Bearer prefix if present
            if token.startswith("Bearer "):
                token = token[7:]
            payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            return payload.get("sub")
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Token expired")
        except jwt.InvalidTokenError:
            raise HTTPException(status_code=401, detail="Invalid token")
    else:
        # Simple fallback
        if token.startswith("ncp_"):
            parts = token.split("_")
            if len(parts) >= 2:
                return parts[1]
        return None

# Load databases
containers_db: Dict[str, Any] = load_db(CONTAINERS_DB_FILE)
users_db: Dict[str, Any] = load_db(USERS_DB_FILE)

# Auth dependency
async def get_current_user(authorization: Optional[str] = Header(None)) -> Optional[str]:
    """Extract username from Authorization header"""
    if not authorization:
        return None
    return verify_token(authorization)

async def require_user(authorization: Optional[str] = Header(None)) -> str:
    """Require authentication, raise 401 if missing"""
    user = await get_current_user(authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user

def check_container_access(name: str, username: str):
    """Check if user owns the container or is admin"""
    info = containers_db.get(name, {})
    owner = info.get("owner")
    
    # Admin can access all
    if username == "admin":
        return True
    
    # Owner can access their own
    if owner == username:
        return True
    
    # No owner set - first access claims it (for migration)
    if not owner:
        containers_db[name]["owner"] = username
        save_db(CONTAINERS_DB_FILE, containers_db)
        return True
    
    raise HTTPException(status_code=403, detail=f"Access denied: container '{name}' is owned by '{owner}'")

# Command utilities
def run_cmd(cmd: List[str], capture=True, timeout=300, cwd: Optional[str] = None) -> tuple:
    try:
        if capture:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=cwd)
            return result.stdout, result.stderr, result.returncode
        else:
            result = subprocess.run(cmd, timeout=timeout, cwd=cwd)
            return "", "", result.returncode
    except subprocess.TimeoutExpired:
        return "", "Command timed out", 1
    except Exception as e:
        return "", str(e), 1

def get_container_status(name: str) -> str:
    stdout, stderr, rc = run_cmd(["nixos-container", "status", name])
    if rc == 0:
        return "up" if stdout.strip() == "up" else "down"
    return "unknown"

def get_all_containers():
    stdout, stderr, rc = run_cmd(["nixos-container", "list"])
    if rc == 0:
        return [n.strip() for n in stdout.strip().split('\n') if n.strip()]
    return []

def find_next_available_ip() -> Optional[str]:
    used_ips = set()
    containers = get_all_containers()
    for name in containers:
        info = containers_db.get(name, {})
        if info.get("ip"):
            used_ips.add(info["ip"])
    
    for third in range(1, 255):
        for fourth in range(1, 255):
            ip = f"10.100.{third}.{fourth}"
            if ip not in used_ips:
                return ip
    return None

def build_container_config(name: str, ip: str, user_config: str) -> str:
    """Build complete container Nix config from user snippet"""
    cleaned_config = user_config.strip()
    
    # Remove boot.isContainer if present (nixos-container sets this)
    cleaned_config = re.sub(r'\s*boot\.isContainer\s*=\s*[^;]+;\s*', '\n', cleaned_config)
    # Remove networking.hostName if present
    cleaned_config = re.sub(r'\s*networking\.hostName\s*=\s*[^;]+;\s*', '\n', cleaned_config)
    # Remove networking.useDHCP if present
    cleaned_config = re.sub(r'\s*networking\.useDHCP\s*=\s*[^;]+;\s*', '\n', cleaned_config)
    
    # Check if user_config is already a complete Nix expression (starts with {)
    if cleaned_config.startswith('{'):
        # User provided full config - just add our required settings
        return f'''{{ config, lib, pkgs, ... }}:

{{
  services.openssh.enable = true;
  users.users.root.initialPassword = "root";
{cleaned_config}
  system.stateVersion = "24.11";
}}
'''
    else:
        # User provided just attribute contents
        return f'''{{ config, lib, pkgs, ... }}:

{{
  services.openssh.enable = true;
  users.users.root.initialPassword = "root";
  
  {cleaned_config}
  
  system.stateVersion = "24.11";
}}
'''

def setup_port_forward(host_port: int, container_ip: str, container_port: int):
    run_cmd([
        "iptables", "-t", "nat", "-A", "PREROUTING",
        "-p", "tcp", "--dport", str(host_port),
        "-j", "DNAT", "--to-destination", f"{container_ip}:{container_port}"
    ])
    run_cmd([
        "iptables", "-t", "nat", "-A", "POSTROUTING",
        "-p", "tcp", "--dport", str(container_port),
        "-d", container_ip,
        "-j", "MASQUERADE"
    ])

def remove_port_forward(host_port: int, container_ip: str, container_port: int):
    run_cmd([
        "iptables", "-t", "nat", "-D", "PREROUTING",
        "-p", "tcp", "--dport", str(host_port),
        "-j", "DNAT", "--to-destination", f"{container_ip}:{container_port}"
    ])
    run_cmd([
        "iptables", "-t", "nat", "-D", "POSTROUTING",
        "-p", "tcp", "--dport", str(container_port),
        "-d", container_ip,
        "-j", "MASQUERADE"
    ])

# ============ AUTH ENDPOINTS ============

@app.post("/api/v1/auth/register")
async def register(creds: UserRegister):
    """Register a new user"""
    if not re.match(r'^[a-zA-Z0-9_-]{3,32}$', creds.username):
        raise HTTPException(status_code=400, detail="Username must be 3-32 alphanumeric characters")
    
    if len(creds.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
    
    if creds.username in users_db:
        raise HTTPException(status_code=409, detail="Username already exists")
    
    users_db[creds.username] = {
        "username": creds.username,
        "password_hash": hash_password(creds.password),
        "email": creds.email,
        "created_at": datetime.now().isoformat(),
        "is_admin": False
    }
    save_db(USERS_DB_FILE, users_db)
    
    return {"message": "User registered successfully", "username": creds.username}

@app.post("/api/v1/auth/login")
async def login(creds: UserLogin):
    """Login and get JWT token"""
    user = users_db.get(creds.username)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    
    if not verify_password(creds.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    
    token = create_token(creds.username)
    
    return {
        "access_token": token,
        "token_type": "Bearer",
        "expires_in": JWT_EXPIRATION_HOURS * 3600,
        "username": creds.username
    }

@app.get("/api/v1/auth/me", response_model=UserInfo)
async def get_me(user: str = Depends(require_user)):
    """Get current user info"""
    user_data = users_db.get(user, {})
    return UserInfo(
        username=user,
        email=user_data.get("email"),
        created_at=user_data.get("created_at", "unknown")
    )

# ============ CONTAINER ENDPOINTS (Authenticated) ============

@app.get("/")
async def root(user: Optional[str] = Depends(get_current_user)):
    """Serve HTML page with container list - shows user's containers or public view"""
    # Get containers accessible to this user
    all_names = get_all_containers()
    containers = []
    
    for name in all_names:
        info = containers_db.get(name, {})
        owner = info.get("owner")
        
        # Show if: public, owned by user, or user is admin
        if not user:
            # Public view - only show unowned containers
            if not owner:
                status = get_container_status(name)
                containers.append({
                    "name": name,
                    "status": status,
                    "ip": info.get("ip", "-"),
                    "port": info.get("host_port", "-"),
                    "owner": owner or "unclaimed"
                })
        elif user == "admin" or owner == user or not owner:
            status = get_container_status(name)
            containers.append({
                "name": name,
                "status": status,
                "ip": info.get("ip", "-"),
                "port": info.get("host_port", "-"),
                "owner": owner or "unclaimed"
            })
    
    auth_section = ""
    if user:
        auth_section = f"<p>👤 Logged in as: <b>{user}</b> | <a href='/api/v1/auth/me'>Profile</a></p>"
    else:
        auth_section = """<p>🔒 <a href="#" onclick="document.getElementById('login-form').style.display='block';return false">Login</a> or 
        <a href="#" onclick="document.getElementById('register-form').style.display='block';return false">Register</a></p>
        <div id="login-form" style="display:none;background:#f0f0f0;padding:15px;border-radius:5px;margin:10px 0;">
            <h4>Login</h4>
            <input type="text" id="login-user" placeholder="Username"><br>
            <input type="password" id="login-pass" placeholder="Password"><br>
            <button onclick="doLogin()">Login</button>
        </div>
        <div id="register-form" style="display:none;background:#f0f0f0;padding:15px;border-radius:5px;margin:10px 0;">
            <h4>Register</h4>
            <input type="text" id="reg-user" placeholder="Username"><br>
            <input type="password" id="reg-pass" placeholder="Password"><br>
            <input type="email" id="reg-email" placeholder="Email (optional)"><br>
            <button onclick="doRegister()">Register</button>
        </div>"""
    
    html = f"""<!DOCTYPE html>
<html>
<head>
    <title>NCP - Nix Container Platform</title>
    <meta charset="utf-8">
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; max-width: 900px; margin: 40px auto; padding: 20px; line-height: 1.6; background: #f5f5f5; }}
        h1 {{ color: #333; border-bottom: 3px solid #007acc; padding-bottom: 10px; }}
        .container {{ background: white; border-radius: 8px; padding: 20px; margin: 10px 0; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        .container h3 {{ margin-top: 0; color: #007acc; }}
        .status {{ display: inline-block; padding: 4px 12px; border-radius: 12px; font-size: 0.85em; font-weight: bold; }}
        .up {{ background: #d4edda; color: #155724; }}
        .down {{ background: #f8d7da; color: #721c24; }}
        .info {{ color: #666; font-size: 0.9em; }}
        .owner {{ font-size: 0.8em; color: #999; background: #f0f0f0; padding: 2px 8px; border-radius: 10px; }}
        .empty {{ text-align: center; color: #666; padding: 40px; }}
        .endpoint {{ background: #f8f9fa; padding: 15px; border-radius: 5px; margin-top: 30px; }}
        .auth-box {{ background: #e3f2fd; padding: 15px; border-radius: 5px; margin: 20px 0; }}
        code {{ background: #e9ecef; padding: 2px 6px; border-radius: 3px; font-family: monospace; }}
        pre {{ background: #f4f4f4; padding: 15px; overflow-x: auto; border-radius: 5px; }}
        input {{ margin: 5px; padding: 8px; border: 1px solid #ddd; border-radius: 4px; }}
        button {{ background: #007acc; color: white; border: none; padding: 8px 16px; border-radius: 4px; cursor: pointer; margin: 5px; }}
        button:hover {{ background: #005fa3; }}
    </style>
</head>
<body>
    <h1>🚀 NCP - Nix Container Platform</h1>
    <p>Dynamic NixOS container deployment on nix.latha.org</p>
    
    <div class="auth-box">
        {auth_section}
    </div>
"""
    
    if containers:
        for c in containers:
            status_class = "up" if c["status"] == "up" else "down"
            port_str = f":{c['port']}" if c["port"] != "-" else ""
            owner_badge = f"<span class=\"owner\">👤 {c['owner']}</span>"
            
            if c["port"] != "-":
                service_url = f"http://204.168.220.202:{c['port']}"
                name_html = f'<a href="{service_url}" target="_blank" style="text-decoration: none; color: #007acc;">{c["name"]}</a>'
            else:
                name_html = c['name']
            
            html += f"""
    <div class="container">
        <h3>{name_html} {owner_badge}</h3>
        <span class="status {status_class}">{c['status']}</span>
        <p class="info">IP: {c['ip']}{port_str}</p>
    </div>
"""
    else:
        html += '<div class="empty"><p>No containers visible</p><p>Login to see your containers</p></div>'
    
    html += """
    <div class="endpoint">
        <h3>API Endpoints</h3>
        <pre>POST /api/v1/auth/register   - Register new user
POST /api/v1/auth/login      - Login, get token
GET  /api/v1/auth/me         - Get current user
GET  /api/v1/containers      - List your containers
POST /api/v1/containers      - Create container
GET  /api/v1/containers/{name} - Container details
POST /api/v1/containers/{name}/restart - Restart
DELETE /api/v1/containers/{name} - Destroy</pre>
    </div>
    
    <script>
        async function doLogin() {
            const username = document.getElementById('login-user').value;
            const password = document.getElementById('login-pass').value;
            try {
                const res = await fetch('/api/v1/auth/login', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({username, password})
                });
                const data = await res.json();
                if (res.ok) {
                    localStorage.setItem('ncp_token', data.access_token);
                    alert('Login successful!');
                    location.reload();
                } else {
                    alert('Error: ' + data.detail);
                }
            } catch(e) {
                alert('Error: ' + e.message);
            }
        }
        
        async function doRegister() {
            const username = document.getElementById('reg-user').value;
            const password = document.getElementById('reg-pass').value;
            const email = document.getElementById('reg-email').value || null;
            try {
                const res = await fetch('/api/v1/auth/register', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({username, password, email})
                });
                const data = await res.json();
                if (res.ok) {
                    alert('Registered! Please login.');
                    document.getElementById('register-form').style.display='none';
                } else {
                    alert('Error: ' + data.detail);
                }
            } catch(e) {
                alert('Error: ' + e.message);
            }
        }
        
        // Add token to all API requests if logged in
        const token = localStorage.getItem('ncp_token');
        if (token) {
            const originalFetch = window.fetch;
            window.fetch = function() {
                let args = Array.from(arguments);
                if (args[0].startsWith('/api/') && args.length > 1) {
                    args[1].headers = args[1].headers || {};
                    args[1].headers['Authorization'] = 'Bearer ' + token;
                }
                return originalFetch.apply(this, args);
            };
        }
    </script>
</body>
</html>"""
    
    return HTMLResponse(content=html)

@app.get("/api/v1/containers", response_model=List[ContainerInfo])
async def list_containers(user: str = Depends(require_user)):
    """List containers accessible to the authenticated user"""
    names = get_all_containers()
    containers = []
    
    for name in names:
        info = containers_db.get(name, {})
        owner = info.get("owner")
        
        # Show if: user is admin, user owns it, or unowned
        if user == "admin" or owner == user or not owner:
            status = get_container_status(name)
            containers.append(ContainerInfo(
                name=name,
                status=status,
                ip=info.get("ip"),
                host_port=info.get("host_port"),
                created_at=info.get("created_at", "unknown"),
                owner=owner
            ))
    
    return containers

@app.post("/api/v1/containers", response_model=ContainerInfo)
async def create_container(spec: ContainerSpec, user: str = Depends(require_user)):
    """Create a new container owned by the current user"""
    if not re.match(r'^[a-zA-Z0-9_-]+$', spec.name):
        raise HTTPException(status_code=400, detail="Invalid container name")
    
    if len(spec.name) > 12:
        raise HTTPException(status_code=400, detail="Container name too long (max 12 chars)")
    
    existing = get_all_containers()
    if spec.name in existing:
        raise HTTPException(status_code=409, detail=f"Container {spec.name} already exists")
    
    if not spec.ip:
        spec.ip = find_next_available_ip()
    
    if not spec.ip:
        raise HTTPException(status_code=500, detail="No available IPs")
    
    try:
        # Build container config
        container_config = build_container_config(spec.name, spec.ip, spec.nix_config)
        
        # Create container with inline config
        stdout, stderr, rc = run_cmd([
            "nixos-container", "create", spec.name,
            "--config", container_config,
            "--host-address", NETWORK_CONFIG["gateway"],
            "--local-address", spec.ip
        ], timeout=600)
        
        if rc != 0:
            raise Exception(f"Container creation failed: {stderr}")
        
        # Start the container
        stdout, stderr, rc = run_cmd([
            "nixos-container", "start", spec.name
        ], timeout=60)
        
        if rc != 0:
            status = get_container_status(spec.name)
            if status != "up":
                raise Exception(f"Container start failed: {stderr}")
        
        # Setup port forwarding
        if spec.host_port:
            setup_port_forward(spec.host_port, spec.ip, spec.container_port)
        
        # Save metadata with owner
        containers_db[spec.name] = {
            "ip": spec.ip,
            "host_port": spec.host_port,
            "container_port": spec.container_port,
            "created_at": datetime.now().isoformat(),
            "config": spec.nix_config,
            "status": "up",
            "owner": user  # <-- Ownership tracking
        }
        save_db(CONTAINERS_DB_FILE, containers_db)
        
    except Exception as e:
        # Cleanup on failure
        if spec.name in get_all_containers():
            run_cmd(["nixos-container", "destroy", spec.name])
        raise HTTPException(status_code=500, detail=str(e))
    
    return ContainerInfo(
        name=spec.name,
        status="up",
        ip=spec.ip,
        host_port=spec.host_port,
        created_at=containers_db[spec.name]["created_at"],
        owner=user
    )

@app.get("/api/v1/containers/{name}", response_model=ContainerInfo)
async def get_container(name: str, user: str = Depends(require_user)):
    """Get container details - checks ownership"""
    check_container_access(name, user)  # <-- Authorization check
    
    status = get_container_status(name)
    info = containers_db.get(name, {})
    
    return ContainerInfo(
        name=name,
        status=status,
        ip=info.get("ip"),
        host_port=info.get("host_port"),
        created_at=info.get("created_at", "unknown"),
        owner=info.get("owner")
    )

@app.post("/api/v1/containers/{name}/restart")
async def restart_container(name: str, user: str = Depends(require_user)):
    """Restart a container - checks ownership"""
    check_container_access(name, user)  # <-- Authorization check
    
    stdout, stderr, rc = run_cmd(["nixos-container", "restart", name], timeout=120)
    
    if rc != 0:
        raise HTTPException(status_code=500, detail=f"Restart failed: {stderr}")
    
    return {"message": f"Container {name} restarted"}

@app.delete("/api/v1/containers/{name}")
async def destroy_container(name: str, user: str = Depends(require_user)):
    """Destroy a container - checks ownership"""
    check_container_access(name, user)  # <-- Authorization check
    
    info = containers_db.get(name, {})
    
    # Remove port forwarding
    if info.get("host_port") and info.get("ip"):
        remove_port_forward(info["host_port"], info["ip"], info.get("container_port", 80))
    
    stdout, stderr, rc = run_cmd(["nixos-container", "destroy", name], timeout=120)
    
    if rc != 0:
        raise HTTPException(status_code=500, detail=f"Destroy failed: {stderr}")
    
    # Remove from database
    if name in containers_db:
        del containers_db[name]
        save_db(CONTAINERS_DB_FILE, containers_db)
    
    return {"message": f"Container {name} destroyed"}

# Admin endpoints
@app.get("/api/v1/admin/users")
async def list_users(user: str = Depends(require_user)):
    """List all users (admin only)"""
    if user != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    return [{"username": u, "email": data.get("email"), "created_at": data.get("created_at")} 
            for u, data in users_db.items()]

@app.get("/api/v1/admin/containers")
async def list_all_containers(user: str = Depends(require_user)):
    """List all containers with owners (admin only)"""
    if user != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    names = get_all_containers()
    containers = []
    for name in names:
        status = get_container_status(name)
        info = containers_db.get(name, {})
        containers.append(ContainerInfo(
            name=name,
            status=status,
            ip=info.get("ip"),
            host_port=info.get("host_port"),
            created_at=info.get("created_at", "unknown"),
            owner=info.get("owner", "unclaimed")
        ))
    return containers

if __name__ == "__main__":
    # Create admin user if none exists
    if "admin" not in users_db:
        users_db["admin"] = {
            "username": "admin",
            "password_hash": hash_password("admin123"),  # Change this!
            "email": "admin@nix.latha.org",
            "created_at": datetime.now().isoformat(),
            "is_admin": True
        }
        save_db(USERS_DB_FILE, users_db)
        print("Created default admin user (admin/admin123)")
    
    uvicorn.run(app, host="0.0.0.0", port=8000)
