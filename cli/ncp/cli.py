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
import subprocess
import shutil
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
    
    def get_me(self):
        """Get current user info"""
        response = self.session.get(self._url('/api/v1/auth/me'))
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

    # Secrets API methods
    def list_secrets(self):
        """List all secrets"""
        response = self.session.get(self._url('/api/v1/secrets'))
        self._handle_error(response)
        return response.json()
    
    def upload_secret(self, name: str, content: bytes):
        """Upload an encrypted secret"""
        if not name.endswith('.age'):
            name = f"{name}.age"
        response = self.session.post(
            self._url(f'/api/v1/secrets/{name}'),
            data=content,
            headers={'Content-Type': 'application/octet-stream'}
        )
        self._handle_error(response)
        return response.json()
    
    def download_secret(self, name: str):
        """Download a secret"""
        if not name.endswith('.age'):
            name = f"{name}.age"
        response = self.session.get(self._url(f'/api/v1/secrets/{name}'))
        self._handle_error(response)
        return response.content
    
    def delete_secret_api(self, name: str):
        """Delete a secret"""
        if not name.endswith('.age'):
            name = f"{name}.age"
        response = self.session.delete(self._url(f'/api/v1/secrets/{name}'))
        self._handle_error(response)
        return response.json()


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
            user_info = client.get_me()
            username = user_info.get('username', 'unknown')
            click.echo(f"✅ Auth Status: Authenticated as {username}")
            containers = client.list_containers()
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


@cli.group()
def secrets():
    """Manage encrypted secrets using agenix
    
    Store sensitive data (API keys, passwords, tokens) encrypted
    and make them available to containers at runtime.
    
    Commands:
        init                    - Initialize agenix in current project
        set <name>              - Create or update a secret
        edit <name>             - Edit an existing secret
        show <name>             - Decrypt and display a secret
        list                    - List all secrets
        rm <name>               - Delete a secret
        template                - Generate Nix template for using secrets
    
    Example:
        ncp secrets init
        ncp secrets set database_password
        ncp secrets set api_key
        ncp list
    """
    pass


def _get_project_secrets_dir() -> Path:
    """Get the secrets directory for the current project"""
    return Path.cwd() / "secrets"


def _get_secrets_nix_path() -> Path:
    """Get the path to secrets.nix"""
    return Path.cwd() / "secrets.nix"


def _find_ssh_pubkey() -> Optional[str]:
    """Find the user's SSH public key"""
    # Try common SSH key locations
    possible_keys = [
        Path.home() / ".ssh" / "id_ed25519.pub",
        Path.home() / ".ssh" / "id_rsa.pub",
        Path.home() / ".ssh" / "id_ecdsa.pub",
    ]
    for key_path in possible_keys:
        if key_path.exists():
            return str(key_path)
    return None


