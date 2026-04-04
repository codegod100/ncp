# Infrastructure Host Configuration
# Manages the container subnet, routing, and all containers on Hetzner

{ config, pkgs, lib, containerNetwork, ... }:

let
  bridgeName = "ctrs";
  subnet = containerNetwork.subnet;
  gateway = containerNetwork.gateway;
  
  # Import dynamically created container configs from /etc/nix-fly/containers/
  # These are created by the API
  dynamicContainerConfigs = 
    if builtins.pathExists /etc/nix-fly/containers/imports.nix 
    then import /etc/nix-fly/containers/imports.nix
    else [];

in {
  boot.loader.grub.enable = true;
  boot.loader.grub.device = "/dev/sda";
  boot.initrd.availableKernelModules = [ "ahci" "xhci_pci" "virtio_pci" "virtio_scsi" "sd_mod" "sr_mod" "ext4" ];

  fileSystems."/" = {
    device = "/dev/disk/by-label/nixos";
    fsType = "ext4";
  };
  fileSystems."/boot" = {
    device = "/dev/disk/by-label/boot";
    fsType = "ext4";
  };
  swapDevices = [
    { device = "/dev/disk/by-label/swap"; }
  ];

  networking.hostName = "infra-host";
  networking.useDHCP = true;
  
  time.timeZone = "America/Los_Angeles";
  i18n.defaultLocale = "en_US.UTF-8";
  console.keyMap = "us";

  nix.settings.experimental-features = "nix-command flakes";

  # Container network bridge
  networking.bridges.${bridgeName} = {
    interfaces = [];
  };
  
  networking.interfaces.${bridgeName} = {
    ipv4.addresses = [{
      address = gateway;
      prefixLength = 16;
    }];
  };

  # NAT for containers
  networking.nat = {
    enable = true;
    internalInterfaces = [ bridgeName ];
    externalInterface = "enp1s0";
  };

  # Nix-Fly API Service (v2 with staging/apply workflow)
  systemd.services.nix-fly-api = {
    description = "Nix-Fly Container Management API";
    wantedBy = [ "multi-user.target" ];
    after = [ "network.target" ];
    
    path = with pkgs; [ nixos-container iptables bash coreutils config.system.build.nixos-rebuild ];
    
    serviceConfig = {
      Type = "simple";
      ExecStart = "${pkgs.python3.withPackages (ps: with ps; [ fastapi uvicorn pydantic ])}/bin/python3 /home/nixos/code/nixos-infra-host/api/main.py";
      Restart = "always";
      RestartSec = 5;
      User = "root";
      Group = "root";
      StateDirectory = "nix-fly";
    };
  };

  # Caddy reverse proxy with API
  services.caddy = {
    enable = true;
    
    extraConfig = ''
      nix.latha.org {
        # Nix-Fly API at /fly/*
        handle_path /fly/* {
          reverse_proxy localhost:8000
        }
        
        # API Server at /api/*
        handle /api/* {
          uri strip_prefix /api
          reverse_proxy ${containerNetwork.containers.api-server.ip}:3000
        }
        
        # Worker at /worker/*
        handle /worker/* {
          uri strip_prefix /worker
          reverse_proxy ${containerNetwork.containers.worker.ip}:3000
        }
        
        # Info page at root - with proper HTML content-type
        handle {
          header Content-Type "text/html; charset=utf-8"
          respond <<HTML
<!DOCTYPE html>
<html>
<head><title>NixOS Container Infrastructure</title></head>
<body>
<h1>NixOS Container Infrastructure - nix.latha.org</h1>
<h2>Nix-Fly API</h2>
<p>Container management API available at <a href="/fly/">/fly/</a></p>
<h2>Services</h2>
<ul>
  <li><a href="/fly/">Nix-Fly API</a> - Container management</li>
  <li><a href="/api/health">API Health</a> (${containerNetwork.containers.api-server.ip}:3000)</li>
  <li><a href="/worker/health">Worker Health</a> (${containerNetwork.containers.worker.ip}:3000)</li>
  <li>PostgreSQL: ${containerNetwork.containers.postgres.ip}:5432</li>
</ul>
</body>
</html>
HTML 200
        }
      }
      
      http://nix.latha.org {
        redir https://nix.latha.org{uri} permanent
      }
      
      :80 {
        handle_path /fly/* {
          reverse_proxy localhost:8000
        }
        
        handle /api/* {
          uri strip_prefix /api
          reverse_proxy ${containerNetwork.containers.api-server.ip}:3000
        }
        
        handle /worker/* {
          uri strip_prefix /worker
          reverse_proxy ${containerNetwork.containers.worker.ip}:3000
        }
        
        handle {
          header Content-Type "text/html; charset=utf-8"
          respond "<h1>NixOS Container Infrastructure</h1><p>API at <a href='/fly/'>/fly/</a> | Use <a href='https://nix.latha.org'>https://nix.latha.org</a></p>" 200
        }
      }
    '';
  };

  # Firewall with port forwarding to containers
  networking.firewall = {
    enable = true;
    trustedInterfaces = [ bridgeName ];
    
    allowedTCPPorts = [ 
      22      # SSH to host
      80      # HTTP (Caddy)
      443     # HTTPS (Caddy)
      8000    # Nix-Fly API (internal)
      8080    # API Server (direct)
      8081    # Worker (direct)
      5432    # PostgreSQL (direct)
    ];
    
    extraCommands = ''
      # Enable IP forwarding
      echo 1 > /proc/sys/net/ipv4/ip_forward
      
      # Allow traffic between containers
      iptables -A FORWARD -i ${bridgeName} -o ${bridgeName} -j ACCEPT
      
      # DNAT: Forward external traffic to containers (direct access)
      # API Server: 8080 -> 10.100.1.10:3000
      iptables -t nat -A PREROUTING -p tcp --dport 8080 -j DNAT --to-destination ${containerNetwork.containers.api-server.ip}:3000
      iptables -t nat -A POSTROUTING -p tcp --dport 3000 -d ${containerNetwork.containers.api-server.ip} -j MASQUERADE
      
      # Worker: 8081 -> 10.100.2.10:3000
      iptables -t nat -A PREROUTING -p tcp --dport 8081 -j DNAT --to-destination ${containerNetwork.containers.worker.ip}:3000
      iptables -t nat -A POSTROUTING -p tcp --dport 3000 -d ${containerNetwork.containers.worker.ip} -j MASQUERADE
      
      # PostgreSQL: 5432 -> 10.100.3.10:5432
      iptables -t nat -A PREROUTING -p tcp --dport 5432 -j DNAT --to-destination ${containerNetwork.containers.postgres.ip}:5432
      iptables -t nat -A POSTROUTING -p tcp --dport 5432 -d ${containerNetwork.containers.postgres.ip} -j MASQUERADE
      
      # Also allow local host access to containers via DNAT
      iptables -t nat -A OUTPUT -o lo -p tcp --dport 8080 -j DNAT --to-destination ${containerNetwork.containers.api-server.ip}:3000
      iptables -t nat -A OUTPUT -o lo -p tcp --dport 8081 -j DNAT --to-destination ${containerNetwork.containers.worker.ip}:3000
      iptables -t nat -A OUTPUT -o lo -p tcp --dport 5432 -j DNAT --to-destination ${containerNetwork.containers.postgres.ip}:5432
    '';
  };

  # DNS for containers
  services.dnsmasq = {
    enable = true;
    settings = {
      interface = bridgeName;
      bind-interfaces = true;
      domain-needed = true;
      bogus-priv = true;
      address = [
        "/api-server.ctrs/${containerNetwork.containers.api-server.ip}"
        "/worker.ctrs/${containerNetwork.containers.worker.ip}"
        "/postgres.ctrs/${containerNetwork.containers.postgres.ip}"
      ];
    };
  };

  # Containers with private network
  # Static containers (defined in this file)
  containers = {
    api-server = {
      autoStart = true;
      ephemeral = false;
      privateNetwork = true;
      hostAddress = gateway;
      localAddress = containerNetwork.containers.api-server.ip;
      
      config = { config, pkgs, lib, ... }: {
        imports = [ ../containers/api-server.nix ];
      };
    };
    
    worker = {
      autoStart = true;
      ephemeral = false;
      privateNetwork = true;
      hostAddress = gateway;
      localAddress = containerNetwork.containers.worker.ip;
      
      config = { config, pkgs, lib, ... }: {
        imports = [ ../containers/worker.nix ];
      };
    };
    
    postgres = {
      autoStart = true;
      ephemeral = false;
      privateNetwork = true;
      hostAddress = gateway;
      localAddress = containerNetwork.containers.postgres.ip;
      
      config = { config, pkgs, lib, ... }: {
        imports = [ ../containers/postgres.nix ];
      };
    };
  };

  # Import dynamically created container configs from API
  # These are stored in /etc/nix-fly/containers/ as individual .nix files
  imports = dynamicContainerConfigs;

  environment.systemPackages = with pkgs; [
    nixos-container systemd iproute2 iptables bridge-utils tcpdump curl jq htop vim git socat
    (python3.withPackages (ps: with ps; [ fastapi uvicorn pydantic requests ]))
  ];

  environment.etc."infra-tools.sh".source = pkgs.writeShellScript "infra-tools" ''
    #!/usr/bin/env bash
    
    CMD="$1"
    shift
    
    case "$CMD" in
      status)
        echo "=== Container Status ==="
        nixos-container list 2>/dev/null || echo "No containers"
        
        echo ""
        echo "=== Network Status ==="
        ip addr show ${bridgeName} 2>/dev/null || echo "Bridge ${bridgeName} not found"
        
        echo ""
        echo "=== Service Status ==="
        echo "Caddy: $(systemctl is-active caddy 2>/dev/null)"
        echo "Nix-Fly API: $(systemctl is-active nix-fly-api 2>/dev/null)"
        
        echo ""
        echo "=== Port Tests ==="
        for port in 80 443 8000 8080 8081 5432; do
          if timeout 2 bash -c "cat < /dev/null > /dev/tcp/localhost/\$port" 2>/dev/null; then
            echo "Port \$port: open"
          else
            echo "Port \$port: closed"
          fi
        done
        ;;
        
      logs)
        CTR="$1"
        if [ -z "$CTR" ]; then
          echo "Usage: infra logs <container-name>"
          exit 1
        fi
        nixos-container run $CTR -- journalctl -f
        ;;
        
      shell)
        CTR="$1"
        if [ -z "$CTR" ]; then
          echo "Usage: infra shell <container-name>"
          exit 1
        fi
        nixos-container root-login $CTR
        ;;
        
      api-logs)
        journalctl -u nix-fly-api -f
        ;;
        
      test)
        echo "=== Testing Services ==="
        echo ""
        echo "Nix-Fly API:"
        curl -s http://localhost:8000/ 2>&1 | head -1 || echo "Failed"
        echo ""
        echo "Caddy HTTP (port 80):"
        curl -s http://localhost/ 2>&1 | head -1 || echo "Failed"
        echo ""
        echo "API via Caddy /api/health:"
        curl -s http://localhost/api/health 2>&1 || echo "Failed"
        ;;
        
      *)
        echo "Container Infrastructure Manager"
        echo ""
        echo "Commands:"
        echo "  status         - Show container and network status"
        echo "  logs <ctr>     - Follow container logs"
        echo "  shell <ctr>    - Root shell in container"
        echo "  api-logs       - Follow API service logs"
        echo "  test           - Test all services"
        echo ""
        echo "Nix-Fly API:"
        echo "  https://nix.latha.org/fly/         - API docs and endpoints"
        echo "  curl https://nix.latha.org/fly/api/v1/containers"
        echo ""
        echo "Services:"
        echo "  https://nix.latha.org/api/         - API Server (container)"
        echo "  https://nix.latha.org/worker/      - Worker (container)"
        ;;
    esac
  '';

  environment.shellAliases = {
    infra = "bash /etc/infra-tools.sh";
  };

  services.openssh = {
    enable = true;
    settings = {
      PermitRootLogin = "no";
      PasswordAuthentication = false;
    };
  };

  users.users.root.hashedPassword = "!";
  
  users.users.nixos = {
    isNormalUser = true;
    extraGroups = [ "wheel" ];
    openssh.authorizedKeys.keys = [
      "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIPsBDVEb9Kl3JfyOQRJE8jPtIXPjfnmv4oFGKVxvMwnH nandi@nixos"
    ];
  };

  security.sudo.wheelNeedsPassword = false;

  system.stateVersion = "24.11";
}
