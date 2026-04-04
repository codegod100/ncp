#!/usr/bin/env python3
"""
Nix-Fly Container Management API - Dynamic Edition
Imperative container creation without nixos-rebuild
"""

import subprocess
import json
import os
import re
import tempfile
import shutil
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse, HTMLResponse, PlainTextResponse
import uvicorn
from datetime import datetime

app = FastAPI(title="NCP API", version="2.0.0")

# Container specification model
class ContainerSpec(BaseModel):
    name: str
    description: Optional[str] = None
    ip: Optional[str] = None
    host_port: Optional[int] = None
    container_port: int = 3000
    nix_config: str
    auto_start: bool = True

class ContainerInfo(BaseModel):
    name: str
    status: str
    ip: Optional[str] = None
    host_port: Optional[int] = None
    created_at: str

# Data directory for persistence
DATA_DIR = "/var/lib/nix-fly"
CONTAINERS_DB_FILE = f"{DATA_DIR}/containers.json"

# Network configuration
NETWORK_CONFIG = {
    "subnet": "10.100.0.0/16",
    "gateway": "10.100.0.1",
}

def load_db() -> Dict[str, Any]:
    """Load containers database from disk"""
    if os.path.exists(CONTAINERS_DB_FILE):
        try:
            with open(CONTAINERS_DB_FILE, 'r') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_db(db: Dict[str, Any]):
    """Save containers database to disk"""
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(CONTAINERS_DB_FILE, 'w') as f:
        json.dump(db, f, indent=2)

# In-memory state (loaded from disk)
containers_db: Dict[str, Any] = load_db()

def run_cmd(cmd: List[str], capture=True, timeout=300, cwd: Optional[str] = None) -> tuple:
    """Run shell command and return (stdout, stderr, returncode)"""
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
    """Check if container is running"""
    stdout, stderr, rc = run_cmd(["nixos-container", "status", name])
    if rc == 0:
        status = stdout.strip()
        return "up" if status == "up" else "down"
    return "unknown"

def get_all_containers():
    """List all nixos containers"""
    stdout, stderr, rc = run_cmd(["nixos-container", "list"])
    if rc == 0:
        return [n.strip() for n in stdout.strip().split('\n') if n.strip()]
    return []

def find_next_available_ip() -> Optional[str]:
    """Find next available IP in 10.100.x.x range"""
    used_ips = set()
    
    # Get IPs from running containers
    containers = get_all_containers()
    for name in containers:
        info = containers_db.get(name, {})
        if info.get("ip"):
            used_ips.add(info["ip"])
    
    # Find next available in range 10.100.1.x - 10.100.254.x
    for third in range(1, 255):
        for fourth in range(1, 255):
            ip = f"10.100.{third}.{fourth}"
            if ip not in used_ips:
                return ip
    return None

def build_container_nix(name: str, ip: str, user_config: str, host_port: Optional[int], container_port: int) -> str:
    """Build a complete NixOS container expression and return the built system path"""
    
    # Create temporary directory for the build
    tmpdir = tempfile.mkdtemp(prefix=f"nix-fly-{name}-")
    
    try:
        # Clean up the user config - extract from braces if wrapped
        cleaned_config = user_config.strip()
        if cleaned_config.startswith('{') and cleaned_config.endswith('}'):
            cleaned_config = cleaned_config[1:-1].strip()
        
        # Build a complete nixos system for the container
        # Wrap user config in a module so pkgs/lib are available
        nix_expr = f'''
let
  nixpkgs = import <nixpkgs> {{}};
in
(nixpkgs.nixos (
  {{ config, pkgs, lib, ... }}: {{
    boot.isContainer = true;
    
    networking.useDHCP = false;
    networking.useHostResolvConf = false;
    
    networking.interfaces.eth0 = {{
      ipv4.addresses = [{{
        address = "{ip}";
        prefixLength = 16;
      }}];
    }};
    networking.defaultGateway = "{NETWORK_CONFIG['gateway']}";
    networking.nameservers = [ "8.8.8.8" "1.1.1.1" ];
    
    services.openssh.enable = true;
    users.users.root.initialPassword = "root";
    
    {cleaned_config}
    
    system.stateVersion = "24.11";
  }}
)).config.system.build.toplevel
'''
        
        # Write the nix expression
        nix_file = os.path.join(tmpdir, "container.nix")
        with open(nix_file, 'w') as f:
            f.write(nix_expr)
        
        # Build it
        stdout, stderr, rc = run_cmd(
            ["nix-build", nix_file, "-o", os.path.join(tmpdir, "result")],
            timeout=600,
            cwd=tmpdir
        )
        
        if rc != 0:
            raise Exception(f"Build failed: {stderr}")
        
        result_path = os.path.join(tmpdir, "result")
        if not os.path.exists(result_path):
            raise Exception("Build completed but result not found")
        
        # Return the real path (resolve symlink)
        return os.path.realpath(result_path)
        
    except Exception as e:
        shutil.rmtree(tmpdir, ignore_errors=True)
        raise e