@secrets.command()
@click.option('--key', '-k', help='SSH public key for encryption (defaults to ~/.ssh/id_ed25519.pub)')
def init(key):
    """Initialize agenix secrets in current project"""
    project_dir = Path.cwd()
    secrets_dir = _get_project_secrets_dir()
    secrets_nix = _get_secrets_nix_path()
    
    # Check if already initialized
    if secrets_nix.exists():
        click.echo("⚠️  secrets.nix already exists in this directory")
        if not click.confirm("Reinitialize? (this will backup existing secrets.nix)"):
            return
        # Backup existing
        backup_path = secrets_nix.with_suffix('.nix.backup')
        secrets_nix.rename(backup_path)
        click.echo(f"📦 Backed up existing secrets.nix to {backup_path}")
    
    # Find SSH key
    if not key:
        key = _find_ssh_pubkey()
        if not key:
            click.echo("❌ No SSH public key found in ~/.ssh/")
            click.echo("   Please generate one: ssh-keygen -t ed25519")
            click.echo("   Or specify a key with --key /path/to/key.pub")
            sys.exit(1)
    
    key_path = Path(key)
    if not key_path.exists():
        click.echo(f"❌ SSH key not found: {key}")
        sys.exit(1)
    
    # Read the key
    try:
        with open(key_path, 'r') as f:
            key_content = f.read().strip()
    except Exception as e:
        click.echo(f"❌ Failed to read SSH key: {e}")
        sys.exit(1)
    
    # Create secrets directory
    secrets_dir.mkdir(exist_ok=True)
    (secrets_dir / ".gitignore").write_text("*\n!.gitignore\n")
    
    # Create initial secrets.nix
    secrets_nix_content = f'''# Agenix secrets configuration
# This file defines who can decrypt which secrets
# DO NOT COMMIT THE secrets/ DIRECTORY - only commit this file

let
  # Add more SSH keys here to grant access
  # other_user = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAI... user@host";
in
{{
  # Example: secret for database password
  # "secrets/database_password.age".publicKeys = [ users_key ];

  # Template for new secrets - copy and modify
  # "secrets/my_secret.age".publicKeys = [ users_key ];
}}
'''
    
    # Substitute the actual key
    secrets_nix_content = secrets_nix_content.replace('users_key', f'users_key /* {key_path.name} */')
    
    # Write the file with user's key
    with open(secrets_nix, 'w') as f:
        # Write properly formatted secrets.nix
        f.write(f'''# Agenix secrets configuration
# This file defines who can decrypt which secrets
# DO NOT COMMIT THE secrets/ DIRECTORY - only commit this file

let
  users_key = "{key_content}";
  # Add more SSH keys here to grant access
  # other_user = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAI... user@host";
in
{{
  # Example: secret for database password
  # "secrets/database_password.age".publicKeys = [ users_key ];

  # Template for new secrets - copy and modify
  # "secrets/my_secret.age".publicKeys = [ users_key ];
}}
''')
    
    click.echo("✅ Initialized agenix in current project")
    click.echo(f"   Secrets directory: {secrets_dir}/")
    click.echo(f"   Config file: {secrets_nix}")
    click.echo(f"   Encryption key: {key_path}")
    click.echo("")
    click.echo("Next steps:")
    click.echo("  1. ncp secrets set <secret_name>   # Create your first secret")
    click.echo("  2. Add the secret to your flake.nix")
    click.echo("")
    click.echo("⚠️  IMPORTANT: Add secrets/ to .gitignore!")


@secrets.command()
@click.argument('name')
@click.option('--value', '-v', help='Secret value (will prompt if not provided)')
@click.option('--from-file', '-f', type=click.Path(exists=True), help='Read secret from file')
def set(name, value, from_file):
    """Create or update an encrypted secret"""
    secrets_nix = _get_secrets_nix_path()
    secrets_dir = _get_project_secrets_dir()
    
    if not secrets_nix.exists():
        click.echo("❌ Not an agenix project. Run 'ncp secrets init' first.")
        sys.exit(1)
    
    # Get secret value
    if from_file:
        value = Path(from_file).read_text()
    elif not value:
        value = click.prompt(f'Enter value for {name}', hide_input=True, confirmation_prompt=True)
    
    if not value:
        click.echo("❌ Secret value cannot be empty")
        sys.exit(1)
    
    # Ensure .age extension
    if not name.endswith('.age'):
        name = f"{name}.age"
    
    # Secret path relative to project root
    secret_relative = f"secrets/{name}"
    secret_path = secrets_dir / name
    
    # STEP 1: Add secret to secrets.nix if not already there
    secrets_nix_content = secrets_nix.read_text()
    secret_entry = f'"{secret_relative}".publicKeys = [ users_key ];'
    
    if secret_relative not in secrets_nix_content:
        click.echo(f"📝 Adding {secret_relative} to secrets.nix...")
        # Find the closing brace and insert before it
        lines = secrets_nix_content.split('\n')
        # Look for the closing `}` of the attribute set
        insert_idx = len(lines)
        for i, line in enumerate(lines):
            if line.strip() == '}' and i > len(lines) - 5:  # Last closing brace
                insert_idx = i
                break
        
        # Insert the new secret entry
        lines.insert(insert_idx, f'  {secret_entry}')
        secrets_nix.write_text('\n'.join(lines))
        click.echo(f"   ✓ Added to secrets.nix")
    
    # STEP 2: Create temp file with secret value
    import tempfile
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as tmp:
        tmp.write(value)
        tmp.flush()
        tmp_path = tmp.name
    
    try:
        # STEP 3: Encrypt using agenix
        # For new secrets, we need to use EDITOR to create the file
        # agenix will use the EDITOR to create the file, but we want to automate this
        # So we use a trick: set EDITOR to cat the temp file
        
        env = os.environ.copy()
        env['EDITOR'] = f'cat {tmp_path}'
        
        click.echo(f"🔐 Encrypting {name}...")
        result = subprocess.run(
            ['agenix', '-e', secret_relative],
            capture_output=True,
            text=True,
            cwd=str(Path.cwd()),
            env=env
        )
        
        if result.returncode != 0:
            click.echo(f"❌ Failed to encrypt secret: {result.stderr}")
            sys.exit(1)
        
        click.echo(f"✅ Secret saved: {secret_path}")
        click.echo(f"   Size: {len(value)} bytes encrypted")
        click.echo(f"   Entry in secrets.nix: {secret_entry}")
        
    finally:
        # Securely delete temp file
        os.unlink(tmp_path)


