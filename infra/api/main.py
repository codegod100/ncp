"""NCP Container Management API - Main entry point."""

import re
import os
import tempfile
import shutil
import subprocess
import json
import logging
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Tuple, Dict, Any

# Setup logging before anything else
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("ncp-api")
logger.info("=" * 60)
logger.info("NCP API Starting up")
logger.info("=" * 60)

from fastapi import FastAPI, HTTPException, Depends, Request, Response
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import uvicorn

# Load environment variables from .env file
load_dotenv()

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

# Config from environment
NCP_USER = os.getenv("NCP_USER", "nandi")
NCP_USER_HOME = os.getenv("NCP_USER_HOME", f"/home/{NCP_USER}")
NIXBUILD_SSH_KEY_NAME = os.getenv("NIXBUILD_SSH_KEY_NAME", "id_ed25519_nixbuild")
NIXBUILD_SSH_USER = os.getenv("NIXBUILD_SSH_USER", NCP_USER)
NIXBUILD_HOST = os.getenv("NIXBUILD_HOST", "eu.nixbuild.net")
NIXBUILD_MAX_JOBS = os.getenv("NIXBUILD_MAX_JOBS", "100")
NIXBUILD_FEATURES = os.getenv("NIXBUILD_FEATURES", "benchmark,big-parallel")
NIX_MACHINES_FILE = os.getenv("NIX_MACHINES_FILE", "/etc/nix/machines")

# Network settings
CONTAINER_SUBNET = os.getenv("CONTAINER_SUBNET", "10.100.0.0/16")
CONTAINER_HOST_IP = os.getenv("CONTAINER_HOST_IP", "10.100.0.1")

# API settings
API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("API_PORT", "8000"))

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
def run_cmd(cmd: List[str], timeout: int = 30, description: str = None) -> Tuple[str, str, int]:
    """Run shell command and return stdout, stderr, returncode."""
    cmd_str = ' '.join(cmd)
    desc = f" [{description}]" if description else ""
    logger.info(f"[CMD{desc}] $ {cmd_str} (timeout={timeout}s)")
    start = datetime.now()
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        elapsed = (datetime.now() - start).total_seconds()
        
        if result.returncode == 0:
            logger.info(f"[CMD{desc}] ✓ Success in {elapsed:.1f}s")
            if result.stdout:
                logger.debug(f"[CMD{desc}] stdout: {result.stdout[:500]}")
        else:
            logger.warning(f"[CMD{desc}] ✗ Failed (code={result.returncode}) in {elapsed:.1f}s")
            if result.stderr:
                logger.warning(f"[CMD{desc}] stderr: {result.stderr[:500]}")
        
        return result.stdout, result.stderr, result.returncode
        
    except subprocess.TimeoutExpired:
        elapsed = (datetime.now() - start).total_seconds()
        logger.error(f"[CMD{desc}] ⏱ TIMEOUT after {elapsed:.1f}s (limit was {timeout}s)")
        return "", f"Command timed out after {timeout}s", -1
        
    except Exception as e:
        elapsed = (datetime.now() - start).total_seconds()
        logger.error(f"[CMD{desc}] 💥 Exception after {elapsed:.1f}s: {e}")
        return "", str(e), -1


def get_all_containers() -> List[str]:
    """Get list of all nixos containers."""
    logger.debug("[CONTAINERS] Listing all nixos containers...")
    stdout, _, _ = run_cmd(["nixos-container", "list"], timeout=5, description="list-containers")
    containers = [name.strip() for name in stdout.strip().split('\n') if name.strip()]
    logger.info(f"[CONTAINERS] Found {len(containers)} containers: {containers}")
    return containers


def get_container_status(name: str) -> str:
    """Get container status (up/down)."""
    logger.debug(f"[STATUS] Checking status of container '{name}'...")
    stdout, _, rc = run_cmd(["nixos-container", "status", name], timeout=10, description=f"status-{name}")
    status = "up" if rc == 0 and "up" in stdout else "down"
    logger.debug(f"[STATUS] Container '{name}' is {status}")
    return status


def get_container_ip(name: str) -> Optional[str]:
    """Get container IP."""
    logger.debug(f"[IP] Getting IP for container '{name}'...")
    stdout, _, rc = run_cmd(["nixos-container", "show-ip", name], timeout=10, description=f"ip-{name}")
    ip = stdout.strip() if rc == 0 else None
    if ip:
        logger.debug(f"[IP] Container '{name}' has IP: {ip}")
    else:
        logger.warning(f"[IP] Could not get IP for container '{name}'")
    return ip


