#!/usr/bin/env python3
"""
Nix-Fly Container Management API
Fly.io-style container deployment for NixOS
"""

import subprocess
import json
import os
import re
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse, HTMLResponse, PlainTextResponse
import uvicorn
from datetime import datetime

app = FastAPI(title="Nix-Fly API", version="1.0.0")

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

def run_cmd(cmd: List[str], capture=True, timeout=60, cwd: Optional[str] = None) -> tuple:
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
        # Try to get IP from container status
        stdout, _, rc = run_cmd(["nixos-container", "run", name, "--", "hostname", "-I"])
        if rc == 0:
            ips = stdout.strip().split()
            for ip in ips:
                if ip.startswith("10.100."):
                    used_ips.add(ip)
                    break
    
    # Also check our database
    for c in containers_db.values():
        if c.get("ip"):
            used_ips.add(c["ip"])
    
    # Find available IP in 10.100.10.x range
    for i in range(10, 250):
        candidate = f"10.100.10.{i}"
        if candidate not in used_ips:
            return candidate
    
    return None

def write_container_nix(name: str, ip: str, nix_config: str, host_port: Optional[int], container_port: int) -> str:
    """Write container configuration to /etc/nix-fly/containers/{name}.nix"""
    config_dir = "/etc/nix-fly/containers"
    os.makedirs(config_dir, exist_ok=True)
    
    config_file = f"{config_dir}/{name}.nix"
    
    # Strip the leading '{ config, pkgs, lib, ... }:' from nix_config if present
    # to avoid duplication since we wrap it ourselves
    cleaned_config = nix_config.strip()
    if cleaned_config.startswith('{'):
        # Find the matching closing brace for the args
        # Pattern: { config, pkgs, lib, ... }: or { ... }:
        match = re.match(r'\s*\{[^}]*\}\s*:\s*(.*)', cleaned_config, re.DOTALL)
        if match:
            cleaned_config = match.group(1).strip()
    
    # Create proper NixOS container config
    config_content = f'''{{ config, pkgs, lib, ... }}:

{{
  # Container: {name}
  containers.{name} = {{
    autoStart = true;
    ephemeral = false;
    privateNetwork = true;
    hostAddress = "10.100.0.1";
    localAddress = "{ip}";
    
    config = {{ config, pkgs, lib, ... }}: {cleaned_config};
  }};
'''
    
    if host_port:
        config_content += f'''  
  # Port forwarding firewall rules
  networking.firewall.extraCommands = ''
    iptables -t nat -A PREROUTING -p tcp --dport {host_port} -j DNAT --to-destination {ip}:{container_port}
    iptables -t nat -A POSTROUTING -p tcp --dport {container_port} -d {ip} -j MASQUERADE
  '';
'''
    
    config_content += '''}
'''
    
    with open(config_file, 'w') as f:
        f.write(config_content)
    
    return config_file

def generate_imports_nix():
    """Regenerate /etc/nix-fly/containers/imports.nix with all containers"""
    config_dir = "/etc/nix-fly/containers"
    os.makedirs(config_dir, exist_ok=True)
    
    # Find all .nix files except imports.nix
    configs = []
    if os.path.exists(config_dir):
        for f in os.listdir(config_dir):
            if f.endswith('.nix') and f != 'imports.nix':
                configs.append(f"./{f}")
    
    imports_content = "# Auto-generated container imports\n[\n"
    for c in configs:
        imports_content += f"  {c}\n"
    imports_content += "]\n"
    
    with open(f"{config_dir}/imports.nix", 'w') as f:
        f.write(imports_content)