@secrets.command()
@click.argument('name')
def edit(name):
    """Edit an existing secret"""
    secrets_nix = _get_secrets_nix_path()
    secrets_dir = _get_project_secrets_dir()
    
    if not secrets_nix.exists():
        click.echo("❌ Not an agenix project. Run 'ncp secrets init' first.")
        sys.exit(1)
    
    # Ensure .age extension
    if not name.endswith('.age'):
        name = f"{name}.age"
    
    secret_path = secrets_dir / name
    
    if not secret_path.exists():
        click.echo(f"❌ Secret not found: {name}")
        click.echo("   Create it first with: ncp secrets set " + name.replace('.age', ''))
        sys.exit(1)
    
    # Open in agenix editor
    result = subprocess.run(
        ['agenix', '-e', str(secret_path)],
        capture_output=True,
        text=True,
        cwd=str(Path.cwd())
    )
    
    if result.returncode != 0:
        click.echo(f"❌ Failed to edit secret: {result.stderr}")
        sys.exit(1)
    
    click.echo(f"✅ Secret updated: {secret_path}")


@secrets.command()
@click.argument('name')
def show(name):
    """Decrypt and display a secret (use with caution!)"""
    secrets_nix = _get_secrets_nix_path()
    secrets_dir = _get_project_secrets_dir()
    
    if not secrets_nix.exists():
        click.echo("❌ Not an agenix project. Run 'ncp secrets init' first.")
        sys.exit(1)
    
    # Ensure .age extension
    if not name.endswith('.age'):
        name = f"{name}.age"
    
    secret_path = secrets_dir / name
    
    if not secret_path.exists():
        click.echo(f"❌ Secret not found: {name}")
        sys.exit(1)
    
    # Decrypt using agenix
    result = subprocess.run(
        ['agenix', '-d', str(secret_path)],
        capture_output=True,
        text=True,
        cwd=str(Path.cwd())
    )
    
    if result.returncode != 0:
        click.echo(f"❌ Failed to decrypt secret: {result.stderr}")
        sys.exit(1)
    
    click.echo(f"🔓 Decrypted secret ({name}):")
    click.echo("─" * 40)
    click.echo(result.stdout)


@secrets.command()
def list():
    """List all secrets"""
    secrets_nix = _get_secrets_nix_path()
    secrets_dir = _get_project_secrets_dir()
    
    if not secrets_nix.exists():
        click.echo("❌ Not an agenix project. Run 'ncp secrets init' first.")
        sys.exit(1)
    
    if not secrets_dir.exists():
        click.echo("No secrets directory found")
        return
    
    secrets_files = list(secrets_dir.glob("*.age"))
    
    if not secrets_files:
        click.echo("No secrets found")
        return
    
    click.echo("📦 Secrets:")
    for secret in sorted(secrets_files):
        size = secret.stat().st_size
        click.echo(f"   • {secret.name} ({size} bytes)")
    
    click.echo(f"\nTotal: {len(secrets_files)} secrets")


@secrets.command()
@click.argument('name')
@click.option('--yes', '-y', is_flag=True, help='Skip confirmation')
def rm(name, yes):
    """Delete a secret"""
    secrets_dir = _get_project_secrets_dir()
    
    # Ensure .age extension
    if not name.endswith('.age'):
        name = f"{name}.age"
    
    secret_path = secrets_dir / name
    
    if not secret_path.exists():
        click.echo(f"❌ Secret not found: {name}")
        sys.exit(1)
    
    if not yes:
        if not click.confirm(f"Delete {name}?"):
            return
    
    secret_path.unlink()
    click.echo(f"✅ Deleted: {name}")
    click.echo("⚠️  Remember to remove the entry from secrets.nix")


@secrets.command()
def template():
    """Generate Nix template for using secrets in containers"""
    template = '''
# Example: Using secrets in your flake.nix

{ config, pkgs, agenix, ... }:

{
  # Import agenix module
  imports = [ agenix.nixosModules.default ];

  # Enable agenix
  age.identityPaths = [ "/root/.ssh/id_ed25519" ];
  
  # Define secrets
  age.secrets.database_password = {
    file = ./secrets/database_password.age;
    owner = "myapp";
    group = "myapp";
    mode = "600";
  };

  # Use secret in a service
  systemd.services.myapp = {
    serviceConfig = {
      # Pass secret path as environment variable
      Environment = "DB_PASSWORD_FILE=%{config.age.secrets.database_password.path}";
    };
  };
}

# Then in your application, read the secret from the file:
# DB_PASSWORD=$(cat $DB_PASSWORD_FILE)
'''
    click.echo(template)
    click.echo("\n# Save this to your flake.nix and adapt as needed")