def setup_nixbuild_net() -> Tuple[bool, str]:
    """Configure nixbuild.net as a remote builder on the server."""
    logger.info(f"[NIXBUILD] Setting up nixbuild.net remote builder...")
    logger.info(f"[NIXBUILD] Host: {NIXBUILD_HOST}, User: {NIXBUILD_SSH_USER}, MaxJobs: {NIXBUILD_MAX_JOBS}")
    
    # Check if already configured
    if os.path.exists(NIX_MACHINES_FILE):
        with open(NIX_MACHINES_FILE, 'r') as f:
            if NIXBUILD_HOST in f.read():
                logger.info(f"[NIXBUILD] Already configured - skipping")
                return True, f"{NIXBUILD_HOST} already configured"
    
    # Copy existing SSH key from user's home
    user_ssh_key = os.path.join(NCP_USER_HOME, ".ssh", NIXBUILD_SSH_KEY_NAME)
    ssh_key_path = f"/root/.ssh/{NIXBUILD_SSH_KEY_NAME}"
    ssh_dir = "/root/.ssh"
    
    try:
        # Check if user has the key
        if not os.path.exists(user_ssh_key):
            logger.error(f"[NIXBUILD] SSH key not found: {user_ssh_key}")
            return False, f"No existing nixbuild key found at {user_ssh_key}"
        
        logger.info(f"[NIXBUILD] Found SSH key at {user_ssh_key}")
        
        # Create SSH directory
        os.makedirs(ssh_dir, mode=0o700, exist_ok=True)
        logger.info(f"[NIXBUILD] Created SSH directory: {ssh_dir}")
        
        # Copy the key
        shutil.copy2(user_ssh_key, ssh_key_path)
        shutil.copy2(user_ssh_key + ".pub", ssh_key_path + ".pub")
        os.chmod(ssh_key_path, 0o600)
        logger.info(f"[NIXBUILD] Copied SSH key to {ssh_key_path}")
        
        # Setup known_hosts
        known_hosts = os.path.join(ssh_dir, "known_hosts")
        nixbuild_key = f"{NIXBUILD_HOST} ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIPIQCZc54poJ8vqawd8TraNryQeJnvH1eLpIDgbiqymM"
        
        if not os.path.exists(known_hosts) or nixbuild_key not in open(known_hosts).read():
            with open(known_hosts, 'a') as f:
                f.write(nixbuild_key + "\n")
            os.chmod(known_hosts, 0o644)
            logger.info(f"[NIXBUILD] Added {NIXBUILD_HOST} to known_hosts")
        
        # Setup SSH config
        ssh_config = os.path.join(ssh_dir, "config")
        nixbuild_config = f"""Host {NIXBUILD_HOST}
  User {NIXBUILD_SSH_USER}
  PubkeyAcceptedKeyTypes ssh-ed25519
  ServerAliveInterval 60
  IPQoS throughput
  IdentityFile {ssh_key_path}
"""
        
        if not os.path.exists(ssh_config) or NIXBUILD_HOST not in open(ssh_config).read():
            with open(ssh_config, 'a') as f:
                f.write(nixbuild_config)
            os.chmod(ssh_config, 0o600)
            logger.info(f"[NIXBUILD] Added SSH config for {NIXBUILD_HOST}")
        
        # Configure build machines
        machines_entry = f"ssh://{NIXBUILD_SSH_USER}@{NIXBUILD_HOST} x86_64-linux - {NIXBUILD_MAX_JOBS} 1 {NIXBUILD_FEATURES} - -\n"
        
        if os.path.exists(NIX_MACHINES_FILE):
            with open(NIX_MACHINES_FILE, 'r') as f:
                content = f.read()
            if NIXBUILD_HOST not in content:
                with open(NIX_MACHINES_FILE, 'a') as f:
                    f.write(machines_entry)
                logger.info(f"[NIXBUILD] Added {NIXBUILD_HOST} to {NIX_MACHINES_FILE}")
            else:
                logger.info(f"[NIXBUILD] {NIXBUILD_HOST} already in {NIX_MACHINES_FILE}")
        else:
            with open(NIX_MACHINES_FILE, 'w') as f:
                f.write(machines_entry)
            logger.info(f"[NIXBUILD] Created {NIX_MACHINES_FILE} with {NIXBUILD_HOST}")
        os.chmod(NIX_MACHINES_FILE, 0o644)
        
        logger.info(f"[NIXBUILD] ✓ Configuration complete")
        return True, f"{NIXBUILD_HOST} configured with existing key for user '{NIXBUILD_SSH_USER}'"
        
    except Exception as e:
        logger.error(f"[NIXBUILD] ✗ Setup failed: {e}")
        return False, f"Setup failed: {str(e)}"


