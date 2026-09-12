"""Utilities for reading environment variables with .env file support.

Environment variables set via the web UI are written to the .env file,
but the running process doesn't automatically reload them. This module
provides a helper that reads from both the .env file and os.environ,
preferring the .env file (most recently updated) over cached os.environ values.
"""

import os
from pathlib import Path
from typing import Optional

from dotenv import dotenv_values

# Path to the .env file (project root)
ENV_FILE_PATH = Path(__file__).parent.parent.parent / ".env"


def get_env(key: str, default: Optional[str] = None) -> Optional[str]:
    """Get an environment variable, checking .env file first.

    This ensures that values set via the web UI are immediately available
    without requiring a container restart.

    Args:
        key: The environment variable name
        default: Default value if not found

    Returns:
        The value from .env file, os.environ, or default
    """
    # Read from .env file first (gets latest values set via web UI)
    if ENV_FILE_PATH.exists():
        env_values = dotenv_values(ENV_FILE_PATH)
        value = env_values.get(key)
        if value:
            return value

    # Fall back to os.environ (for Docker-provided env vars)
    return os.getenv(key, default)


def get_env_all(*keys: str) -> dict[str, Optional[str]]:
    """Get multiple environment variables at once.

    Args:
        *keys: Environment variable names to retrieve

    Returns:
        Dict mapping keys to their values (or None if not set)
    """
    env_values = {}
    if ENV_FILE_PATH.exists():
        env_values = dotenv_values(ENV_FILE_PATH)

    return {key: env_values.get(key) or os.getenv(key) for key in keys}


def get_integration_fields(name: str) -> dict:
    """Fields saved for an integration on the Integrations page.

    Credentials entered in the web UI live in the `integrations` table
    (keys like "BRIDGE IP ADDRESS", "API KEY"), not in environment
    variables, so tools read them from here first.
    """
    import json

    try:
        import psycopg

        dsn = os.getenv(
            "DATABASE_URL",
            "postgresql://gpt_home:gpt_home_secret@db:5432/gpt_home",
        )
        with psycopg.connect(dsn, connect_timeout=3) as conn:
            row = conn.execute(
                "SELECT fields::text FROM integrations WHERE name = %s",
                (name.lower(),),
            ).fetchone()
        if row and row[0]:
            return json.loads(row[0])
    except Exception:
        pass
    return {}


def get_host_ip() -> str:
    """Get the host LAN IP address from inside a Docker container."""
    import subprocess

    try:
        result = subprocess.run(
            ["nsenter", "-t", "1", "-n", "hostname", "-I"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip().split()[0]
    except Exception:
        pass

    try:
        with open("/run/gpt-home/host-ip", "r") as f:
            ip = f.read().strip()
            if ip:
                return ip
    except Exception:
        pass

    return "gpt-home.local"
