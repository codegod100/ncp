# PostgreSQL Container Configuration
# Database server accessible by other containers in the subnet

{ config, pkgs, lib, ... }:

{
  networking.firewall = {
    enable = true;
    allowedTCPPorts = [ 5432 22 ];
  };

  environment.systemPackages = with pkgs; [
    postgresql
    inetutils
    curl
    jq
  ];

  # PostgreSQL configuration
  services.postgresql = {
    enable = true;
    package = pkgs.postgresql_16;
    
    settings = {
      # Listen on all interfaces (container network)
      listen_addresses = lib.mkForce "*";
      port = 5432;
      
      # Basic performance tuning
      max_connections = 100;
      shared_buffers = "256MB";
    };
    
    # Allow connections from the container subnet
    authentication = lib.mkOverride 10 ''
      # TYPE  DATABASE    USER        ADDRESS           METHOD
      local   all         all                           trust
      host    all         all         127.0.0.1/32      trust
      host    all         all         ::1/128           trust
      host    all         all         10.100.0.0/16     trust  # Container subnet
    '';
    
    # Initial database setup
    initialScript = pkgs.writeText "postgres-init.sql" ''
      CREATE USER app WITH PASSWORD 'app' CREATEDB;
      CREATE DATABASE app OWNER app;
      GRANT ALL PRIVILEGES ON DATABASE app TO app;
      
      -- Create a simple table for testing
      \c app;
      CREATE TABLE IF NOT EXISTS jobs (
        id SERIAL PRIMARY KEY,
        name VARCHAR(255) NOT NULL,
        status VARCHAR(50) DEFAULT 'pending',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
      );
      
      INSERT INTO jobs (name, status) VALUES 
        ('test-job-1', 'completed'),
        ('test-job-2', 'pending'),
        ('test-job-3', 'running');
    '';
  };

  # Container metadata
  networking.hostName = "postgres";

  # Health check script
  environment.etc."postgres-health.sh".source = pkgs.writeShellScript "postgres-health" ''
    #!/bin/sh
    ${config.services.postgresql.package}/bin/pg_isready -h localhost -p 5432
  '';
}