@app.get("/")
async def root():
    """API root with documentation"""
    return {
        "service": "nix-fly-api",
        "version": "1.0.0",
        "description": "Fly.io-style container deployment for NixOS",
        "endpoints": {
            "GET /api/v1/containers": "List all containers",
            "POST /api/v1/containers": "Create/deploy new container (writes config, requires rebuild)",
            "GET /api/v1/containers/{name}": "Get container details",
            "POST /api/v1/containers/{name}/restart": "Restart container",
            "DELETE /api/v1/containers/{name}": "Destroy container (writes config, requires rebuild)",
            "GET /api/v1/containers/{name}/logs": "Stream container logs",
            "POST /api/v1/apply": "Apply pending container changes (rebuild NixOS)",
            "GET /api/v1/pending": "List pending container changes",
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
    """Stage a new container (writes config, requires 'apply' to activate)"""
    
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
        # Write container config
        config_file = write_container_nix(
            spec.name, 
            spec.ip, 
            spec.nix_config,
            spec.host_port,
            spec.container_port
        )
        
        # Regenerate imports
        generate_imports_nix()
        
        # Store metadata (mark as pending)
        containers_db[spec.name] = {
            "ip": spec.ip,
            "host_port": spec.host_port,
            "container_port": spec.container_port,
            "created_at": datetime.now().isoformat(),
            "config": spec.nix_config,
            "config_file": config_file,
            "status": "pending"
        }
        save_db(containers_db)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to write config: {str(e)}")
    
    return ContainerInfo(
        name=spec.name,
        status="pending",
        ip=spec.ip,
        host_port=spec.host_port,
        created_at=containers_db[spec.name]["created_at"]
    )

@app.get("/api/v1/pending")
async def list_pending():
    """List containers that need 'apply' to activate"""
    pending = []
    
    config_dir = "/etc/nix-fly/containers"
    if os.path.exists(config_dir):
        for f in os.listdir(config_dir):
            if f.endswith('.nix') and f != 'imports.nix':
                name = f[:-4]  # Remove .nix
                existing = get_all_containers()
                if name not in existing:
                    pending.append({
                        "name": name,
                        "status": "pending",
                        "action": "create",
                        "config_file": f"{config_dir}/{f}"
                    })
    
    return {"pending": pending}

@app.post("/api/v1/apply")
async def apply_changes():
    """Apply pending container changes by rebuilding NixOS"""
    pending = await list_pending()
    
    if not pending["pending"]:
        return {"message": "No pending changes", "applied": []}
    
    names = [p["name"] for p in pending["pending"]]
    
    # Run nixos-rebuild switch (this could take a while)
    stdout, stderr, rc = run_cmd(
        ["nixos-rebuild", "switch", "--flake", "/home/nixos/code/nixos-infra-host#infra-host"],
        capture=False,
        timeout=300
    )
    
    if rc != 0:
        raise HTTPException(status_code=500, detail=f"Rebuild failed: {stderr}")
    
    return {
        "message": "Applied pending changes",
        "applied": names,
        "containers": await list_containers()
    }

@app.get("/api/v1/containers/{name}", response_model=ContainerInfo)
async def get_container(name: str):
    """Get container details"""
    # Check if it's a pending container
    config_file = f"/etc/nix-fly/containers/{name}.nix"
    if os.path.exists(config_file) and name not in get_all_containers():
        info = containers_db.get(name, {})
        return ContainerInfo(
            name=name,
            status="pending",
            ip=info.get("ip"),
            host_port=info.get("host_port"),
            created_at=info.get("created_at", "unknown")
        )
    
    # Check running containers
    if name not in get_all_containers():
        raise HTTPException(status_code=404, detail=f"Container {name} not found")
    
    info = containers_db.get(name, {})
    return ContainerInfo(
        name=name,
        status=get_container_status(name),
        ip=info.get("ip"),
        host_port=info.get("host_port"),
        created_at=info.get("created_at", "unknown")
    )

@app.post("/api/v1/containers/{name}/restart")
async def restart_container(name: str):
    """Restart a container"""
    if name not in get_all_containers():
        raise HTTPException(status_code=404, detail=f"Container {name} not found")
    
    stdout, stderr, rc = run_cmd(["nixos-container", "restart", name])
    
    if rc != 0:
        raise HTTPException(status_code=500, detail=f"Failed to restart: {stderr}")
    
    return {"name": name, "status": "restarted", "new_status": get_container_status(name)}

@app.delete("/api/v1/containers/{name}")
async def destroy_container(name: str):
    """Mark container for destruction (requires 'apply' to remove)"""
    if name not in get_all_containers():
        # Check if it's just a pending config
        config_file = f"/etc/nix-fly/containers/{name}.nix"
        if os.path.exists(config_file):
            os.remove(config_file)
            generate_imports_nix()
            if name in containers_db:
                del containers_db[name]
                save_db(containers_db)
            return {"name": name, "status": "destroyed", "note": "Pending config removed"}
        
        raise HTTPException(status_code=404, detail=f"Container {name} not found")
    
    # Remove from database
    if name in containers_db:
        del containers_db[name]
        save_db(containers_db)
    
    # Remove config file
    config_file = f"/etc/nix-fly/containers/{name}.nix"
    if os.path.exists(config_file):
        os.remove(config_file)
        generate_imports_nix()
    
    # Note: Actual container destruction happens on next 'apply'
    return {
        "name": name, 
        "status": "marked_for_destruction",
        "note": "Run 'apply' to complete destruction"
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
    config_file = f"/etc/nix-fly/containers/{name}.nix"
    if not os.path.exists(config_file):
        raise HTTPException(status_code=404, detail=f"Config for {name} not found")
    
    with open(config_file, 'r') as f:
        content = f.read()
    
    return PlainTextResponse(content)

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
        .note { background: #fff3cd; padding: 10px 15px; border-radius: 5px; border-left: 4px solid #ffc107; }
    </style>
</head>
<body>
    <h1>🚀 Nix-Fly API</h1>
    <p>Fly.io-style container deployment for NixOS</p>
    
    <div class="note">
        <strong>Note:</strong> Creating/destroying containers writes NixOS configuration files to 
        <code>/etc/nix-fly/containers/</code>. You must call <code>POST /api/v1/apply</code> 
        to activate changes via <code>nixos-rebuild switch</code>.
    </div>
    
    <h2>Quick Start</h2>
    <pre><code># List containers
curl https://nix.latha.org/fly/api/v1/containers

# Deploy a container (staged, not active yet)
curl -X POST https://nix.latha.org/fly/api/v1/containers \\
  -H "Content-Type: application/json" \\
  -d '{"name": "myapp", "nix_config": "{ services.nginx.enable = true; }"}'

# Apply changes (rebuilds NixOS)
curl -X POST https://nix.latha.org/fly/api/v1/apply</code></pre>
    
    <h2>Endpoints</h2>
    <div class="endpoint">
        <span class="method">GET</span> <strong>/api/v1/containers</strong> - List all containers
    </div>
    <div class="endpoint">
        <span class="method">POST</span> <strong>/api/v1/containers</strong> - Stage new container
        <pre>{"name": "my-app", "nix_config": "{ ... }", "host_port": 8080}</pre>
    </div>
    <div class="endpoint">
        <span class="method">GET</span> <strong>/api/v1/containers/{name}</strong> - Container details
    </div>
    <div class="endpoint">
        <span class="method">POST</span> <strong>/api/v1/containers/{name}/restart</strong> - Restart container
    </div>
    <div class="endpoint">
        <span class="method">DELETE</span> <strong>/api/v1/containers/{name}</strong> - Mark for destruction
    </div>
    <div class="endpoint">
        <span class="method">GET</span> <strong>/api/v1/containers/{name}/logs?follow=true</strong> - Stream logs
    </div>
    <div class="endpoint">
        <span class="method">GET</span> <strong>/api/v1/pending</strong> - List staged changes
    </div>
    <div class="endpoint">
        <span class="method">POST</span> <strong>/api/v1/apply</strong> - Apply all staged changes (rebuild)
    </div>
    
    <h2>OpenAPI Docs</h2>
    <p><a href="/fly/docs">/fly/docs</a> - Interactive Swagger UI</p>
    <p><a href="/fly/openapi.json">/fly/openapi.json</a> - OpenAPI schema</p>
</body>
</html>
    """

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