def setup_port_forward(host_port: int, container_ip: str, container_port: int) -> bool:
    """Setup iptables DNAT rule."""
    logger.info(f"[PORT-FWD] Setting up port forward: host:{host_port} -> {container_ip}:{container_port}")
    
    # Remove ALL existing rules for this port (cleanup duplicates)
    # iptables -L --line-numbers output format:
    # Chain PREROUTING (policy ACCEPT)
    # num  target     prot opt source               destination
    # 1    DNAT       tcp  --  0.0.0.0/0            0.0.0.0/0            tcp dpt:9002 to:10.100.0.5:80
    cleanup_count = 0
    max_iterations = 50  # Safety limit to prevent infinite loops
    
    for _ in range(max_iterations):
        stdout, _, _ = run_cmd(["iptables", "-t", "nat", "-L", "PREROUTING", "-n", "--line-numbers"], 
                               description=f"list-rules-port-{host_port}")
        
        # Parse line numbers from output - skip first 2 header lines
        lines = stdout.strip().split('\n')
        rule_to_delete = None
        
        for line in lines[2:]:  # Skip "Chain PREROUTING..." and "num target..." headers
            parts = line.split()
            if len(parts) >= 4:
                # parts[0] is the line number, parts[-2] is usually "dpt:PORT"
                for part in parts:
                    if part == f"dpt:{host_port}" or part.startswith(f"dpt:{host_port}"):
                        # Found the rule - extract the actual iptables line number
                        try:
                            rule_to_delete = int(parts[0])
                        except ValueError:
                            pass
                        break
            if rule_to_delete:
                break
        
        if not rule_to_delete:
            break  # No more rules for this port
        
        # Delete by the actual iptables line number (1-indexed)
        logger.debug(f"[PORT-FWD] Deleting rule at line {rule_to_delete} for port {host_port}")
        _, stderr, rc = run_cmd(["iptables", "-t", "nat", "-D", "PREROUTING", str(rule_to_delete)], 
                               timeout=10, description=f"del-rule-port-{host_port}-line-{rule_to_delete}")
        
        if rc != 0:
            logger.warning(f"[PORT-FWD] Failed to delete rule {rule_to_delete}: {stderr}")
            break  # Stop trying if delete fails
        
        cleanup_count += 1
    
    if cleanup_count > 0:
        logger.info(f"[PORT-FWD] Cleaned up {cleanup_count} existing rules for port {host_port}")
    
    # Add DNAT rule
    logger.info(f"[PORT-FWD] Adding DNAT rule: {host_port} -> {container_ip}:{container_port}")
    _, _, rc = run_cmd([
        "iptables", "-t", "nat", "-A", "PREROUTING",
        "-p", "tcp", "--dport", str(host_port),
        "-j", "DNAT", "--to-destination", f"{container_ip}:{container_port}"
    ], timeout=10, description=f"add-rule-port-{host_port}")
    
    if rc == 0:
        logger.info(f"[PORT-FWD] ✓ Port forward created: {host_port} -> {container_ip}:{container_port}")
    else:
        logger.error(f"[PORT-FWD] ✗ Failed to create port forward for port {host_port}")
    
    return rc == 0


def remove_port_forward(host_port: int, container_ip: str, container_port: int) -> bool:
    """Remove iptables DNAT rule."""
    logger.info(f"[PORT-FWD] Removing port forward: host:{host_port} -> {container_ip}:{container_port}")
    run_cmd([
        "iptables", "-t", "nat", "-D", "PREROUTING",
        "-p", "tcp", "--dport", str(host_port),
        "-j", "DNAT", "--to-destination", f"{container_ip}:{container_port}"
    ], timeout=10, description=f"remove-rule-port-{host_port}")
    logger.info(f"[PORT-FWD] Port forward removed (if it existed)")
    return True


