{ pkgs ? import <nixpkgs> {} }:

pkgs.mkShell {
  buildInputs = with pkgs.python3Packages; [
    fastapi
    uvicorn
    pydantic
    python-dotenv
    pyjwt
    passlib
  ] ++ [
    pkgs.nixos-container
  ];
  
  shellHook = ''
    echo "NCP API dev shell ready"
    echo "Run: python3 main.py"
  '';
}
