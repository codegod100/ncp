#!/usr/bin/env python3
"""
Deploy NCP container examples
Usage: python3 deploy.py backend-api.nix my-backend 9001
"""
import json
import sys
import subprocess

def read_nix_file(path):
    """Read a .nix file and return its contents as a string."""
    with open(path, 'r') as f:
        return f.read()

def deploy_container(name, nix_config, host_port, api_url="https://nix.latha.org/api/v1", token=None):
    """Deploy container via ncp API."""
    if token is None:
        print("Error: Need authentication token")
        print("Get one with: curl -X POST https://nix.latha.org/api/v1/auth/login ...")
        sys.exit(1)
    
    payload = {
        "name": name,
        "nix_config": nix_config,
        "host_port": int(host_port),
        "container_port": 80
    }
    
    # Use curl to POST
    cmd = [
        "curl", "-s", "-X", "POST",
        f"{api_url}/containers",
        "-H", f"Authorization: Bearer {token}",
        "-H", "Content-Type: application/json",
        "-d", json.dumps(payload)
    ]
    
    print(f"Deploying {name} on port {host_port}...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    print(result.stdout)
    if result.returncode != 0:
        print("Error:", result.stderr)

if __name__ == "__main__":
    import os
    
    # Check args
    if len(sys.argv) < 4:
        print("Usage: python3 deploy.py <config.nix> <container-name> <host-port>")
        print("Example: python3 deploy.py backend-api.nix my-api 9001")
        sys.exit(1)
    
    nix_file = sys.argv[1]
    name = sys.argv[2]
    port = sys.argv[3]
    
    # Get token from environment
    token = os.environ.get("NCP_TOKEN")
    if not token:
        print("Error: Set NCP_TOKEN environment variable")
        print("export NCP_TOKEN=$(curl -s -X POST https://nix.latha.org/api/v1/auth/login ...)")
        sys.exit(1)
    
    # Read config
    try:
        config = read_nix_file(nix_file)
    except FileNotFoundError:
        print(f"Error: {nix_file} not found")
        sys.exit(1)
    
    # Deploy
    deploy_container(name, config, port, token=token)
