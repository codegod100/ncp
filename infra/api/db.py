"""Database operations for NCP API."""

import json
import os
from typing import Dict, Any

# Allow overriding data directory via environment variable
DATA_DIR = os.getenv("NCP_DATA_DIR", "/var/lib/ncp")
CONTAINERS_DB_FILE = os.path.join(DATA_DIR, "containers.json")
USERS_DB_FILE = os.path.join(DATA_DIR, "users.json")

# In-memory databases (loaded from disk)
containers_db: Dict[str, Any] = {}
users_db: Dict[str, Any] = {}


def load_db(filepath: str, default: dict = None) -> dict:
    """Load JSON database from disk."""
    default = default or {}
    try:
        with open(filepath, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save_db(filepath: str, data: dict) -> None:
    """Save JSON database to disk atomically."""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    temp = filepath + ".tmp"
    with open(temp, 'w') as f:
        json.dump(data, f, indent=2)
    os.rename(temp, filepath)


def init_db():
    """Initialize databases from disk."""
    global containers_db, users_db
    containers_db = load_db(CONTAINERS_DB_FILE, {})
    users_db = load_db(USERS_DB_FILE, {})
