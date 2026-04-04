{ pkgs ? import <nixpkgs> {} }:

pkgs.python3Packages.buildPythonApplication {
  pname = nix-fly-api;
  version = 1.0.0;
  
  src = builtins.path { path = ./.; name = nix-fly-api-src; };
  
  propagatedBuildInputs = with pkgs.python3Packages; [
    fastapi
    uvicorn
    pydantic
    python-dotenv
  ];
  
  doCheck = false;
}
