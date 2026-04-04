#!/usr/bin/env python3
"""
NCP Container Management API - Dynamic Edition
Uses nixos-container with inline config for proper container lifecycle
"""

import subprocess
import json
import os
import re
import tempfile
import shutil
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse, HTMLResponse, PlainTextResponse
import uvicorn
from datetime import datetime

app = FastAPI(title="NCP API", version="2.1.0")

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

DATA_DIR = "/var/lib/ncp"
CONTAINERS_DB_FILE = f"{DATA_DIR}/containers.json"

NETWORK_CONFIG = {
    "subnet": "10.100.0.0/16",
    "gateway": "10.100.0.1",
}

def load_db() -> Dict[str, Any]:
    if os.path.exists(CONTAINERS_DB_FILE):
        try:
            with open(CONTAINERS_DB_FILE, 'r') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_db(db: Dict[str, Any]):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(CONTAINERS_DB_FILE, 'w') as f:
        json.dump(db, f, indent=2)

containers_db: Dict[str, Any] = load_db()

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

def build_container_config(name: str, ip: str, user_config: str) -> str:
    """Build a NixOS container configuration string (just the body, not a function)"""
    cleaned_config = user_config.strip()
    # If user wrapped in { }, extract just the body
    if cleaned_config.startswith('{') and cleaned_config.endswith('}'):
        # Count braces to find matching end
        depth = 0
        end_pos = 0
        for i, c in enumerate(cleaned_config):
            if c == '{':
                depth += 1
            elif c == '}':
                depth -= 1
                if depth == 0:
                    end_pos = i
                    break
        cleaned_config = cleaned_config[1:end_pos].strip()
    
    return f'''
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
'''

@app.get("/")
async def root():
    return {
        "service": "ncp-api",
        "version": "2.1.0",
        "description": "Dynamic NixOS container deployment",
    }

@app.get("/api/v1/containers", response_model=List[ContainerInfo])
async def list_containers():
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
    if not re.match(r'^[a-zA-Z0-9_-]+$', spec.name):
        raise HTTPException(status_code=400, detail="Invalid container name")
    
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
        
        # Create container with inline config - let nixos-container handle the build
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
            # Try to get status even if start failed
            status = get_container_status(spec.name)
            if status != "up":
                raise Exception(f"Container start failed: {stderr}")
        
        # Setup port forwarding
        if spec.host_port:
            setup_port_forward(spec.host_port, spec.ip, spec.container_port)
        
        # Save metadata
        containers_db[spec.name] = {
            "ip": spec.ip,
            "host_port": spec.host_port,
            "container_port": spec.container_port,
            "created_at": datetime.now().isoformat(),
            "config": spec.nix_config,
            "status": "up"
        }
        save_db(containers_db)
        
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
        created_at=containers_db[spec.name]["created_at"]
    )

@app.get("/api/v1/containers/{name}", response_model=ContainerInfo)
async def get_container(name: str):
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
    if name not in get_all_containers():
        raise HTTPException(status_code=404, detail=f"Container {name} not found")
    
    run_cmd(["nixos-container", "stop", name], timeout=30)
    stdout, stderr, rc = run_cmd(["nixos-container", "start", name], timeout=30)
    
    if rc != 0:
        raise HTTPException(status_code=500, detail=f"Failed to start: {stderr}")
    
    return {"name": name, "action": "restart", "new_status": get_container_status(name)}

@app.delete("/api/v1/containers/{name}")
async def destroy_container(name: str):
    if name not in get_all_containers():
        raise HTTPException(status_code=404, detail=f"Container {name} not found")
    
    # Remove port forwarding
    info = containers_db.get(name, {})
    if info.get("host_port") and info.get("ip"):
        remove_port_forward(info["host_port"], info["ip"], info.get("container_port", 80))
    
    stdout, stderr, rc = run_cmd(["nixos-container", "destroy", name], timeout=60)
    if rc != 0:
        raise HTTPException(status_code=500, detail=f"Failed to destroy: {stderr}")
    
    if name in containers_db:
        del containers_db[name]
        save_db(containers_db)
    
    return {"name": name, "action": "destroyed"}

@app.get("/api/v1/containers/{name}/logs")
async def container_logs(name: str, follow: bool = False, lines: int = 100):
    if name not in get_all_containers():
        raise HTTPException(status_code=404, detail=f"Container {name} not found")
    
    def log_generator():
        cmd = ["nixos-container", "run", name, "--", "journalctl"]
        if follow:
            cmd.extend(["-f"])
        else:
            cmd.extend(["-n", str(lines)])
        
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
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

@app.get("/docs-ui", response_class=HTMLResponse)
async def docs_ui():
    return """<!DOCTYPE html>
<html>
<head><title>NCP API</title><style>
body{font-family:sans-serif;max-width:900px;margin:40px auto;padding:20px}
code{background:#f4f4f4;padding:2px 6px;border-radius:3px}
pre{background:#f4f4f4;padding:15px;overflow-x:auto;border-radius:5px}
.endpoint{margin:20px 0;padding:15px;border-left:4px solid #007acc;background:#f9f9f9}
.method{font-weight:bold;color:#007acc}
</style></head>
<body>
<h1>🚀 NCP API</h1>
<p>Dynamic NixOS container deployment</p>

<h2>Endpoints</h2>
<div class="endpoint"><span class="method">GET</span> /api/v1/containers - List containers</div>
<div class="endpoint"><span class="method">POST</span> /api/v1/containers - Create container</div>
<div class="endpoint"><span class="method">GET</span> /api/v1/containers/{name} - Container details</div>
<div class="endpoint"><span class="method">POST</span> /api/v1/containers/{name}/restart - Restart</div>
<div class="endpoint"><span class="method">DELETE</span> /api/v1/containers/{name} - Destroy</div>

<h2>Example</h2>
<pre>curl -X POST https://nix.latha.org/api/api/v1/containers \\
  -H "Content-Type: application/json" \\
  -d '{"name":"myapp","nix_config":"{services.nginx.enable=true;}","host_port":8080}'</pre>
</body>
</html>"""

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
