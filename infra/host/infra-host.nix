# Infrastructure Host Configuration
# Manages dynamic NixOS containers via NCP API

{ config, pkgs, lib, containerNetwork, ... }:

let
  bridgeName = "ctrs";
  subnet = containerNetwork.subnet;
  gateway = containerNetwork.gateway;

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

  # NCP API Service (dynamic imperative containers, no rebuilds)
  systemd.services.ncp-api = {
    description = "NCP Container Management API";
    wantedBy = [ "multi-user.target" ];
    after = [ "network.target" ];
    
    path = with pkgs; [ nixos-container iptables bash coreutils nix ];
    
    environment = {
      NIX_PATH = "nixpkgs=/nix/var/nix/profiles/per-user/root/channels/nixos";
    };
    
    serviceConfig = {
      Type = "simple";
      ExecStart = "${pkgs.python3.withPackages (ps: with ps; [ fastapi uvicorn pydantic ])}/bin/python3 /home/nixos/code/ncp/infra/api/main.py";
      Restart = "always";
      RestartSec = 5;
      User = "root";
      Group = "root";
      StateDirectory = "ncp";
    };
  };

  # Caddy reverse proxy
  services.caddy = {
    enable = true;
    
    extraConfig = ''
      nix.latha.org {
        # API calls at /api/* - proxy with path intact
        handle /api/* {
          reverse_proxy localhost:8000
        }
        
        # Root path / - HTML frontend
        handle / {
          reverse_proxy localhost:8000
        }
        
        # All other paths to API
        handle {
          reverse_proxy localhost:8000
        }
      }
      
      http://nix.latha.org {
        redir https://nix.latha.org{uri} permanent
      }
      
      :80 {
        # API calls at /api/*
        handle /api/* {
          reverse_proxy localhost:8000
        }
        
        # All paths to API
        handle {
          reverse_proxy localhost:8000
        }
      }
    '';
  };

  # Firewall
  networking.firewall = {
    enable = true;
    trustedInterfaces = [ bridgeName ];
    
    allowedTCPPorts = [ 
      22      # SSH
      80      # HTTP (Caddy)
      443     # HTTPS (Caddy)
      8000    # NCP API (internal)
    ];
    
    extraCommands = ''
      # Enable IP forwarding
      echo 1 > /proc/sys/net/ipv4/ip_forward
      
      # Enable proxy ARP on container interfaces for inter-container communication
      for iface in /proc/sys/net/ipv4/conf/ve-*/proxy_arp; do
        if [ -f "$iface" ]; then
          echo 1 > "$iface"
        fi
      done
      
      # Allow traffic between containers
      iptables -A FORWARD -i ${bridgeName} -o ${bridgeName} -j ACCEPT
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
    };
  };

  # No static containers - all dynamic via NCP API
  containers = {};

  environment.systemPackages = with pkgs; [
    nixos-container systemd iproute2 iptables bridge-utils tcpdump curl jq htop vim git socat
    (python3.withPackages (ps: with ps; [ fastapi uvicorn pydantic requests pyjwt ]))
  ];

  environment.etc."ncp-tools.sh".source = pkgs.writeShellScript "ncp-tools" ''
    #!/usr/bin/env bash
    
    CMD="$1"
    shift
    
    case "$CMD" in
      status)
        echo "=== Container Status ==="
        nixos-container list 2>/dev/null || echo "No containers"
        
        echo ""
        echo "=== Service Status ==="
        echo "Caddy: $(systemctl is-active caddy 2>/dev/null)"
        echo "NCP API: $(systemctl is-active ncp-api 2>/dev/null)"
        
        echo ""
        echo "=== API Test ==="
        curl -s http://localhost:8000/ | jq -r '.version, .description' 2>/dev/null || echo "API not responding"
        ;;
        
      logs)
        CTR="$1"
        if [ -z "$CTR" ]; then
          echo "Usage: ncp logs <container-name>"
          exit 1
        fi
        nixos-container run $CTR -- journalctl -f
        ;;
        
      shell)
        CTR="$1"
        if [ -z "$CTR" ]; then
          echo "Usage: ncp shell <container-name>"
          exit 1
        fi
        nixos-container root-login $CTR
        ;;
        
      api-logs)
        journalctl -u ncp-api -f
        ;;
        
      *)
        echo "NCP - Nix Container Platform"
        echo ""
        echo "Commands:"
        echo "  status         - Show container and service status"
        echo "  logs <ctr>     - Follow container logs"
        echo "  shell <ctr>    - Root shell in container"
        echo "  api-logs       - Follow NCP API logs"
        echo ""
        echo "API: https://nix.latha.org/api/"
        ;;
    esac
  '';

  environment.shellAliases = {
    ncp = "bash /etc/ncp-tools.sh";
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