def create_container_imperative(name: str, system_path: str, ip: str) -> bool:
    """Create container imperatively using nixos-container with built system"""
    
    # Check if container already exists
    if name in get_all_containers():
        return False
    
    # Create container directory structure
    container_root = f"/var/lib/containers/{name}"
    os.makedirs(container_root, exist_ok=True)
    
    # Copy the built system to container root
    stdout, stderr, rc = run_cmd([
        "rsync", "-a", "--delete",
        f"{system_path}/",
        f"{container_root}/"
    ], timeout=120)
    
    if rc != 0:
        # Try cp -r if rsync fails
        run_cmd(["rm", "-rf", container_root])
        stdout, stderr, rc = run_cmd([
            "cp", "-r", f"{system_path}/.", container_root
        ], timeout=120)
        if rc != 0:
            raise Exception(f"Failed to copy system: {stderr}")
    
    # Create the container using nixos-container
    stdout, stderr, rc = run_cmd([
        "nixos-container", "create", name,
        "--ensure-running" if True else "",
        "--host-address", NETWORK_CONFIG["gateway"],
        "--local-address", ip
    ])
    
    if rc != 0:
        raise Exception(f"Container creation failed: {stderr}")
    
    return True

def setup_port_forward(name: str, host_port: int, container_ip: str, container_port: int):
    """Setup iptables port forwarding"""
    # Add PREROUTING rule
    stdout, stderr, rc = run_cmd([
        "iptables", "-t", "nat", "-A", "PREROUTING",
        "-p", "tcp", "--dport", str(host_port),
        "-j", "DNAT", "--to-destination", f"{container_ip}:{container_port}"
    ])
    if rc != 0:
        print(f"Warning: Failed to add PREROUTING rule: {stderr}")
    
    # Add POSTROUTING rule
    stdout, stderr, rc = run_cmd([
        "iptables", "-t", "nat", "-A", "POSTROUTING",
        "-p", "tcp", "--dport", str(container_port),
        "-d", container_ip,
        "-j", "MASQUERADE"
    ])
    if rc != 0:
        print(f"Warning: Failed to add POSTROUTING rule: {stderr}")

def remove_port_forward(host_port: int, container_ip: str, container_port: int):
    """Remove iptables port forwarding"""
    # Remove PREROUTING rule
    run_cmd([
        "iptables", "-t", "nat", "-D", "PREROUTING",
        "-p", "tcp", "--dport", str(host_port),
        "-j", "DNAT", "--to-destination", f"{container_ip}:{container_port}"
    ])
    
    # Remove POSTROUTING rule
    run_cmd([
        "iptables", "-t", "nat", "-D", "POSTROUTING",
        "-p", "tcp", "--dport", str(container_port),
        "-d", container_ip,
        "-j", "MASQUERADE"
    ])

@app.get("/")
async def root():
    """API root with documentation"""
    return {
        "service": "nix-fly-api",
        "version": "2.0.0",
        "description": "Dynamic NixOS container deployment via NCP (no rebuilds!)",
        "endpoints": {
            "GET /api/v1/containers": "List all containers",
            "POST /api/v1/containers": "Create and start container immediately (dynamic)",
            "GET /api/v1/containers/{name}": "Get container details",
            "POST /api/v1/containers/{name}/restart": "Restart container",
            "DELETE /api/v1/containers/{name}": "Destroy container immediately (dynamic)",
            "GET /api/v1/containers/{name}/logs": "Stream container logs",
        }
    }

@app.get("/api/v1/containers", response_model=List[ContainerInfo])
async def list_containers():
    """List all containers"""
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
            created_at=info.get("created_at", "unknown")
        ))
    
    return containers

