#!/usr/bin/env python3
"""Runtime secret loading helpers.

Secrets stay outside the repository.  This module only reports presence and
source metadata; it never prints or returns secret values from status helpers.
"""
import os
import re
from pathlib import Path

DEFAULT_PRIVATE_ENV = Path.home() / ".ccrt" / "tielv.env"
TUSHARE_TOKEN = "TUSHARE_TOKEN"


def _strip_quotes(value):
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    return value


def parse_env_file(path):
    """Parse a small .env-style file with KEY=value or export KEY=value lines."""
    secrets = {}
    p = Path(path).expanduser()
    if not p.exists():
        return secrets
    for raw in p.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            continue
        secrets[key] = _strip_quotes(value)
    return secrets


def load_secret(name, private_env=DEFAULT_PRIVATE_ENV, allow_process_env=True):
    """Return (secret_value, metadata_without_secret)."""
    if allow_process_env:
        value = os.environ.get(name, "")
        if value:
            return value, {"status": "PASS", "source": "process_env", "private_env": str(private_env)}

    p = Path(private_env).expanduser()
    secrets = parse_env_file(p)
    value = secrets.get(name, "")
    if value:
        return value, {"status": "PASS", "source": "private_env_file", "private_env": str(p)}

    return None, {
        "status": "BLOCK",
        "source": "missing",
        "private_env": str(p),
        "private_env_exists": p.exists(),
        "reason": f"missing_runtime_env:{name}",
    }


def check_secret_readiness(name, private_env=DEFAULT_PRIVATE_ENV, launchd_compatible=False):
    """Return status metadata without the secret value.

    launchd_compatible=True intentionally ignores the interactive process
    environment, because launchd jobs do not read shell startup files.
    """
    p = Path(private_env).expanduser()
    if launchd_compatible:
        value = parse_env_file(p).get(name, "")
        if value:
            return {
                "status": "PASS",
                "name": name,
                "source": "private_env_file",
                "private_env": str(p),
                "private_env_exists": True,
                "launchd_compatible": True,
            }
        return {
            "status": "BLOCK",
            "name": name,
            "source": "missing_private_env_file" if not p.exists() else "missing_key_in_private_env_file",
            "private_env": str(p),
            "private_env_exists": p.exists(),
            "launchd_compatible": False,
            "reason": f"missing_launchd_runtime_env:{name}",
        }

    value, meta = load_secret(name, private_env=p, allow_process_env=True)
    return {
        "status": meta["status"],
        "name": name,
        "source": meta["source"],
        "private_env": str(p),
        "private_env_exists": p.exists(),
        "launchd_compatible": meta.get("source") == "private_env_file",
        "reason": meta.get("reason", ""),
    }
