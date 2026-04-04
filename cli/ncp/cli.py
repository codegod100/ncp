#!/usr/bin/env python3
"""
ncp - Nix Container Platform CLI
A CLI tool for deploying and managing NixOS containers dynamically
"""

import click
import requests
import json
import sys
import os
from typing import Optional
from pathlib import Path
from urllib.parse import urljoin

DEFAULT_API_URL = "https://nix.latha.org"


def get_config_dir() -> Path:
    """Get or create config directory"""
    config_dir = Path.home() / ".config" / "ncp"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


def get_config_path() -> Path:
    """Get config file path"""
    return get_config_dir() / "config.json"


def load_config() -> dict:
    """Load config from file"""
    config_path = get_config_path()
    if config_path.exists():
        try:
            with open(config_path, 'r') as f:
                return json.load(f)
        except:
            return {}
    return {}


def save_config(config: dict):
    """Save config to file"""
    config_path = get_config_path()
    with open(config_path, 'w') as f:
        json.dump(config, f, indent=2)
    # Set restrictive permissions (only owner can read)
    os.chmod(config_path, 0o600)


def get_saved_token() -> Optional[str]:
    """Get token from config file"""
    config = load_config()
    return config.get('token')


def save_token(token: str, api_url: str = DEFAULT_API_URL):
    """Save token to config file"""
    config = load_config()
    config['token'] = token
    config['api_url'] = api_url
    save_config(config)


def clear_token():
    """Remove saved token"""
    config = load_config()
    config.pop('token', None)
    save_config(config)

class NCPClient:
    """Client for the Nix Container Platform API"""
    
    def __init__(self, base_url: str = DEFAULT_API_URL, token: Optional[str] = None):
        self.base_url = base_url.rstrip('/')
        self.token = token
        self.session = requests.Session()
        if token:
            self.session.headers.update({"Authorization": f"Bearer {token}"})
    
    def _url(self, path: str) -> str:
        return urljoin(self.base_url + '/', path.lstrip('/'))
    
    def _handle_error(self, response):
        if not response.ok:
            try:
                error = response.json()
                click.echo(f"Error: {error.get('detail', response.text)}", err=True)
            except:
                click.echo(f"Error: {response.status_code} - {response.text}", err=True)
            sys.exit(1)
    
    def list_containers(self):
        """List all containers"""
        response = self.session.get(self._url('/api/v1/containers'))
        self._handle_error(response)
        return response.json()
    
    def get_container(self, name: str):
        """Get container details"""
        response = self.session.get(self._url(f'/api/v1/containers/{name}'))
        self._handle_error(response)
        return response.json()
    
    def create_container(self, spec: dict):
        """Create/deploy a new container (starts immediately)"""
        response = self.session.post(
            self._url('/api/v1/containers'),
            json=spec
        )
        self._handle_error(response)
        return response.json()
    
    def deploy_project(self, project_name: str, files: dict):
        """Deploy a project (directory of files) to the server.
        
        Server handles all Nix parsing and container creation.
        """
        response = self.session.post(
            self._url(f'/api/v1/projects/{project_name}/deploy'),
            json={'files': files}
        )
        self._handle_error(response)
        return response.json()
    
    def restart_container(self, name: str):
        """Restart a container"""
        response = self.session.post(
            self._url(f'/api/v1/containers/{name}/restart')
        )
        self._handle_error(response)
        return response.json()
    
    def destroy_container(self, name: str):
        """Destroy a container immediately"""
        response = self.session.delete(
            self._url(f'/api/v1/containers/{name}')
        )
        self._handle_error(response)
        return response.json()
    
    def get_logs(self, name: str, follow: bool = False, lines: int = 100):
        """Get container logs"""
        params = {"follow": follow, "lines": lines}
        response = self.session.get(
            self._url(f'/api/v1/containers/{name}/logs'),
            params=params,
            stream=follow
        )
        self._handle_error(response)
        return response


@click.group()
@click.option('--api-url', envvar='NCP_API_URL', default=DEFAULT_API_URL,
              help='Nix Container Platform API URL (default: https://nix.latha.org)')
@click.option('--token', envvar='NCP_TOKEN',
              help='API authentication token')
