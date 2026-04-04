#!/usr/bin/env python3
"""
ncp - Nix Container Platform CLI
A CLI tool for deploying and managing NixOS containers dynamically
"""

import click
import requests
import json
import sys
from typing import Optional
from urllib.parse import urljoin

DEFAULT_API_URL = "https://nix.latha.org"

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
        """Create/deploy a new container (starts immediately)"""
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
              help='Nix-Fly API URL (default: https://nix.latha.org/fly)')
@click.option('--token', envvar='NCP_TOKEN',
              help='API authentication token')
@click.pass_context
def cli(ctx, api_url, token):
    """ncp - Nix Container Platform CLI
    
    Deploy and manage NixOS containers dynamically.
    
    Workflow (Dynamic Mode):
        ncp deploy-demo --name my-app    # Deploy and start immediately!
        ncp list                          # View running containers
        ncp logs my-app -f                # Stream logs
        ncp destroy my-app                # Destroy immediately
    
    Commands:
        list, deploy, deploy-demo         # Container lifecycle
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


@cli.command(name='deploy')
@click.option('--name', required=True, help='Container name')
@click.option('--port', default=8080, help='External port to expose')
@click.option('--config', '-c', help='Nix config file to use')
@click.pass_context
def deploy(ctx, name, port, config):
    """Deploy a container from a Nix config file"""
    client = ctx.obj['client']
    
    # Read config file
    if config:
        with open(config, 'r') as f:
            nix_config = f.read()
    else:
        # Default nginx config
        nix_config = '''{
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
  networking.firewall.allowedTCPPorts = [ 80 ];
}'''
    
    spec = {
        "name": name,
        "description": f"Container {name} deployed via ncp CLI",
        "nix_config": nix_config,
        "host_port": port,
        "container_port": 80,
        "auto_start": True
    }
    
    click.echo(f"🚀 Deploying container '{name}'...")
    click.echo(f"   Port mapping: {port} → 80 (container)")
    click.echo(f"   ⏳ Building and starting (this may take a minute)...")
    
    try:
        result = client.create_container(spec)
        click.echo(f"✅ Container deployed and running!")
        click.echo(f"   Status: {result['status']}")
        click.echo(f"   IP: {result.get('ip') or 'auto-assigned'}")
        click.echo(f"   Access: http://204.168.220.202:{port}")
    except SystemExit:
        click.echo("❌ Deployment failed", err=True)
        sys.exit(1)


@cli.command(name='deploy-demo')
@click.option('--name', default='demo-web', help='Container name')
@click.option('--port', default=8082, help='External port to expose')
@click.pass_context
def deploy_demo(ctx, name, port):
    """Deploy a demo nginx container"""
    ctx.invoke(deploy, name=name, port=port, config=None)


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
