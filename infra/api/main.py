"""NCP Container Management API - Main entry point."""

import re
import os
import tempfile
import shutil
import subprocess
import json
from datetime import datetime
from typing import Optional, List, Tuple, Dict, Any

from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# Import our modules
import db
from db import init_db, save_db, CONTAINERS_DB_FILE, USERS_DB_FILE
from models import (
    ContainerInfo, ContainerCreateRequest, ContainerDestroyRequest,
    ProjectDeployRequest, ProjectDeployResponse,
    UserRegister, UserLogin, TokenResponse
)
from auth import (
    init_default_admin, hash_password, verify_password, create_access_token,
    require_user, optional_user
)

app = FastAPI(title="NCP API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize on startup
init_db()


# Utility functions
def run_cmd(cmd: List[str], timeout: int = 30) -> Tuple[str, str, int]:
    """Run shell command and return stdout, stderr, returncode."""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return result.stdout, result.stderr, result.returncode
    except subprocess.TimeoutExpired:
        return "", f"Command timed out after {timeout}s", -1
    except Exception as e:
        return "", str(e), -1


def get_all_containers() -> List[str]:
    """Get list of all nixos containers."""
    stdout, _, _ = run_cmd(["nixos-container", "list"])
    return [name.strip() for name in stdout.strip().split('\n') if name.strip()]


def get_container_status(name: str) -> str:
    """Get container status (up/down)."""
    stdout, _, rc = run_cmd(["nixos-container", "status", name], timeout=10)
    return "up" if rc == 0 and "up" in stdout else "down"


def get_container_ip(name: str) -> Optional[str]:
    """Get container IP."""
    stdout, _, rc = run_cmd(["nixos-container", "show-ip", name], timeout=10)
    return stdout.strip() if rc == 0 else None


def setup_port_forward(host_port: int, container_ip: str, container_port: int) -> bool:
    """Setup iptables DNAT rule."""
    # Remove existing rule if present
    stdout, _, _ = run_cmd(["iptables", "-t", "nat", "-L", "PREROUTING", "-n", "--line-numbers"])
    if f"dpt:{host_port}" in stdout:
        lines = stdout.strip().split('\n')
        for i, line in enumerate(lines):
            if f"dpt:{host_port}" in line:
                run_cmd(["iptables", "-t", "nat", "-D", "PREROUTING", str(i)], timeout=10)
                break
    
    # Add DNAT rule
    _, _, rc = run_cmd([
        "iptables", "-t", "nat", "-A", "PREROUTING",
        "-p", "tcp", "--dport", str(host_port),
        "-j", "DNAT", "--to-destination", f"{container_ip}:{container_port}"
    ], timeout=10)
    return rc == 0


def remove_port_forward(host_port: int, container_ip: str, container_port: int) -> bool:
    """Remove iptables DNAT rule."""
    run_cmd([
        "iptables", "-t", "nat", "-D", "PREROUTING",
        "-p", "tcp", "--dport", str(host_port),
        "-j", "DNAT", "--to-destination", f"{container_ip}:{container_port}"
    ], timeout=10)
    return True


def find_next_available_ip() -> Optional[str]:
    """Find next available IP in container subnet."""
    import ipaddress
    subnet = ipaddress.ip_network("10.100.0.0/16")
    used_ips = set()
    
    for name in get_all_containers():
        ip = get_container_ip(name)
        if ip:
            try:
                used_ips.add(ipaddress.ip_address(ip))
            except ValueError:
                pass
    
    for host in range(2, 255):
        candidate = ipaddress.ip_address(subnet.network_address + host)
        if candidate not in used_ips and candidate != ipaddress.ip_address("10.100.0.1"):
            return str(candidate)
    return None


# HTML Frontend
def generate_html_page(title: str, body_content: str) -> str:
    """Generate HTML page with common styling."""
    return f'''<!DOCTYPE html>
<html>
<head>
    <title>{title} - NCP</title>
    <style>
        body {{ font-family: system-ui, sans-serif; max-width: 900px; margin: 2rem auto; padding: 0 1rem; }}
        h1 {{ color: #333; border-bottom: 2px solid #5277c3; padding-bottom: 0.5rem; }}
        .container {{ border: 1px solid #ddd; border-radius: 8px; padding: 1rem; margin: 1rem 0; }}
        .status {{ display: inline-block; padding: 0.25rem 0.5rem; border-radius: 4px; font-size: 0.875rem; font-weight: 500; }}
        .status.up {{ background: #d4edda; color: #155724; }}
        .status.down {{ background: #f8d7da; color: #721c24; }}
        .auth-bar {{ background: #f5f5f5; padding: 1rem; border-radius: 8px; margin-bottom: 2rem; }}
        .btn {{ background: #5277c3; color: white; border: none; padding: 0.5rem 1rem; border-radius: 4px; cursor: pointer; margin-right: 0.5rem; }}
        .btn:hover {{ background: #3f5aa6; }}
        input {{ padding: 0.5rem; border: 1px solid #ddd; border-radius: 4px; margin-right: 0.5rem; }}
        a {{ color: #5277c3; text-decoration: none; }}
        a:hover {{ text-decoration: underline; }}
    </style>
</head>
<body>
    {body_content}
    <script>
        const API_URL = window.location.origin + '/api/v1';
        const token = localStorage.getItem('ncp_token');
        
        function updateAuthUI() {{
            const authDiv = document.getElementById('auth-section');
            if (token && authDiv) {{
                authDiv.innerHTML = `<span>Logged in</span> <button class="btn" onclick="logout()">Logout</button>`;
            }}
        }}
        
        function logout() {{
            localStorage.removeItem('ncp_token');
            window.location.reload();
        }}
        
        async function api(method, endpoint, body = null) {{
            const opts = {{
                method,
                headers: {{ 'Content-Type': 'application/json' }}
            }};
            if (token) opts.headers['Authorization'] = `Bearer ${{token}}`;
            if (body) opts.body = JSON.stringify(body);
            const resp = await fetch(API_URL + endpoint, opts);
            return resp.json();
        }}
        
        updateAuthUI();
    </script>
</body>
</html>'''


@app.get("/", response_class=HTMLResponse)
async def root_page(request: Request):
    """Serve HTML frontend listing containers."""
    user = optional_user(request)
    
    # Get containers
    all_containers = get_all_containers()
    visible_containers = []
    
    for name in all_containers:
        info = db.containers_db.get(name, {})
        owner = info.get("owner")
        
        # Show if: unowned, or current user owns it, or user is admin
        if not owner or owner == user or (user and db.users_db.get(user, {}).get("is_admin")):
            status = get_container_status(name)
            visible_containers.append({
                "name": name,
                "status": status,
                "ip": info.get("ip"),
                "host_port": info.get("host_port"),
                "owner": owner or "unclaimed"
            })
    
    # Build container list HTML
    containers_html = ""
    if visible_containers:
        for c in visible_containers:
            status_class = "up" if c["status"] == "up" else "down"
            port_info = f" (Port {c['host_port']})" if c["host_port"] else ""
            
            # Make service name a clickable link if port is known
            name_display = c["name"]
            if c["host_port"]:
                name_display = f'<a href="http://204.168.220.202:{c["host_port"]}" target="_blank">{c["name"]}</a>'
            
            containers_html += f'''
            <div class="container">
                <strong>{name_display}</strong> 
                <span class="status {status_class}">{c["status"]}</span>
                <span style="color: #666; margin-left: 1rem;">Owner: {c["owner"]}{port_info}</span>
            </div>'''
    else:
        containers_html = "<p>No containers found.</p>"
    
    body = f'''
    <h1>NCP Containers</h1>
    <div class="auth-bar" id="auth-section">
        <input type="text" id="username" placeholder="Username">
        <input type="password" id="password" placeholder="Password">
        <button class="btn" onclick="login()">Login</button>
    </div>
    {containers_html}
    <script>
        async function login() {{
            const u = document.getElementById('username').value;
            const p = document.getElementById('password').value;
            const resp = await fetch(API_URL + '/auth/login', {{
                method: 'POST',
                headers: {{'Content-Type': 'application/json'}},
                body: JSON.stringify({{username: u, password: p}})
            }});
            const data = await resp.json();
            if (data.access_token) {{
                localStorage.setItem('ncp_token', data.access_token);
                window.location.reload();
            }} else {{
                alert('Login failed: ' + (data.detail || 'Unknown error'));
            }}
        }}
    </script>
    '''
    
    return HTMLResponse(content=generate_html_page("Containers", body))


# API Endpoints
@app.get("/api/v1/containers")
async def list_containers(user: Optional[str] = Depends(optional_user)):
    """List all containers (public view shows unowned only)."""
    all_names = get_all_containers()
    result = []
    
    for name in all_names:
        info = db.containers_db.get(name, {})
        owner = info.get("owner")
        
        # Public: only unowned. Authenticated: own + unowned. Admin: all.
        if not user and owner:
            continue
        if user and owner and owner != user and not db.users_db.get(user, {}).get("is_admin"):
            continue
        
        result.append(ContainerInfo(
            name=name,
            status=get_container_status(name),
            ip=info.get("ip"),
            host_port=info.get("host_port"),
            created_at=info.get("created_at"),
            owner=owner or "unclaimed"
        ))
    
    return result


@app.post("/api/v1/containers", response_model=ContainerInfo)
async def create_container(
    req: ContainerCreateRequest,
    user: str = Depends(require_user)
):
    """Create a new container."""
    full_name = req.name[:12]
    
    if len(full_name) < 3:
        raise HTTPException(400, "Name too short after truncation")
    
    if full_name in get_all_containers():
        raise HTTPException(409, f"Container '{full_name}' already exists")
    
    # Allocate IP
    ip = find_next_available_ip()
    if not ip:
        raise HTTPException(500, "No available IPs")
    
    # Build config
    nix_config = req.config or '{ services.nginx.enable = true; networking.firewall.allowedTCPPorts = [ 80 ]; }'
    config_file = build_container_config(full_name, nix_config)
    
    try:
        # Create container
        stdout, stderr, rc = run_cmd([
            "nixos-container", "create", full_name,
            "--config-file", config_file,
            "--host-address", "10.100.0.1",
            "--local-address", ip
        ], timeout=600)
        
        if rc != 0:
            raise HTTPException(500, f"Creation failed: {stderr}")
    finally:
        os.unlink(config_file)
    
    # Start and setup port forward
    run_cmd(["nixos-container", "start", full_name], timeout=60)
    setup_port_forward(req.port, ip, req.container_port)
    
    # Save to DB
    db.containers_db[full_name] = {
        "ip": ip,
        "host_port": req.port,
        "container_port": req.container_port,
        "config": nix_config,
        "status": "up",
        "owner": user,
        "created_at": datetime.now().isoformat(),
        "public": req.public
    }
    save_db(CONTAINERS_DB_FILE, db.containers_db)
    
    return ContainerInfo(
        name=full_name,
        status="up",
        ip=ip,
        host_port=req.port,
        created_at=db.containers_db[full_name]["created_at"],
        owner=user
    )


@app.post("/api/v1/containers/destroy")
async def destroy_container(req: ContainerDestroyRequest, user: str = Depends(require_user)):
    """Destroy a container (owner or admin only)."""
    full_name = req.name[:12]
    info = db.containers_db.get(full_name)
    
    if not info:
        raise HTTPException(404, "Container not found")
    
    if info.get("owner") != user and not db.users_db.get(user, {}).get("is_admin"):
        raise HTTPException(403, "Not owner of this container")
    
    # Cleanup port forward
    if info.get("host_port") and info.get("ip"):
        remove_port_forward(info["host_port"], info["ip"], info.get("container_port", 80))
    
    # Destroy container
    _, stderr, rc = run_cmd(["nixos-container", "destroy", full_name], timeout=60)
    if rc != 0 and "No such file or directory" not in stderr:
        raise HTTPException(500, f"Destroy failed: {stderr}")
    
    # Remove from DB
    if full_name in db.containers_db:
        del db.containers_db[full_name]
        save_db(CONTAINERS_DB_FILE, db.containers_db)
    
    return {"success": True, "message": f"Container '{full_name}' destroyed"}


@app.post("/api/v1/projects/{project_name}/deploy", response_model=ProjectDeployResponse)
async def deploy_project(
    project_name: str,
    request: ProjectDeployRequest,
    user: str = Depends(require_user)
):
    """Deploy a project - writes files and uses nixos-container --flake."""
    
    if not re.match(r'^[a-zA-Z0-9_-]+$', project_name):
        raise HTTPException(400, "Invalid project name")
    
    if "flake.nix" not in request.files:
        raise HTTPException(400, "No flake.nix in project files")
    
    # Create temp directory
    temp_dir = tempfile.mkdtemp(prefix=f"ncp_project_{project_name}_")
    deployed, destroyed, errors = [], [], []
    
    try:
        # Write all files
        for filepath, content in request.files.items():
            full_path = os.path.join(temp_dir, filepath)
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, 'w') as f:
                f.write(content)
        
        # Get ncp.containers from flake (simple eval for ports only)
        port_cmd = f'''
let flake = builtins.getFlake (toString {temp_dir}); 
in builtins.mapAttrs (n: c: c.port) (flake.ncp.containers or {{}})
'''
        stdout, stderr, rc = run_cmd(["nix", "eval", "--impure", "--json", "--expr", port_cmd], timeout=60)
        
        if rc != 0:
            raise HTTPException(400, f"Failed to evaluate flake.nix: {stderr}")
        
        try:
            ports = json.loads(stdout)
        except:
            raise HTTPException(400, "No ncp.containers defined in flake.nix")
        
        if not ports:
            raise HTTPException(400, "No ncp.containers defined in flake.nix")
        
        # Get current containers for this project
        existing = get_all_containers()
        current = {n: i for n, i in db.containers_db.items() 
                   if i.get('owner') == user and i.get('project') == project_name and n in existing}
        
        desired = set(ports.keys())
        current_names = set(current.keys())
        
        # Destroy obsolete
        for name in current_names - desired:
            full_name = name[:12]
            info = db.containers_db.get(full_name, {})
            if info.get('host_port') and info.get('ip'):
                remove_port_forward(info['host_port'], info['ip'], info.get('container_port', 80))
            run_cmd(["nixos-container", "destroy", full_name], timeout=60)
            if full_name in db.containers_db:
                del db.containers_db[full_name]
                save_db(CONTAINERS_DB_FILE, db.containers_db)
            destroyed.append(full_name)
        
        # Create new containers using --flake
        for name in desired - current_names:
            full_name = name[:12]
            host_port = ports.get(name)
            
            if not host_port:
                errors.append(f"{full_name}: no port specified")
                continue
            
            ip = find_next_available_ip()
            if not ip:
                errors.append(f"{full_name}: no available IPs")
                continue
            
            # Create using --flake
            stdout, stderr, rc = run_cmd([
                "nixos-container", "create", full_name,
                "--flake", f"{temp_dir}#{name}",
                "--host-address", "10.100.0.1",
                "--local-address", ip
            ], timeout=600)
            
            if rc != 0:
                errors.append(f"{full_name}: creation failed - {stderr}")
                continue
            
            run_cmd(["nixos-container", "start", full_name], timeout=60)
            setup_port_forward(host_port, ip, 80)  # Assume port 80 inside
            
            db.containers_db[full_name] = {
                "ip": ip,
                "host_port": host_port,
                "container_port": 80,
                "status": "up",
                "owner": user,
                "project": project_name,
                "created_at": datetime.now().isoformat()
            }
            save_db(CONTAINERS_DB_FILE, db.containers_db)
            
            deployed.append(ContainerInfo(
                name=full_name, status="up", ip=ip,
                host_port=host_port,
                created_at=db.containers_db[full_name]["created_at"],
                owner=user
            ))
    
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
    
    msgs = []
    if deployed:
        msgs.append(f"Created {len(deployed)} containers")
    if destroyed:
        msgs.append(f"Removed {len(destroyed)} obsolete containers")
    if errors:
        msgs.append(f"{len(errors)} errors: {'; '.join(errors[:3])}")
    
    return ProjectDeployResponse(
        project=project_name,
        containers=deployed,
        message=", ".join(msgs) if msgs else "No changes"
    )