@click.pass_context
def cli(ctx, api_url, token):
    """ncp - Nix Container Platform CLI
    
    Deploy and manage NixOS containers dynamically.
    
    Workflow (Dynamic Mode):
        ncp login                        # Authenticate interactively
        ncp status                       # Verify auth
        ncp deploy --name my-app         # Deploy and start immediately!
        ncp list                         # View running containers
        ncp logs my-app -f               # Stream logs
        ncp destroy my-app               # Destroy immediately
    
    Commands:
        login, status                      # Authentication
        list, deploy, deploy-demo          # Container lifecycle
        info, logs, restart, destroy       # Container management
    """
    ctx.ensure_object(dict)
    
    # Load token from config file if not provided via env/cli
    if not token:
        token = get_saved_token()
    
    ctx.obj['client'] = NCPClient(api_url, token)


@cli.command()
@click.pass_context
def list(ctx):
    """List all containers"""
    client = ctx.obj['client']
    containers = client.list_containers()
    
    if not containers:
        click.echo("No containers found.")
    else:
        click.echo(f"\n{'NAME':<20} {'STATUS':<10} {'IP':<15} {'PORT':<6}")
        click.echo("-" * 55)
        
        for c in containers:
            name = c['name']
            status = c['status']
            ip = c.get('ip') or '-'
            port = str(c.get('host_port') or '-')
            click.echo(f"{name:<20} {status:<10} {ip:<15} {port:<6}")
    
    click.echo()


@cli.command()
@click.argument('name')
@click.pass_context
def info(ctx, name):
    """Show container details"""
    client = ctx.obj['client']
    container = client.get_container(name)
    
    click.echo(f"\n📦 Container: {container['name']}")
    click.echo(f"   Status: {container['status']}")
    click.echo(f"   IP: {container.get('ip') or 'N/A'}")
    click.echo(f"   Host Port: {container.get('host_port') or 'N/A'}")
    click.echo(f"   Created: {container.get('created_at', 'unknown')}")
    click.echo()


def read_project_files(project_dir: str) -> dict:
    """Read all files in a project directory for sending to server.
    
    Returns dict mapping filenames to their contents.
    """
    files = {}
    import os
    
    for root, dirs, filenames in os.walk(project_dir):
        # Skip .git and common ignore directories
        dirs[:] = [d for d in dirs if d not in ['.git', '.venv', 'node_modules', '__pycache__']]
        
        for filename in filenames:
            # Skip common non-config files
            if filename.endswith(('.lock', '.log', '.tmp', '.swp', '.swo', '~')):
                continue
            
            filepath = os.path.join(root, filename)
            relpath = os.path.relpath(filepath, project_dir)
            
            try:
                with open(filepath, 'r') as f:
                    files[relpath] = f.read()
            except (UnicodeDecodeError, IOError):
                # Skip binary files or unreadable files
                pass
    
    return files


@cli.command(name='deploy')
@click.argument('project')
@click.pass_context
def deploy(ctx, project):
    """Deploy a project to NCP.
    
    Reads the project directory and sends it to the server for deployment.
    The server handles all Nix parsing and container creation.
    
    Usage: ncp deploy PROJECT
    
    Example:
        ncp deploy myapp     # Deploys myapp/ directory
        ncp deploy simple    # Deploys simple/ directory
    """
    client = ctx.obj['client']
    
    # Check if project directory exists
    if not os.path.isdir(project):
        click.echo(f"❌ Project directory not found: {project}/", err=True)
        click.echo(f"   Expected a directory named '{project}' in current directory", err=True)
        sys.exit(1)
    
    # Check for flake.nix
    flake_path = os.path.join(project, "flake.nix")
    if not os.path.exists(flake_path):
        click.echo(f"❌ No flake.nix found in {project}/", err=True)
        click.echo(f"   Projects must have a flake.nix file defining containers", err=True)
        sys.exit(1)
    
    click.echo(f"🚀 Deploying project '{project}'...")
    click.echo(f"   Reading project files from {project}/")
    
    # Read all project files
    try:
        files = read_project_files(project)
    except Exception as e:
        click.echo(f"❌ Failed to read project: {e}", err=True)
        sys.exit(1)
    
    click.echo(f"   📁 {len(files)} files to deploy")
    click.echo(f"   ⏳ Sending to server for build...")
    
    # Use basename as project name (server doesn't need full path)
    project_name = os.path.basename(os.path.normpath(project))
    
    # Send to server
    try:
        result = client.deploy_project(project_name, files)
        
        click.echo(f"✅ Project deployed!")
        
        # Show deployed containers
        if 'containers' in result:
            click.echo(f"\n📦 Deployed containers:")
            for container in result['containers']:
                name = container.get('name', 'unknown')
                port = container.get('host_port', 'unknown')
                status = container.get('status', 'unknown')
                click.echo(f"   • {name} (port {port}) - {status}")
        
        if 'message' in result:
            click.echo(f"\n{result['message']}")
            
    except SystemExit:
        click.echo("❌ Deployment failed", err=True)
        sys.exit(1)
