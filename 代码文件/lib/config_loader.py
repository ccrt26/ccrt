"""Unified config loader — cross-platform project config helpers."""
import json
import os
from pathlib import Path

_cache = {}

def detect_root():
    """Detect project root by walking upward until CLAUDE.md is found."""
    cur = Path(__file__).resolve()
    for candidate in [cur.parent, *cur.parents]:
        if (candidate / "CLAUDE.md").exists():
            return candidate
    return Path.cwd()

ROOT = detect_root()
_CONFIG_DIR = ROOT / "代码文件" / "config"

def load_config(section):
    """Load a config section by name: paths, api_config, thresholds."""
    if section in _cache:
        return _cache[section]
    path = _CONFIG_DIR / f"{section}.json"
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        config = json.load(f)
    _cache[section] = config
    return config

def get_path(key):
    """Resolve a dotted path key against paths.json directories."""
    paths = load_config("paths")
    value = paths.get("directories", {})
    for part in key.split("."):
        if isinstance(value, dict):
            value = value.get(part)
        else:
            value = None
            break
    if isinstance(value, str):
        return str(ROOT / value)
    return None
