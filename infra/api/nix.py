"""Nix operations for container management."""

import os
import json
import subprocess
import ipaddress
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path

# Network configuration
NETWORK_CONFIG = {
    "subnet": "10.100.0.0/16",
    "gateway": "10.100.0.1",
    "host_ip": "10.100.0.1",
    "bridge": "ctrs"
}


def run_cmd(cmd: List[str], timeout: int = 30, input_data: str = None) -> Tuple[str, str, int]:
    """Run shell command and return stdout, stderr, returncode."""
    try:
        result = subprocess.run(
            cmd, 
            capture_output=True, 
            text=True, 
            timeout=timeout,
            input=input_data
        )
        return result.stdout, result.stderr, result.returncode
    except subprocess.TimeoutExpired:
        return "", f"Command timed out after {timeout}s", -1
    except Exception as e:
        return "", str(e), -1


def get_all_containers() -> List[str]:
    """Get list of all nixos containers on the system."""
    stdout, stderr, rc = run_cmd(["nixos-container", "list"])
    if rc == 0:
        return [name.strip() for name in stdout.strip().split('\n') if name.strip()]
    return []


def get_container_status(name: str) -> str:
    """Get status of a container (up/down)."""
    stdout, _, rc = run_cmd(["nixos-container", "status", name], timeout=10)
    if rc == 0 and "up" in stdout:
        return "up"
    return "down"


def get_container_ip(name: str) -> Optional[str]:
    """Get IP address of a container."""
    stdout, _, rc = run_cmd(["nixos-container", "show-ip", name], timeout=10)
    if rc == 0:
        return stdout.strip()
    return None


def setup_port_forward(host_port: int, container_ip: str, container_port: int) -> bool:
    """Setup iptables DNAT rule for port forwarding."""
    # Check if rule already exists
    stdout, _, _ = run_cmd(["iptables", "-t", "nat", "-L", "PREROUTING", "-n", "--line-numbers"])
    if f"dpt:{host_port}" in stdout:
        # Remove existing rule
        lines = stdout.strip().split('\n')
        for i, line in enumerate(lines):
            if f"dpt:{host_port}" in line and "to:" in line:
                run_cmd(["iptables", "-t", "nat", "-D", "PREROUTING", str(i)], timeout=10)
                break
    
    # Add DNAT rule
    _, stderr, rc = run_cmd([
        "iptables", "-t", "nat", "-A", "PREROUTING",
        "-p", "tcp", "--dport", str(host_port),
        "-j", "DNAT", "--to-destination", f"{container_ip}:{container_port}"
    ], timeout=10)
    
    return rc == 0


def remove_port_forward(host_port: int, container_ip: str, container_port: int) -> bool:
    """Remove iptables DNAT rule."""
    _, _, _ = run_cmd([
        "iptables", "-t", "nat", "-D", "PREROUTING",
        "-p", "tcp", "--dport", str(host_port),
        "-j", "DNAT", "--to-destination", f"{container_ip}:{container_port}"
    ], timeout=10)
    return True


def find_next_available_ip() -> Optional[str]:
    """Find next available IP in container subnet."""
    subnet = ipaddress.ip_network(NETWORK_CONFIG["subnet"])
    used_ips = set()
    
    # Get IPs from nixos-container
    containers = get_all_containers()
    for name in containers:
        ip = get_container_ip(name)
        if ip:
            try:
                used_ips.add(ipaddress.ip_address(ip))
            except ValueError:
                pass
    
    # Find first available IP (.2 through .254)
    for host in range(2, 255):
        candidate = ipaddress.ip_address(subnet.network_address + host)
        if candidate not in used_ips and candidate != ipaddress.ip_address(NETWORK_CONFIG["gateway"]):
            return str(candidate)
    
    return None


def build_container_config(name: str, ip: str, custom_config: str) -> str:
    """Build container config string."""
    base = f'''{{ 
      boot.isContainer = true;
      networking.useDHCP = false;
      networking.firewall.enable = true;
      {custom_config}
    }}'''
    return base


def parse_flake_containers_nix(temp_dir: str) -> Dict[str, Any]:
    """Parse container definitions using Nix evaluation."""
    script_dir = Path(__file__).parent
    eval_script = script_dir / "evaluate-project.nix"
    
    # Run Nix evaluation
    stdout, stderr, rc = run_cmd(
        [
            "nix", "eval", "--impure", "--json",
            "--expr", f'import {eval_script} {{ projectPath = {temp_dir}; }}'
        ],
        timeout=120
    )
    
    if rc != 0:
        print(f"Nix eval failed: {stderr}")
        return {}
    
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError as e:
        print(f"Failed to parse JSON: {e}")
        return {}
    
    # Convert to simpler format
    containers = {}
    for name, info in data.items():
        config_nix = convert_config_to_nix(info.get("config", {}))
        containers[name] = {
            "port": info.get("port"),
            "containerPort": info.get("containerPort", 80),
            "config": config_nix
        }
    
    return containers


def convert_config_to_nix(config: dict) -> str:
    """Convert structured config from Nix eval to Nix expression string."""
    def convert(val):
        if not isinstance(val, dict):
            return "{}"
        
        t = val.get("_type")
        v = val.get("value")
        
        if t == "string":
            escaped = v.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
            return f'"{escaped}"'
        elif t == "int":
            return str(v)
        elif t == "bool":
            return "true" if v else "false"
        elif t == "list":
            elements = [convert(item) for item in v]
            return "[ " + " ".join(elements) + " ]"
        elif t == "attrs":
            attrs = [f"{k} = {convert(item)};" for k, item in v.items()]
            return "{ " + " ".join(attrs) + " }"
        else:
            return "{}"
    
    return convert(config)