@cli.command(name='deploy-demo')
@click.option('--name', default='demo-web', help='Container name')
@click.option('--port', default=8082, help='External port to expose')
@click.pass_context
def deploy_demo(ctx, name, port):
    """Deploy a demo nginx container (legacy, use 'deploy' instead)"""
    client = ctx.obj['client']
    
    nix_config = f'''# ncp: port={port}
# ncp: name={name}
{{
  services.nginx = {{
    enable = true;
    virtualHosts.default = {{
      default = true;
      root = "${{pkgs.nginx}}/html";
      locations."/" = {{
        index = "index.html";
      }};
    }};
  }};
  networking.firewall.allowedTCPPorts = [ 80 ];
}}'''
    
    spec = {
        "name": name,
        "description": f"Demo container {name}",
        "nix_config": nix_config,
        "host_port": port,
        "container_port": 80,
        "auto_start": True
    }
    
    click.echo(f"🚀 Deploying demo container '{name}'...")
    click.echo(f"   Port mapping: {port} → 80 (container)")
    
    try:
        result = client.create_container(spec)
        click.echo(f"✅ Container deployed!")
        click.echo(f"   Access: http://204.168.220.202:{port}")
    except SystemExit:
        click.echo("❌ Deployment failed", err=True)
        sys.exit(1)


@cli.command()
@click.argument('name')
@click.pass_context
def restart(ctx, name):
    """Restart a container"""
    client = ctx.obj['client']
    
    click.echo(f"🔄 Restarting '{name}'...")
    result = client.restart_container(name)
    click.echo(f"✅ Container restarted. New status: {result['new_status']}")


@cli.command()
@click.argument('name')
@click.option('--force', is_flag=True, help='Skip confirmation')
@click.pass_context
def destroy(ctx, name, force):
    """Destroy a container immediately"""
    client = ctx.obj['client']
    
    if not force:
        if not click.confirm(f"⚠️  Destroy '{name}' immediately?"):
            click.echo("Aborted.")
            return
    
    click.echo(f"🗑️  Destroying '{name}'...")
    result = client.destroy_container(name)
    click.echo(f"✅ {result.get('action', 'Container destroyed')}")


@cli.command()
@click.argument('name')
@click.option('--follow', '-f', is_flag=True, help='Follow log output')
@click.option('--lines', '-n', default=100, help='Number of lines to show')
@click.pass_context
def logs(ctx, name, follow, lines):
    """Show container logs"""
    client = ctx.obj['client']
    
    response = client.get_logs(name, follow=follow, lines=lines)
    
    if follow:
        click.echo(f"📜 Streaming logs for '{name}' (Ctrl+C to exit)...\n")
        try:
            for line in response.iter_lines():
                if line:
                    click.echo(line.decode('utf-8'))
        except KeyboardInterrupt:
            click.echo("\n\n👋 Log streaming stopped.")
    else:
        click.echo(response.text)


@cli.command()
@click.pass_context
def status(ctx):
    """Show authentication and connection status"""
    client = ctx.obj['client']
    
    click.echo("\n🔐 ncp Status")
    click.echo("─" * 40)
    
    # API URL
    click.echo(f"📡 API URL:    {client.base_url}")
    
    # Auth status
    if client.token:
        # Mask the token for display
        token_display = client.token[:20] + "..." if len(client.token) > 20 else client.token
        click.echo(f"🔑 Auth Token: {token_display}")
        
        # Try to validate by making a request
        try:
            containers = client.list_containers()
            click.echo(f"✅ Auth Status: Authenticated")
            click.echo(f"📦 Containers: {len(containers)} found")
        except SystemExit:
            # list_containers calls sys.exit(1) on error
            click.echo(f"⚠️  Auth Status: Token exists but API request failed")
            click.echo(f"   Check your connection or token may be expired")
    else:
        click.echo(f"❌ Auth Status: Not logged in")
        click.echo(f"   Run: ncp login")
        
        # Show config file location
        config_path = get_config_path()
        if config_path.exists():
            click.echo(f"")
            click.echo(f"   Config file: {config_path}")
            click.echo(f"   (File exists but no valid token found)")
    
    click.echo()


