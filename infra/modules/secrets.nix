{ config, pkgs, lib, ... }:

let
  cfg = config.ncp.secrets;
in {
  options.ncp.secrets = {
    enable = lib.mkEnableOption "NCP secrets management with agenix";
    
    secretsDir = lib.mkOption {
      type = lib.types.path;
      default = "/var/lib/ncp/secrets";
      description = "Directory where encrypted secrets are stored";
    };
    
    identityPaths = lib.mkOption {
      type = lib.types.listOf lib.types.path;
      default = [ "/root/.ssh/id_ed25519" ];
      description = "SSH private keys for decrypting secrets";
    };
  };

  config = lib.mkIf cfg.enable {
    # Install agenix CLI
    environment.systemPackages = with pkgs; [ agenix age ];
    
    # Create secrets directory
    systemd.tmpfiles.rules = [
      "d ${cfg.secretsDir} 0700 root root -"
    ];
    
    # Provide a helper script for containers to access secrets
    environment.etc."ncp-secrets-helper.sh" = {
      mode = "0755";
      text = ''
        #!/usr/bin/env bash
        # NCP Secrets Helper
        # Usage: ncp-secret <secret-name>
        
        SECRETS_DIR="${cfg.secretsDir}"
        
        if [ -z "$1" ]; then
          echo "Usage: ncp-secret <secret-name>" >&2
          exit 1
        fi
        
        SECRET_FILE="$SECRETS_DIR/$1.age"
        
        if [ ! -f "$SECRET_FILE" ]; then
          echo "Secret not found: $1" >&2
          exit 1
        fi
        
        # Decrypt and output
        ${pkgs.agenix}/bin/agenix -d "$SECRET_FILE"
      '';
    };
    
    # Alias for convenience
    environment.shellAliases = {
      "ncp-secret" = "bash /etc/ncp-secrets-helper.sh";
    };
  };
}