@app.post("/api/v1/containers", response_model=ContainerInfo)
async def create_container(spec: ContainerSpec):
    """Create and start a container immediately (no apply needed!)"""
    
    # Validate name
    if not re.match(r'^[a-zA-Z0-9_-]+$', spec.name):
        raise HTTPException(status_code=400, detail="Invalid container name. Use alphanumeric, dash, underscore.")
    
    # Check if exists
    existing = get_all_containers()
    if spec.name in existing:
        raise HTTPException(status_code=409, detail=f"Container {spec.name} already exists")
    
    # Auto-assign IP
    if not spec.ip:
        spec.ip = find_next_available_ip()
    
    if not spec.ip:
        raise HTTPException(status_code=500, detail="No available IPs in range")
    
    try:
        # Build the container system
        print(f"Building container {spec.name}...")
        system_path = build_container_nix(
            spec.name,
            spec.ip,
            spec.nix_config,
            spec.host_port,
            spec.container_port
        )
        
        # Create the container imperatively
        print(f"Creating container {spec.name}...")
        create_container_imperative(spec.name, system_path, spec.ip)
        
        # Setup port forwarding if requested
        if spec.host_port:
            print(f"Setting up port forward {spec.host_port} -> {spec.ip}:{spec.container_port}")
            setup_port_forward(spec.name, spec.host_port, spec.ip, spec.container_port)
        
        # Store metadata
        containers_db[spec.name] = {
            "ip": spec.ip,
            "host_port": spec.host_port,
            "container_port": spec.container_port,
            "created_at": datetime.now().isoformat(),
            "config": spec.nix_config,
            "system_path": system_path,
            "status": "up"
        }
        save_db(containers_db)
        
    except Exception as e:
        # Cleanup on failure
        if spec.name in get_all_containers():
            run_cmd(["nixos-container", "destroy", spec.name])
        raise HTTPException(status_code=500, detail=f"Failed to create container: {str(e)}")
    
    return ContainerInfo(
        name=spec.name,
        status="up",
        ip=spec.ip,
        host_port=spec.host_port,
        created_at=containers_db[spec.name]["created_at"]
    )

@app.get("/api/v1/containers/{name}", response_model=ContainerInfo)
async def get_container(name: str):
    """Get container details"""
    if name not in get_all_containers():
        raise HTTPException(status_code=404, detail=f"Container {name} not found")
    
    status = get_container_status(name)
    info = containers_db.get(name, {})
    
    return ContainerInfo(
        name=name,
        status=status,
        ip=info.get("ip"),
        host_port=info.get("host_port"),
        created_at=info.get("created_at", "unknown")
    )

@app.post("/api/v1/containers/{name}/restart")
async def restart_container(name: str):
    """Restart a container"""
    if name not in get_all_containers():
        raise HTTPException(status_code=404, detail=f"Container {name} not found")
    
    stdout, stderr, rc = run_cmd(["nixos-container", "stop", name], timeout=30)
    if rc != 0:
        raise HTTPException(status_code=500, detail=f"Failed to stop: {stderr}")
    
    stdout, stderr, rc = run_cmd(["nixos-container", "start", name], timeout=30)
    if rc != 0:
        raise HTTPException(status_code=500, detail=f"Failed to start: {stderr}")
    
    return {
        "name": name,
        "action": "restart",
        "new_status": get_container_status(name)
    }

@app.delete("/api/v1/containers/{name}")
async def destroy_container(name: str):
    """Destroy a container immediately (no apply needed!)"""
    if name not in get_all_containers():
        raise HTTPException(status_code=404, detail=f"Container {name} not found")
    
    # Remove port forwarding if configured
    info = containers_db.get(name, {})
    if info.get("host_port") and info.get("ip"):
        remove_port_forward(
            info["host_port"],
            info["ip"],
            info.get("container_port", 3000)
        )
    
    # Destroy the container
    stdout, stderr, rc = run_cmd(["nixos-container", "destroy", name], timeout=60)
    if rc != 0:
        raise HTTPException(status_code=500, detail=f"Failed to destroy: {stderr}")
    
    # Remove from database
    if name in containers_db:
        del containers_db[name]
        save_db(containers_db)
    
    return {
        "name": name,
        "action": "destroyed",
        "status": "deleted"
    }