@cli.command()
@click.option('--username', '-u', prompt=True, help='Your username')
@click.option('--password', '-p', prompt=True, hide_input=True, help='Your password')
@click.pass_context
def login(ctx, username, password):
    """Authenticate and get API token"""
    client = ctx.obj['client']
    
    click.echo(f"\n🔐 Logging in to {client.base_url}...")
    
    try:
        response = requests.post(
            client._url('/api/v1/auth/login'),
            json={"username": username, "password": password}
        )
        
        if response.status_code == 200:
            data = response.json()
            token = data.get('access_token')
            
            if token:
                click.echo("✅ Login successful!")
                click.echo("")
                click.echo("🔑 Your API token:")
                click.echo(f"   {token}")
                click.echo("")
                click.echo("📋 To use this token, run:")
                click.echo(f"   export NCP_TOKEN={token}")
                click.echo("")
                click.echo("💡 Or add to your shell profile:")
                click.echo(f"   echo 'export NCP_TOKEN={token}' >> ~/.bashrc")
            else:
                click.echo("⚠️  Login succeeded but no token received")
        elif response.status_code == 401:
            click.echo("❌ Login failed: Invalid username or password")
        else:
            click.echo(f"❌ Login failed: {response.status_code}")
            try:
                error = response.json()
                click.echo(f"   {error.get('detail', response.text)}")
            except:
                click.echo(f"   {response.text}")
    except requests.exceptions.ConnectionError:
        click.echo(f"❌ Cannot connect to {client.base_url}")
        click.echo("   Check your internet connection and API URL")
    except Exception as e:
        click.echo(f"❌ Error: {e}")


@cli.command()
@click.option('--username', '-u', prompt=True, help='Your username')
@click.option('--password', '-p', prompt=True, hide_input=True, help='Your password')
@click.pass_context
def login(ctx, username, password):
    """Authenticate and get API token"""
    client = ctx.obj['client']
    
    click.echo(f"\n🔐 Logging in to {client.base_url}...")
    
    try:
        response = requests.post(
            client._url('/api/v1/auth/login'),
            json={"username": username, "password": password}
        )
        
        if response.status_code == 200:
            data = response.json()
            token = data.get('access_token')
            
            if token:
                # Save token to config file
                save_token(token, client.base_url)
                
                click.echo("✅ Login successful!")
                click.echo("")
                click.echo("🔑 Token saved to ~/.config/ncp/config.json")
                click.echo("   (File permissions: 600 - only you can read it)")
                click.echo("")
                click.echo("📋 You can now use ncp without setting NCP_TOKEN:")
                click.echo("   ncp status")
                click.echo("   ncp list")
                click.echo("")
                click.echo("💡 To logout: rm ~/.config/ncp/config.json")
            else:
                click.echo("⚠️  Login succeeded but no token received")
        elif response.status_code == 401:
            click.echo("❌ Login failed: Invalid username or password")
        else:
            click.echo(f"❌ Login failed: {response.status_code}")
            try:
                error = response.json()
                click.echo(f"   {error.get('detail', response.text)}")
            except:
                click.echo(f"   {response.text}")
    except requests.exceptions.ConnectionError:
        click.echo(f"❌ Cannot connect to {client.base_url}")
        click.echo("   Check your internet connection and API URL")
    except Exception as e:
        click.echo(f"❌ Error: {e}")


@cli.command()
def version():
    """Show ncp version"""
    click.echo("ncp (Nix Container Platform) v0.2.0")
    click.echo("Dynamic container CLI - no rebuilds needed!")


# Quick aliases
@cli.command(name='demo')
@click.pass_context
def demo(ctx):
    """Quick deploy a demo container"""
    ctx.invoke(deploy_demo, name='demo-web', port=8082)


if __name__ == '__main__':
    cli()
