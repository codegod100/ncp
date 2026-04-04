{
  description = "NCP - Nix Container Platform";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-24.11";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
        python = pkgs.python3;

      in {
        # Package uses Nix python deps (sandboxed, reproducible)
        packages.default = pkgs.python3Packages.buildPythonApplication {
          pname = "ncp";
          version = "0.1.0";
          src = ./cli;
          format = "pyproject";

          nativeBuildInputs = with pkgs.python3Packages; [ setuptools ];
          propagatedBuildInputs = with pkgs.python3Packages; [ click requests ];
        };

        # Dev shell uses uv for Python dep management
        devShells.default = pkgs.mkShell {
          buildInputs = with pkgs; [
            uv
            python
          ];

          shellHook = ''
            cd cli
            if [ ! -d .venv ]; then
              echo "Creating uv venv..."
              uv venv
            fi
            echo "Installing ncp in editable mode..."
            uv pip install -e .
            cd ..
            
            # Add uv venv to PATH
            export PATH="$PWD/cli/.venv/bin:$PATH"
            
            echo "ncp CLI available (uv-managed editable install)"
            ncp --version
          '';
        };
      });
}
