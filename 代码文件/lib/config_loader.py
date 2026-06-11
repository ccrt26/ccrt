"""Unified config loader — reads JSON configs from 代码文件/config/"""
import json, os

_CONFIG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)).replace("\\lib", "\\config"))
_cache = {}

def detect_root():
    """Return project root directory."""
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def load_config(section):
    """Load a config section by name: 'paths', 'api_config', 'thresholds'."""
    if section in _cache:
        return _cache[section]
    path = os.path.join(_CONFIG_DIR, f"{section}.json")
    if not os.path.exists(path):
        raise FileNotFoundError(f"Config file not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        config = json.load(f)
    _cache[section] = config
    return config

def get_path(key):
    """Resolve a dotted path key against paths.json directories."""
    paths = load_config("paths")
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    d = paths.get("directories", {})
    for part in key.split("."):
        if isinstance(d, dict):
            d = d.get(part)
        else:
            break
    if isinstance(d, str):
        return os.path.join(root, d)
    return None
