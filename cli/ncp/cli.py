#!/usr/bin/env python3
"""
ncp - Nix Container Platform CLI
A CLI tool for deploying and managing NixOS containers via the Nix-Fly API
"""

import click
import requests
import json
import sys
from typing import Optional
from urllib.parse import urljoin

DEFAULT_API_URL = "https://nix.latha.org/fly"

class NCPClient:
    """Client for the Nix-Fly API"""
    
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
        """Create/deploy a new container"""
        response = self.session.post(
            self._url('/api/v1/containers'),
            json=spec
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
        """Destroy a container"""
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
    
    def list_pending(self):
        """List pending/staged containers"""
        response = self.session.get(self._url('/api/v1/pending'))
        self._handle_error(response)
        return response.json()
    
    def apply_changes(self):
        """Apply all pending changes"""
        response = self.session.post(self._url('/api/v1/apply'))
        self._handle_error(response)
        return response.json()


@click.group()
@click.option('--api-url', envvar='NCP_API_URL', default=DEFAULT_API_URL,
              help='Nix-Fly API URL (default: https://nix.latha.org/fly)')
@click.option('--token', envvar='NCP_TOKEN',
              help='API authentication token')
@click.pass_context
def cli(ctx, api_url, token):
    """ncp - Nix Container Platform CLI
    
    Deploy and manage NixOS containers on the Nix-Fly platform.
    
    Workflow:
        ncp deploy-demo --name my-app    # Stage a new container
        ncp pending                       # Check pending changes
        ncp apply                         # Build and activate
        ncp list                          # View running containers
    
    Commands:
        list, pending, apply              # Container lifecycle
        deploy-demo, demo                 # Quick deployments  
        info, logs, restart, destroy      # Container management
    """
    ctx.ensure_object(dict)
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
@click.pass_context
def pending(ctx):
    """List staged/pending containers waiting for 'apply'"""
    client = ctx.obj['client']
    pending = client.list_pending()
    
    if not pending.get('pending'):
        click.echo("No pending changes. All containers are active.")
        return
    
    click.echo(f"\n{'NAME':<20} {'ACTION':<10} {'CONFIG FILE'}")
    click.echo("-" * 70)
    
    for p in pending['pending']:
        name = p['name']
        action = p.get('action', 'unknown')
        config = p.get('config_file', 'N/A')
        click.echo(f"{name:<20} {action:<10} {config}")
    
    click.echo(f"\n⚠️  Run 'ncp apply' to activate these changes")
    click.echo()


@cli.command()
@click.option('--yes', '-y', is_flag=True, help='Skip confirmation')
@click.pass_context
def apply(ctx, yes):
    """Apply pending changes on the remote server"""
    client = ctx.obj['client']
    
    # Check if there are pending changes
    pending = client.list_pending()
    if not pending.get('pending'):
        click.echo("✅ No pending changes to apply.")
        return
    
    names = [p['name'] for p in pending['pending']]
    click.echo(f"🔄 Requesting apply for: {', '.join(names)}")
    click.echo("   The server will run nixos-rebuild switch (may take a few minutes)")
    
    if not yes:
        if not click.confirm("   Continue?"):
            click.echo("Aborted.")
            return
    
    click.echo("\n⏳ Rebuilding NixOS configuration...")
    try:
        result = client.apply_changes()
        click.echo(f"✅ Applied {len(result.get('applied', []))} changes")
        click.echo(f"\n📦 Active containers:")
        for c in result.get('containers', []):
            status = "🟢" if c['status'] == 'up' else "🔴"
            click.echo(f"   {status} {c['name']:<20} ({c['status']})")
    except SystemExit:
        click.echo("❌ Apply failed", err=True)
        sys.exit(1)
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


@cli.command(name='deploy-demo')
@click.option('--name', default='demo-web', help='Container name')
@click.option('--port', default=8082, help='External port to expose')
@click.option('--auto-start', is_flag=True, default=True, help='Start container after creation')
@click.pass_context
def deploy_demo(ctx, name, port, auto_start):
    """Deploy a demo nginx container"""
    client = ctx.obj['client']
    
    # Demo nginx container configuration
    nix_config = '''{ config, pkgs, lib, ... }: {
  # Simple nginx web server
  services.nginx = {
    enable = true;
    virtualHosts.default = {
      default = true;
      root = "${pkgs.nginx}/html";
      locations."/" = {
        index = "index.html";
      };
    };
  };
  
  # Open firewall for nginx
  networking.firewall.allowedTCPPorts = [ 80 ];
  
  system.stateVersion = "24.11";
}'''
    
    spec = {
        "name": name,
        "description": "Demo nginx web server deployed via ncp CLI",
        "nix_config": nix_config,
        "host_port": port,
        "container_port": 80,
        "auto_start": auto_start
    }
    
    click.echo(f"🚀 Deploying container '{name}'...")
    click.echo(f"   Port mapping: {port} → 80 (container)")
    click.echo(f"   ⚠️  This creates a staged config. Run 'ncp apply' to activate.")
    
    try:
        result = client.create_container(spec)
        click.echo(f"✅ Container staged successfully!")
        click.echo(f"   Status: {result['status']}")
        click.echo(f"   IP: {result.get('ip') or 'auto-assigned'}")
        click.echo(f"\n⚡ Next steps:")
        click.echo(f"   1. Run 'ncp apply' to build and activate the container")
        click.echo(f"   2. Access your app at: http://204.168.220.202:{port}")
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
    """Mark a container for destruction (use 'apply' to complete)"""
    client = ctx.obj['client']
    
    if not force:
        if not click.confirm(f"⚠️  Mark '{name}' for destruction?"):
            click.echo("Aborted.")
            return
    
    click.echo(f"🗑️  Marking '{name}' for destruction...")
    result = client.destroy_container(name)
    click.echo(f"✅ {result.get('note', 'Container marked')}")
    
    if 'apply' in result.get('note', '').lower():
        click.echo(f"⚡ Run 'ncp apply' to complete the destruction")


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
def version():
    """Show ncp version"""
    click.echo("ncp (Nix Container Platform) v0.1.0")
    click.echo("CLI for deploying NixOS containers on Nix-Fly")


# Quick aliases
@cli.command(name='demo')
@click.pass_context
def demo(ctx):
    """Quick deploy a demo container"""
    ctx.invoke(deploy_demo, name='demo-web', port=8082)


if __name__ == '__main__':
    cli()
