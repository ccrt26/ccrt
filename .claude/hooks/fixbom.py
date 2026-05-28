#!/usr/bin/env python3
"""BOM fixer — ensure files are UTF-8 without BOM (ADR-6: macOS migration).

Replaces fixbom.ps1. On macOS, all files should be UTF-8 without BOM.
This script strips BOM if present and normalizes line endings to LF.
Code level: L1 (per 新安 review — not L2, no risk/veto logic).
"""
import os
import sys
from pathlib import Path

FILES = [
    ".claude/hooks/shared/pipeline-auth.py",
    ".claude/pipeline_active.json",
]


def strip_bom(filepath):
    """Read file, strip BOM if present, write back as UTF-8 without BOM, LF endings."""
    path = Path(filepath)
    if not path.exists():
        print(f"SKIP: {filepath} (not found)")
        return

    try:
        content = path.read_bytes()
    except Exception as e:
        print(f"ERROR: Cannot read {filepath}: {e}")
        return

    # Strip BOM if present
    if content.startswith(b"\xef\xbb\xbf"):
        content = content[3:]
        action = "BOM stripped"
    else:
        action = "no BOM found"

    # Normalize line endings to LF (no CRLF)
    text = content.decode("utf-8")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    path.write_text(text, encoding="utf-8")
    print(f"OK: {filepath} ({action}, LF normalized)")


def main():
    root = Path(__file__).resolve().parent.parent.parent
    for f in FILES:
        strip_bom(root / f)


if __name__ == "__main__":
    main()