# Auth endpoints
@app.post("/api/v1/auth/register")
async def register(user: UserRegister):
    """Register a new user."""
    if user.username in db.users_db:
        raise HTTPException(400, "Username already exists")
    
    db.users_db[user.username] = {
        "username": user.username,
        "password_hash": hash_password(user.password),
        "email": user.email,
        "created_at": datetime.now().isoformat(),
        "is_admin": False
    }
    save_db(USERS_DB_FILE, db.users_db)
    
    token = create_access_token({"sub": user.username})
    return TokenResponse(access_token=token)


@app.post("/api/v1/auth/login", response_model=TokenResponse)
async def login(creds: UserLogin):
    """Login and get access token."""
    user = db.users_db.get(creds.username)
    if not user or not verify_password(creds.password, user["password_hash"]):
        raise HTTPException(401, "Invalid credentials")
    
    token = create_access_token({"sub": creds.username})
    return TokenResponse(access_token=token)


@app.get("/api/v1/auth/me")
async def me(user: str = Depends(require_user)):
    """Get current user info."""
    info = db.users_db.get(user, {})
    return {"username": user, "is_admin": info.get("is_admin", False)}


if __name__ == "__main__":
    init_default_admin()
    uvicorn.run(app, host="0.0.0.0", port=8000)