@app.get("/api/v1/containers/{name}/logs")
async def container_logs(name: str, follow: bool = False, lines: int = 100):
    """Get container logs"""
    if name not in get_all_containers():
        raise HTTPException(status_code=404, detail=f"Container {name} not found")
    
    def log_generator():
        cmd = ["nixos-container", "run", name, "--", "journalctl"]
        if follow:
            cmd.extend(["-f"])
        else:
            cmd.extend(["-n", str(lines)])
        
        process = subprocess.Popen(
            cmd, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.STDOUT, 
            text=True,
            bufsize=1
        )
        try:
            for line in process.stdout:
                yield line
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except:
                process.kill()
    
    return StreamingResponse(log_generator(), media_type="text/plain")

@app.get("/api/v1/nix-config/{name}")
async def get_nix_config(name: str):
    """Get the NixOS configuration for a container"""
    info = containers_db.get(name)
    if not info:
        raise HTTPException(status_code=404, detail=f"Config for {name} not found")
    
    return PlainTextResponse(info.get("config", "# No config stored"))

@app.get("/docs-ui", response_class=HTMLResponse)
async def docs_ui():
    """Simple HTML UI for API docs"""
    return """
<!DOCTYPE html>
<html>
<head>
    <title>Nix-Fly API</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; max-width: 900px; margin: 40px auto; padding: 20px; line-height: 1.6; }
        code { background: #f4f4f4; padding: 2px 6px; border-radius: 3px; font-size: 0.9em; }
        pre { background: #f4f4f4; padding: 15px; overflow-x: auto; border-radius: 5px; }
        .endpoint { margin: 20px 0; padding: 15px; border-left: 4px solid #007acc; background: #f9f9f9; border-radius: 0 5px 5px 0; }
        .method { font-weight: bold; color: #007acc; }
        h1 { color: #333; }
        h2 { color: #555; border-bottom: 2px solid #eee; padding-bottom: 5px; }
        .note { background: #d4edda; padding: 10px 15px; border-radius: 5px; border-left: 4px solid #28a745; }
    </style>
</head>
<body>
    <h1>🚀 Nix-Fly API v2.0</h1>
    <p>Dynamic Fly.io-style container deployment for NixOS</p>
    
    <div class="note">
        <strong>✅ Dynamic Mode:</strong> Containers are created and started immediately using 
        <code>nixos-container</code> with imperative management. No <code>nixos-rebuild switch</code> needed!
    </div>
    
    <h2>Quick Start</h2>
    <pre><code># List containers
curl https://nix.latha.org/fly/api/v1/containers

# Deploy a container (starts immediately!)
curl -X POST https://nix.latha.org/fly/api/v1/containers \\
  -H "Content-Type: application/json" \\
  -d '{"name": "myapp", "nix_config": "{ services.nginx.enable = true; networking.firewall.allowedTCPPorts = [ 80 ]; }", "host_port": 8080}'

# Container is running immediately - no apply needed!</code></pre>
    
    <h2>Endpoints</h2>
    <div class="endpoint">
        <span class="method">GET</span> <strong>/api/v1/containers</strong> - List all containers
    </div>
    <div class="endpoint">
        <span class="method">POST</span> <strong>/api/v1/containers</strong> - Create and start container immediately
        <pre>{"name": "my-app", "nix_config": "{ ... }", "host_port": 8080}</pre>
    </div>
    <div class="endpoint">
        <span class="method">GET</span> <strong>/api/v1/containers/{name}</strong> - Container details
    </div>
    <div class="endpoint">
        <span class="method">POST</span> <strong>/api/v1/containers/{name}/restart</strong> - Restart container
    </div>
    <div class="endpoint">
        <span class="method">DELETE</span> <strong>/api/v1/containers/{name}</strong> - Destroy container immediately
    </div>
    <div class="endpoint">
        <span class="method">GET</span> <strong>/api/v1/containers/{name}/logs</strong> - Stream logs
    </div>
    
    <h2>Container Config</h2>
    <p>The <code>nix_config</code> field is a Nix expression that gets merged into the container's configuration:</p>
    <pre><code>{
  services.nginx = {
    enable = true;
    virtualHosts.default.root = "${pkgs.nginx}/html";
  };
  networking.firewall.allowedTCPPorts = [ 80 ];
}</code></pre>
    
    <p><em>Networking and base system are configured automatically.</em></p>
</body>
</html>
"""

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