# Remote secrets sync commands
@secrets.group(name='remote')
def secrets_remote():
    """Sync secrets with remote NCP server
    
    Upload and download encrypted secrets to/from the NCP server.
    Secrets remain encrypted during transfer and on the server.
    """
    pass


@secrets_remote.command(name='upload')
@click.argument('name')
@click.pass_context
def secrets_upload(ctx, name):
    """Upload a secret to the remote server"""
    client = ctx.obj['client']
    secrets_dir = _get_project_secrets_dir()
    
    # Ensure .age extension
    if not name.endswith('.age'):
        name = f"{name}.age"
    
    secret_path = secrets_dir / name
    
    if not secret_path.exists():
        click.echo(f"❌ Secret not found locally: {name}")
        sys.exit(1)
    
    click.echo(f"☁️  Uploading {name} to remote...")
    
    with open(secret_path, 'rb') as f:
        content = f.read()
    
    result = client.upload_secret(name, content)
    click.echo(f"✅ Uploaded: {name} ({len(content)} bytes)")


@secrets_remote.command(name='download')
@click.argument('name')
@click.pass_context
def secrets_download(ctx, name):
    """Download a secret from the remote server"""
    client = ctx.obj['client']
    secrets_dir = _get_project_secrets_dir()
    
    # Ensure .age extension
    if not name.endswith('.age'):
        name = f"{name}.age"
    
    click.echo(f"☁️  Downloading {name} from remote...")
    
    content = client.download_secret(name)
    
    # Save to local secrets directory
    secrets_dir.mkdir(exist_ok=True)
    secret_path = secrets_dir / name
    
    with open(secret_path, 'wb') as f:
        f.write(content)
    
    os.chmod(secret_path, 0o600)
    click.echo(f"✅ Downloaded: {name} ({len(content)} bytes)")


@secrets_remote.command(name='sync')
@click.option('--push', is_flag=True, help='Push all local secrets to remote')
@click.option('--pull', is_flag=True, help='Pull all remote secrets locally')
@click.pass_context
def secrets_sync(ctx, push, pull):
    """Sync all secrets with remote server"""
    client = ctx.obj['client']
    secrets_dir = _get_project_secrets_dir()
    
    if not push and not pull:
        click.echo("❌ Specify --push or --pull")
        sys.exit(1)
    
    if push:
        click.echo("☁️  Pushing local secrets to remote...")
        if not secrets_dir.exists():
            click.echo("❌ No local secrets directory")
            sys.exit(1)
        
        secrets = list(secrets_dir.glob("*.age"))
        if not secrets:
            click.echo("No local secrets to push")
            return
        
        for secret in secrets:
            with open(secret, 'rb') as f:
                content = f.read()
            client.upload_secret(secret.name, content)
            click.echo(f"   ✓ {secret.name}")
        
        click.echo(f"✅ Pushed {len(secrets)} secrets")
    
    if pull:
        click.echo("☁️  Pulling remote secrets...")
        result = client.list_secrets()
        secrets = result.get('secrets', [])
        
        if not secrets:
            click.echo("No remote secrets to pull")
            return
        
        secrets_dir.mkdir(exist_ok=True)
        
        for name in secrets:
            content = client.download_secret(name)
            secret_path = secrets_dir / name
            with open(secret_path, 'wb') as f:
                f.write(content)
            os.chmod(secret_path, 0o600)
            click.echo(f"   ✓ {name}")
        
        click.echo(f"✅ Pulled {len(secrets)} secrets")


@secrets_remote.command(name='list')
@click.pass_context
def secrets_remote_list(ctx):
    """List secrets on remote server"""
    client = ctx.obj['client']
    
    click.echo("☁️  Remote secrets:")
    result = client.list_secrets()
    secrets = result.get('secrets', [])
    
    if not secrets:
        click.echo("   No secrets found on remote")
        return
    
    for name in secrets:
        click.echo(f"   • {name}")
    
    click.echo(f"\nTotal: {len(secrets)} secrets on remote")


if __name__ == '__main__':
    cli()
