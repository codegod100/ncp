"""Authentication utilities for NCP API."""

import os
import hashlib
import jwt
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from .db import users_db, load_db, save_db, USERS_DB_FILE

SECRET_FILE = "/var/lib/ncp/jwt_secret"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 7

security = HTTPBearer(auto_error=False)


def get_jwt_secret():
    """Load or generate JWT secret (persistent across restarts)."""
    if os.path.exists(SECRET_FILE):
        with open(SECRET_FILE, 'r') as f:
            return f.read().strip()
    # Generate new secret
    import secrets
    secret = secrets.token_hex(32)
    os.makedirs(os.path.dirname(SECRET_FILE), exist_ok=True)
    with open(SECRET_FILE, 'w') as f:
        os.chmod(SECRET_FILE, 0o600)
        f.write(secret)
    return secret


def hash_password(password: str) -> str:
    """Hash password using SHA-256 with salt."""
    import secrets
    salt = secrets.token_hex(16)
    pwdhash = hashlib.sha256((password + salt).encode()).hexdigest()
    return f"{salt}${pwdhash}"


def verify_password(password: str, stored: str) -> bool:
    """Verify password against stored hash."""
    try:
        salt, stored_hash = stored.split('$', 1)
        pwdhash = hashlib.sha256((password + salt).encode()).hexdigest()
        return pwdhash == stored_hash
    except:
        return False


def create_access_token(data: dict):
    """Create JWT access token."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, get_jwt_secret(), algorithm=ALGORITHM)


def verify_token(token: str):
    """Verify JWT token and return payload."""
    try:
        payload = jwt.decode(token, get_jwt_secret(), algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


def require_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    """Dependency to get current authenticated user."""
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")
    payload = verify_token(credentials.credentials)
    return payload.get("sub")


def optional_user(request: Request) -> Optional[str]:
    """Get user if authenticated, None otherwise."""
    auth_header = request.headers.get("authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return None
    try:
        token = auth_header[7:]
        payload = verify_token(token)
        return payload.get("sub")
    except:
        return None


def init_default_admin():
    """Create default admin user if none exists."""
    if "admin" not in users_db:
        users_db["admin"] = {
            "username": "admin",
            "password_hash": hash_password("admin123"),
            "email": "admin@nix.latha.org",
            "created_at": datetime.now().isoformat(),
            "is_admin": True
        }
        save_db(USERS_DB_FILE, users_db)
        print("Created default admin user (admin/admin123)")


from typing import Optional