def find_next_available_ip() -> Optional[str]:
    """Find next available IP in container subnet."""
    import ipaddress
    logger.debug(f"[IP-ALLOC] Searching for available IP in {CONTAINER_SUBNET}...")
    
    subnet = ipaddress.ip_network(CONTAINER_SUBNET)
    host_ip = ipaddress.ip_address(CONTAINER_HOST_IP)
    used_ips = set()
    
    containers = get_all_containers()
    logger.debug(f"[IP-ALLOC] Checking {len(containers)} existing containers...")
    
    for name in containers:
        ip = get_container_ip(name)
        if ip:
            try:
                used_ips.add(ipaddress.ip_address(ip))
                logger.debug(f"[IP-ALLOC]   - {name}: {ip} (in use)")
            except ValueError:
                pass
    
    logger.debug(f"[IP-ALLOC] {len(used_ips)} IPs are currently in use")
    
    for host in range(2, 255):
        candidate = ipaddress.ip_address(subnet.network_address + host)
        if candidate not in used_ips and candidate != host_ip:
            logger.info(f"[IP-ALLOC] ✓ Found available IP: {candidate}")
            return str(candidate)
    
    logger.error(f"[IP-ALLOC] ✗ No available IPs in {CONTAINER_SUBNET}")
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
        .container {{ border: 1px solid #ddd; border-radius: 8px; padding: 1rem; margin: 0.5rem 0; background: white; }}
        .project {{ margin: 1.5rem 0; }}
        .project h2 {{ color: #333; border-bottom: 2px solid #5277c3; padding-bottom: 0.5rem; margin-bottom: 1rem; }}
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
                // Fetch current user info
                fetch(API_URL + '/auth/me', {{ headers: {{ 'Authorization': 'Bearer ' + token }} }})
                    .then(r => r.json())
                    .then(data => {{
                        const username = data.username || 'unknown';
                        authDiv.innerHTML = '<span>👤 ' + username + '</span> <button class="btn" onclick="logout()">Logout</button>';
                    }})
                    .catch(() => {{
                        authDiv.innerHTML = '<span>👤 Logged in</span> <button class="btn" onclick="logout()">Logout</button>';
                    }});
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
        
        async function loadContainers() {{
            const data = await api('GET', '/containers');
            const listDiv = document.getElementById('containers-list');
            if (!data || data.length === 0) {{
                listDiv.innerHTML = '<p>No containers found.</p>';
                return;
            }}
            
            // Group by project
            const byProject = {{}};
            data.forEach(c => {{
                const proj = c.project || 'default';
                if (!byProject[proj]) byProject[proj] = [];
                byProject[proj].push(c);
            }});
            
            let html = '';
            Object.keys(byProject).sort().forEach(proj => {{
                html += '<div class="project"><h2>📁 ' + proj + '</h2>';
                byProject[proj].forEach(c => {{
                    const statusClass = c.status === 'up' ? 'up' : 'down';
                    const portInfo = c.host_port ? ' (Port ' + c.host_port + ')' : '';
                    const owner = c.owner || 'unclaimed';
                    const nameDisplay = c.host_port 
                        ? '<a href="http://nix.latha.org:' + c.host_port + '">' + c.name + '</a>'
                        : c.name;
                    html += '<div class="container"><strong>' + nameDisplay + '</strong> ' +
                           '<span class="status ' + statusClass + '">' + c.status + '</span> ' +
                           '<span style="color: #666; margin-left: 1rem;">' + owner + portInfo + '</span></div>';
                }});
                html += '</div>';
            }});
            listDiv.innerHTML = html;
        }}
        
        updateAuthUI();
        loadContainers();
    </script>
</body>
</html>'''


def build_container_config(name: str, nix_config: str) -> str:
    """Write NixOS container config to a temp file and return the path."""
    import tempfile
    config_content = f'''
{{ config, pkgs, lib, ... }}:

{nix_config}
'''
    fd, config_file = tempfile.mkstemp(prefix=f"ncp_{name}_", suffix=".nix")
    try:
        with os.fdopen(fd, 'w') as f:
            f.write(config_content)
        logger.debug(f"[CONFIG] Written container config to {config_file}")
        return config_file
    except Exception as e:
        os.close(fd)
        os.unlink(config_file)
        raise e


@app.get("/", response_class=HTMLResponse)
async def root_page(request: Request):
    """Serve HTML frontend - containers loaded dynamically via JS."""
    body = '''
    <h1>NCP Containers</h1>
    <div class="auth-bar" id="auth-section">
        <input type="text" id="username" placeholder="Username">
        <input type="password" id="password" placeholder="Password">
        <button class="btn" onclick="login()">Login</button>
    </div>
    <div id="containers-list"><p>Loading containers...</p></div>
    <script>
        async function login() {
            const u = document.getElementById('username').value;
            const p = document.getElementById('password').value;
            const resp = await fetch(API_URL + '/auth/login', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({username: u, password: p})
            });
            const data = await resp.json();
            if (data.access_token) {
                localStorage.setItem('ncp_token', data.access_token);
                window.location.reload();
            } else {
                alert('Login failed: ' + (data.detail || 'Unknown error'));
            }
        }
    </script>
    '''
    
    return HTMLResponse(content=generate_html_page("Containers", body))


# API Endpoints
@app.get("/api/v1/containers")
async def list_containers(user: Optional[str] = Depends(optional_user)):
    """List all containers (public view shows unowned only)."""
    user_str = user or "anonymous"
    logger.info(f"[LIST] User '{user_str}' listing containers")
    
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
            owner=owner or "unclaimed",
            project=info.get("project")
        ))
    
    logger.info(f"[LIST] Returning {len(result)} containers for '{user_str}'")
    return result


@app.post("/api/v1/containers", response_model=ContainerInfo)
async def create_container(
    req: ContainerCreateRequest,
    user: str = Depends(require_user)
):
    """Create a new container."""
    full_name = req.name[:12]
    logger.info(f"[CREATE] User '{user}' creating container '{full_name}' (requested: '{req.name}')")
    logger.info(f"[CREATE] Config: port={req.port}, container_port={req.container_port}")
    
    if len(full_name) < 3:
        logger.warning(f"[CREATE] Name too short: '{full_name}'")
        raise HTTPException(400, "Name too short after truncation")
    
    existing = get_all_containers()
    if full_name in existing:
        logger.warning(f"[CREATE] Container '{full_name}' already exists")
        raise HTTPException(409, f"Container '{full_name}' already exists")
    
    # Allocate IP
    logger.info(f"[CREATE] Allocating IP for '{full_name}'...")
    ip = find_next_available_ip()
    if not ip:
        logger.error(f"[CREATE] No available IPs for '{full_name}'")
        raise HTTPException(500, "No available IPs")
    logger.info(f"[CREATE] Allocated IP {ip} for '{full_name}'")
    
    # Build config
    nix_config = req.config or '{ services.nginx.enable = true; networking.firewall.allowedTCPPorts = [ 80 ]; }'
    config_file = build_container_config(full_name, nix_config)
    logger.info(f"[CREATE] Created temp config file: {config_file}")
    
    try:
        # Create container
        logger.info(f"[CREATE] Running nixos-container create for '{full_name}'...")
        stdout, stderr, rc = run_cmd([
            "nixos-container", "create", full_name,
            "--config-file", config_file,
            "--host-address", CONTAINER_HOST_IP,
            "--local-address", ip
        ], timeout=600, description=f"create-container-{full_name}")
        
        if rc != 0:
            logger.error(f"[CREATE] Container creation failed: {stderr}")
            raise HTTPException(500, f"Creation failed: {stderr}")
        logger.info(f"[CREATE] ✓ Container '{full_name}' created successfully")
    finally:
        os.unlink(config_file)
        logger.debug(f"[CREATE] Cleaned up temp config file")
    
    # Start and setup port forward
    logger.info(f"[CREATE] Starting container '{full_name}'...")
    run_cmd(["nixos-container", "start", full_name], timeout=60, description=f"start-{full_name}")
    
    logger.info(f"[CREATE] Setting up port forward for '{full_name}'...")
    setup_port_forward(req.port, ip, req.container_port)
    
    # Save to DB
    logger.info(f"[CREATE] Saving '{full_name}' to database...")
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
    logger.info(f"[CREATE] ✓ Container '{full_name}' fully deployed and saved")
    
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
    logger.info(f"[DESTROY] User '{user}' destroying container '{full_name}'")
    
    info = db.containers_db.get(full_name)
    
    if not info:
        logger.warning(f"[DESTROY] Container '{full_name}' not found in database")
        raise HTTPException(404, "Container not found")
    
    if info.get("owner") != user and not db.users_db.get(user, {}).get("is_admin"):
        logger.warning(f"[DESTROY] User '{user}' not authorized to destroy '{full_name}' (owner: {info.get('owner')})")
        raise HTTPException(403, "Not owner of this container")
    
    # Cleanup port forward
    if info.get("host_port") and info.get("ip"):
        logger.info(f"[DESTROY] Removing port forward for '{full_name}'...")
        remove_port_forward(info["host_port"], info["ip"], info.get("container_port", 80))
    
    # Destroy container
    logger.info(f"[DESTROY] Running nixos-container destroy '{full_name}'...")
    _, stderr, rc = run_cmd(["nixos-container", "destroy", full_name], timeout=60, description=f"destroy-{full_name}")
    if rc != 0 and "No such file or directory" not in stderr:
        logger.error(f"[DESTROY] Failed to destroy '{full_name}': {stderr}")
        raise HTTPException(500, f"Destroy failed: {stderr}")
    
    # Remove from DB
    if full_name in db.containers_db:
        del db.containers_db[full_name]
        save_db(CONTAINERS_DB_FILE, db.containers_db)
        logger.info(f"[DESTROY] ✓ Container '{full_name}' removed from database")
    
    logger.info(f"[DESTROY] ✓ Container '{full_name}' destroyed successfully")
    return {"success": True, "message": f"Container '{full_name}' destroyed"}


@app.post("/api/v1/projects/{project_name}/deploy", response_model=ProjectDeployResponse)
async def deploy_project(
    project_name: str,
    request: ProjectDeployRequest,
    user: str = Depends(require_user)
):
    """Deploy a project - writes files and uses nixos-container --flake."""
    logger.info("=" * 60)
    logger.info(f"[DEPLOY] Project '{project_name}' deployment started by user '{user}'")
    logger.info(f"[DEPLOY] Files received: {list(request.files.keys())}")
    
    if not re.match(r'^[a-zA-Z0-9_-]+$', project_name):
        logger.error(f"[DEPLOY] Invalid project name: '{project_name}'")
        raise HTTPException(400, "Invalid project name")
    
    if "flake.nix" not in request.files:
        logger.error(f"[DEPLOY] No flake.nix found in project files")
        raise HTTPException(400, "No flake.nix in project files")
    
    # Create temp directory
    temp_dir = tempfile.mkdtemp(prefix=f"ncp_project_{project_name}_")
    logger.info(f"[DEPLOY] Created temp directory: {temp_dir}")
    deployed, destroyed, errors = [], [], []
    
    try:
        # Write all files
        logger.info(f"[DEPLOY] Writing {len(request.files)} files to temp directory...")
        for filepath, content in request.files.items():
            full_path = os.path.join(temp_dir, filepath)
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, 'w') as f:
                f.write(content)
            logger.debug(f"[DEPLOY]   ✓ Written: {filepath} ({len(content)} bytes)")
        logger.info(f"[DEPLOY] ✓ All files written to {temp_dir}")
        
        # Get ncp.containers from flake (simple eval for ports only)
        port_cmd = f'''
let flake = builtins.getFlake (toString {temp_dir}); 
in builtins.mapAttrs (n: c: c.port) (flake.ncp.containers or {{}})
'''
        logger.info(f"[DEPLOY] Evaluating flake.nix to get container configurations...")
        stdout, stderr, rc = run_cmd(["nix", "eval", "--impure", "--json", "--expr", port_cmd], 
                                     timeout=60, description="eval-flake")
        
        if rc != 0:
            logger.error(f"[DEPLOY] Flake evaluation failed: {stderr}")
            raise HTTPException(400, f"Failed to evaluate flake.nix: {stderr}")
        
        try:
            ports = json.loads(stdout)
            logger.info(f"[DEPLOY] ✓ Flake evaluated successfully")
        except:
            logger.error(f"[DEPLOY] Failed to parse flake evaluation output")
            raise HTTPException(400, "No ncp.containers defined in flake.nix")
        
        if not ports:
            logger.error(f"[DEPLOY] No ncp.containers defined in flake.nix")
            raise HTTPException(400, "No ncp.containers defined in flake.nix")
        
        logger.info(f"[DEPLOY] Desired containers from flake: {list(ports.keys())}")
        logger.info(f"[DEPLOY] Port mappings: {ports}")
        
        # Get current containers for this project
        existing = get_all_containers()
        current = {n: i for n, i in db.containers_db.items() 
                   if i.get('owner') == user and i.get('project') == project_name and n in existing}
        
        logger.info(f"[DEPLOY] Current containers for project '{project_name}': {list(current.keys())}")
        
        desired = set(ports.keys())
        current_names = set(current.keys())
        
        # Destroy obsolete
        to_destroy = current_names - desired
        if to_destroy:
            logger.info(f"[DEPLOY] Destroying {len(to_destroy)} obsolete containers: {list(to_destroy)}")
            for name in to_destroy:
                full_name = name[:12]
                info = db.containers_db.get(full_name, {})
                if info.get('host_port') and info.get('ip'):
                    logger.info(f"[DEPLOY]   Removing port forward for '{full_name}'...")
                    remove_port_forward(info['host_port'], info['ip'], info.get('container_port', 80))
                logger.info(f"[DEPLOY]   Destroying container '{full_name}'...")
                run_cmd(["nixos-container", "destroy", full_name], timeout=60, description=f"destroy-{full_name}")
                if full_name in db.containers_db:
                    del db.containers_db[full_name]
                    save_db(CONTAINERS_DB_FILE, db.containers_db)
                destroyed.append(full_name)
                logger.info(f"[DEPLOY]   ✓ Destroyed '{full_name}'")
        else:
            logger.info(f"[DEPLOY] No obsolete containers to destroy")
        
        # Create new containers using parallel builds
        new_containers = list(desired - current_names)
        output_paths = {}
        
        if new_containers:
            logger.info(f"[DEPLOY] Building {len(new_containers)} new containers: {new_containers}")
            # Build all outputs at once: nix build .#nixosConfigurations.container1.config.system.build.toplevel ...
            build_targets = [f"{temp_dir}#nixosConfigurations.{name}.config.system.build.toplevel" for name in new_containers]
            logger.info(f"[DEPLOY] Build targets: {build_targets}")
            
            logger.info(f"[DEPLOY] Starting parallel nix build (timeout=600s)...")
            stdout, stderr, rc = run_cmd(
                ["nix", "build", "--no-link", "--json"] + build_targets,
                timeout=600, description="nix-build-all"
            )
            
            if rc != 0:
                logger.error(f"[DEPLOY] Build failed: {stderr}")
                raise HTTPException(500, f"Parallel build failed: {stderr}")
            
            logger.info(f"[DEPLOY] ✓ Build completed successfully")
            
            # Parse build results to get output paths
            try:
                build_results = json.loads(stdout)
                # nix build --json returns array of {drvPath, outputs: {out: path}}
                for i, result in enumerate(build_results):
                    name = new_containers[i]
                    out_path = result.get("outputs", {}).get("out")
                    if out_path:
                        output_paths[name] = out_path
                        logger.info(f"[DEPLOY]   Built: {name} -> {out_path}")
            except Exception as e:
                logger.error(f"[DEPLOY] Failed to parse build results: {e}")
                errors.append(f"Failed to parse build results: {e}")
        else:
            logger.info(f"[DEPLOY] No new containers to build")
        
        # Create containers from pre-built system paths
        if new_containers:
            logger.info(f"[DEPLOY] Creating {len(new_containers)} containers from pre-built paths...")
        
        for name in new_containers:
            full_name = name[:12]
            host_port = ports.get(name)
            system_path = output_paths.get(name)
            
            logger.info(f"[DEPLOY] Creating container '{full_name}' (port {host_port})...")
            
            if not host_port:
                logger.error(f"[DEPLOY]   No port specified for '{full_name}'")
                errors.append(f"{full_name}: no port specified")
                continue
            
            if not system_path:
                logger.error(f"[DEPLOY]   No system path for '{full_name}' - build may have failed")
                errors.append(f"{full_name}: build did not produce output")
                continue
            
            logger.info(f"[DEPLOY]   Allocating IP for '{full_name}'...")
            ip = find_next_available_ip()
            if not ip:
                logger.error(f"[DEPLOY]   No available IPs for '{full_name}'")
                errors.append(f"{full_name}: no available IPs")
                continue
            logger.info(f"[DEPLOY]   Allocated IP: {ip}")
            
            # Create using pre-built system path (fast - no building)
            logger.info(f"[DEPLOY]   Creating container '{full_name}' from {system_path}...")
            stdout, stderr, rc = run_cmd([
                "nixos-container", "create", full_name,
                "--system-path", system_path,
                "--host-address", CONTAINER_HOST_IP,
                "--local-address", ip
            ], timeout=60, description=f"create-{full_name}")  # Much shorter timeout - just copying
            
            # If container already exists, destroy and retry
            if rc != 0 and "already exists" in stderr:
                logger.warning(f"[DEPLOY]   Container '{full_name}' already exists, destroying and retrying...")
                run_cmd(["nixos-container", "destroy", full_name], timeout=30, description=f"destroy-retry-{full_name}")
                stdout, stderr, rc = run_cmd([
                    "nixos-container", "create", full_name,
                    "--system-path", system_path,
                    "--host-address", CONTAINER_HOST_IP,
                    "--local-address", ip
                ], timeout=60, description=f"create-retry-{full_name}")
            
            if rc != 0:
                logger.error(f"[DEPLOY]   Failed to create '{full_name}': {stderr}")
                errors.append(f"{full_name}: creation failed - {stderr}")
                continue
            
            logger.info(f"[DEPLOY]   Starting container '{full_name}'...")
            run_cmd(["nixos-container", "start", full_name], timeout=60, description=f"start-{full_name}")
            
            logger.info(f"[DEPLOY]   Setting up port forward {host_port} -> {ip}:80...")
            setup_port_forward(host_port, ip, 80)  # Assume port 80 inside
            
            logger.info(f"[DEPLOY]   Saving '{full_name}' to database...")
            db.containers_db[full_name] = {
                "ip": ip,
                "host_port": host_port,
                "container_port": 80,
                "status": "up",
                "owner": user,
                "project": project_name,
                "created_at": datetime.now().isoformat(),
                "system_path": system_path  # Track the built path
            }
            save_db(CONTAINERS_DB_FILE, db.containers_db)
            
            deployed.append(ContainerInfo(
                name=full_name, status="up", ip=ip,
                host_port=host_port,
                created_at=db.containers_db[full_name]["created_at"],
                owner=user
            ))
            logger.info(f"[DEPLOY]   ✓ Container '{full_name}' deployed successfully")
    
    finally:
        logger.info(f"[DEPLOY] Cleaning up temp directory: {temp_dir}")
        shutil.rmtree(temp_dir, ignore_errors=True)
    
    msgs = []
    if deployed:
        msgs.append(f"Created {len(deployed)} containers: {[c.name for c in deployed]}")
    if destroyed:
        msgs.append(f"Removed {len(destroyed)} obsolete containers: {destroyed}")
    if errors:
        msgs.append(f"{len(errors)} errors: {'; '.join(errors[:3])}")
    
    message = ", ".join(msgs) if msgs else "No changes"
    logger.info(f"[DEPLOY] Deployment complete: {message}")
    logger.info("=" * 60)
    
    return ProjectDeployResponse(
        project=project_name,
        containers=deployed,
        message=message
    )


# Auth endpoints
@app.post("/api/v1/auth/register")
async def register(user: UserRegister):
    """Register a new user."""
    logger.info(f"[AUTH] Registration attempt for username: '{user.username}'")
    
    if user.username in db.users_db:
        logger.warning(f"[AUTH] Registration failed: username '{user.username}' already exists")
        raise HTTPException(400, "Username already exists")
    
    db.users_db[user.username] = {
        "username": user.username,
        "password_hash": hash_password(user.password),
        "email": user.email,
        "created_at": datetime.now().isoformat(),
        "is_admin": False
    }
    save_db(USERS_DB_FILE, db.users_db)
    logger.info(f"[AUTH] ✓ User '{user.username}' registered successfully")
    
    token = create_access_token({"sub": user.username})
    logger.info(f"[AUTH] Token created for '{user.username}'")
    return TokenResponse(access_token=token)


@app.post("/api/v1/auth/login", response_model=TokenResponse)
async def login(creds: UserLogin):
    """Login and get access token."""
    logger.info(f"[AUTH] Login attempt for username: '{creds.username}'")
    
    user = db.users_db.get(creds.username)
    if not user or not verify_password(creds.password, user["password_hash"]):
        logger.warning(f"[AUTH] Login failed for '{creds.username}': invalid credentials")
        raise HTTPException(401, "Invalid credentials")
    
    logger.info(f"[AUTH] ✓ User '{creds.username}' logged in successfully")
    token = create_access_token({"sub": creds.username})
    return TokenResponse(access_token=token)


@app.get("/api/v1/auth/me")
async def me(user: str = Depends(require_user)):
    """Get current user info."""
    info = db.users_db.get(user, {})
    logger.debug(f"[AUTH] User info request for '{user}' (admin={info.get('is_admin', False)})")
    return {"username": user, "is_admin": info.get("is_admin", False)}


# Secrets endpoints
@app.get("/api/v1/secrets")
async def list_secrets(user: str = Depends(require_user)):
    """List available secrets for the user."""
    logger.info(f"[SECRETS] User '{user}' listing secrets")
    
    secrets_dir = Path("/var/lib/ncp/secrets")
    if not secrets_dir.exists():
        return {"secrets": []}
    
    secrets = [f.name for f in secrets_dir.glob("*.age")]
    logger.info(f"[SECRETS] Found {len(secrets)} secrets")
    return {"secrets": secrets}


@app.post("/api/v1/secrets/{secret_name}")
async def upload_secret(
    secret_name: str,
    request: Request,
    user: str = Depends(require_user)
):
    """Upload an encrypted secret file."""
    logger.info(f"[SECRETS] User '{user}' uploading secret '{secret_name}'")
    
    # Ensure .age extension
    if not secret_name.endswith('.age'):
        secret_name = f"{secret_name}.age"
    
    secrets_dir = Path("/var/lib/ncp/secrets")
    secrets_dir.mkdir(parents=True, exist_ok=True)
    
    secret_path = secrets_dir / secret_name
    
    # Read the encrypted content from request body
    content = await request.body()
    
    # Validate it looks like an age-encrypted file
    if not content.startswith(b'age-encryption'):
        logger.warning(f"[SECRETS] Invalid age encryption format for '{secret_name}'")
        raise HTTPException(400, "Invalid age encryption format")
    
    # Write the secret
    with open(secret_path, 'wb') as f:
        f.write(content)
    
    os.chmod(secret_path, 0o600)
    
    logger.info(f"[SECRETS] ✓ Secret '{secret_name}' saved ({len(content)} bytes)")
    return {"success": True, "secret": secret_name, "size": len(content)}


@app.get("/api/v1/secrets/{secret_name}")
async def get_secret(secret_name: str, user: str = Depends(require_user)):
    """Get a secret (returns encrypted content)."""
    logger.info(f"[SECRETS] User '{user}' retrieving secret '{secret_name}'")
    
    if not secret_name.endswith('.age'):
        secret_name = f"{secret_name}.age"
    
    secret_path = Path("/var/lib/ncp/secrets") / secret_name
    
    if not secret_path.exists():
        logger.warning(f"[SECRETS] Secret '{secret_name}' not found")
        raise HTTPException(404, "Secret not found")
    
    with open(secret_path, 'rb') as f:
        content = f.read()
    
    logger.info(f"[SECRETS] ✓ Secret '{secret_name}' retrieved ({len(content)} bytes)")
    return Response(content=content, media_type="application/octet-stream")


@app.delete("/api/v1/secrets/{secret_name}")
async def delete_secret(secret_name: str, user: str = Depends(require_user)):
    """Delete a secret."""
    logger.info(f"[SECRETS] User '{user}' deleting secret '{secret_name}'")
    
    if not secret_name.endswith('.age'):
        secret_name = f"{secret_name}.age"
    
    secret_path = Path("/var/lib/ncp/secrets") / secret_name
    
    if not secret_path.exists():
        logger.warning(f"[SECRETS] Secret '{secret_name}' not found")
        raise HTTPException(404, "Secret not found")
    
    secret_path.unlink()
    logger.info(f"[SECRETS] ✓ Secret '{secret_name}' deleted")
    return {"success": True, "message": f"Secret '{secret_name}' deleted"}


# Admin endpoints
@app.post("/api/v1/admin/setup-nixbuild")
async def setup_nixbuild(user: str = Depends(require_user)):
    """Setup nixbuild.net remote builder (admin only)."""
    logger.info(f"[ADMIN] nixbuild.net setup requested by user '{user}'")
    
    if not db.users_db.get(user, {}).get("is_admin"):
        logger.warning(f"[ADMIN] User '{user}' is not an admin - setup denied")
        raise HTTPException(403, "Admin required")
    
    logger.info(f"[ADMIN] Running nixbuild.net setup...")
    success, message = setup_nixbuild_net()
    
    if success:
        logger.info(f"[ADMIN] ✓ nixbuild.net setup: {message}")
    else:
        logger.error(f"[ADMIN] ✗ nixbuild.net setup failed: {message}")
    
    return {"success": success, "message": message}


@app.on_event("startup")
async def startup_event():
    """Log startup information."""
    logger.info("=" * 60)
    logger.info("🚀 NCP API Server Starting")
    logger.info("=" * 60)
    logger.info(f"[STARTUP] Host: {API_HOST}, Port: {API_PORT}")
    logger.info(f"[STARTUP] Container Subnet: {CONTAINER_SUBNET}, Host IP: {CONTAINER_HOST_IP}")
    logger.info(f"[STARTUP] Data Directory: {db.DATA_DIR}")
    logger.info(f"[STARTUP] Nixbuild Host: {NIXBUILD_HOST}")
    
    container_count = len(db.containers_db)
    user_count = len(db.users_db)
    logger.info(f"[STARTUP] Loaded {container_count} containers, {user_count} users from database")
    logger.info("=" * 60)


if __name__ == "__main__":
    logger.info("[STARTUP] Initializing default admin...")
    init_default_admin()
    logger.info(f"[STARTUP] Starting uvicorn server on {API_HOST}:{API_PORT}")
    uvicorn.run(app, host=API_HOST, port=API_PORT)
