#!/usr/bin/env python3
"""bash_write_detector.py — Static detection of file-write patterns in Bash commands.

Detects: >, >>, tee, cat >, cp, mv, rm, sed -i, perl -pi, python -c open(...,'w'),
Path.write_text, json.dump(..., open(...,'w')), and any command targeting protected extensions.

Code level: L2 (security infrastructure)
"""
import os
import re

PROTECTED_EXTENSIONS = r'\.(py|md|json|yaml|yml|toml|sh|ps1)$'

# Patterns that indicate file writes, each with a regex to extract target path
WRITE_PATTERNS = [
    # Redirection (most common)
    (r'>\s*(\S+)', 'redirect_overwrite'),
    (r'>>\s*(\S+)', 'redirect_append'),
    # tee
    (r'tee\s+(\S+)', 'tee_write'),
    (r'tee\s+-a\s+(\S+)', 'tee_append'),
    # cat >
    (r'cat\s+.*?>\s*(\S+)', 'cat_redirect'),
    # cp (copy = write to dest)
    (r'cp\s+(?:-[a-zA-Z]+\s+)*\S+\s+(\S+)', 'cp_write'),
    # mv (move = write to dest)
    (r'mv\s+(?:-[a-zA-Z]+\s+)*\S+\s+(\S+)', 'mv_write'),
    # rm (delete = destructive write)
    (r'rm\s+(?:-[a-zA-Z]+\s+)*(\S+)', 'rm_delete'),
    # sed -i (in-place edit)
    (r'sed\s+(?:-[a-zA-Z]*i[a-zA-Z]*\s+)*.*?(\S+\.(?:py|md|json|yaml|yml|toml|sh|ps1))', 'sed_inplace'),
    # perl -pi
    (r'perl\s+-pi\s+.*?(\S+)', 'perl_inplace'),
    # python -c "open(..., 'w')"
    (r'python3?\s+-c\s+.*?open\(["\']([^"\']+)["\']\s*,\s*["\']w["\']\)', 'python_open_w'),
    # Path.write_text
    (r'Path\(["\']([^"\']+)["\']\)\.write_text', 'path_write_text'),
    # json.dump with open('w')
    (r'json\.dump\(.*?open\(["\']([^"\']+)["\']\s*,\s*["\']w["\']\)', 'json_dump_w'),
    # Generic: command targeting protected extension files
    (r'(\S+\.(?:py|md|json|yaml|yml|toml|sh|ps1))', 'protected_ext_target'),
]

# Commands that are safe (read-only) even with protected file args
SAFE_COMMANDS = {'cat', 'head', 'tail', 'less', 'grep', 'find', 'ls', 'file',
                 'wc', 'stat', 'du', 'diff', 'git', 'echo', 'printf', 'true', 'false',
                 'python', 'python3', 'node', 'npm', 'npx'}


def detect_writes(command, project_root):
    """Detect file write targets in a bash command.

    Returns: list of dicts with keys: path (str), pattern (str), certainty (str: high/medium/low)
    """
    if not command or not isinstance(command, str):
        return []

    results = []
    cmd_stripped = command.strip()

    # Quick check: if it's a pure read-only command with no redirects, skip
    first_word = cmd_stripped.split()[0] if cmd_stripped.split() else ""
    has_redirect = '>' in cmd_stripped
    has_pipe_write = any(kw in cmd_stripped for kw in ('tee ', 'cp ', 'mv ', 'rm ', 'sed -i', 'perl -pi'))

    if not has_redirect and not has_pipe_write:
        if first_word in SAFE_COMMANDS and 'open(' not in cmd_stripped and 'write_text' not in cmd_stripped:
            return []

    # Check each write pattern
    for pattern, pattern_name in WRITE_PATTERNS:
        matches = re.findall(pattern, cmd_stripped)
        for match in matches:
            if isinstance(match, tuple):
                match = match[0]
            path = match.strip().strip('"').strip("'")
            if not path or path in ('>', '>>', '|'):
                continue

            # Resolve to absolute if relative
            if not os.path.isabs(path):
                path = os.path.join(project_root, path)
            path = os.path.normpath(path)

            # Determine certainty
            if pattern_name == 'protected_ext_target':
                # Only flag if actually a protected extension AND not a safe command
                if re.search(PROTECTED_EXTENSIONS, path):
                    if first_word in SAFE_COMMANDS and not has_redirect:
                        continue
                    certainty = 'low'
                else:
                    continue
            elif pattern_name in ('redirect_overwrite', 'redirect_append', 'tee_write',
                                   'tee_append', 'cat_redirect', 'sed_inplace', 'perl_inplace'):
                certainty = 'high'
            elif pattern_name in ('python_open_w', 'path_write_text', 'json_dump_w'):
                certainty = 'high'
            else:
                certainty = 'medium'

            # Validate path is under project_root
            try:
                rel = os.path.relpath(path, project_root)
                if rel.startswith('..'):
                    continue  # outside project, skip
            except ValueError:
                continue

            results.append({
                "path": rel.replace(os.sep, '/'),
                "pattern": pattern_name,
                "certainty": certainty,
            })

    # If we found nothing but command is not obviously safe, flag as uncertain
    if not results:
        suspicious = ('python' in first_word or 'python3' == first_word or
                      'node' == first_word or 'npm' == first_word or
                      'pip' == first_word or 'curl' == first_word or
                      'wget' == first_word)
        if suspicious and ('>' in cmd_stripped or '|' in cmd_stripped or ';' in cmd_stripped):
            results.append({
                "path": "(uncertain)",
                "pattern": "suspicious_command",
                "certainty": "low",
            })

    return results


def has_write_pattern(command):
    """Quick check: does this command contain any write patterns? Returns bool."""
    if not command:
        return False
    return bool(detect_writes(command, os.getcwd()))


if __name__ == "__main__":
    # Quick smoke test
    tests = [
        ('echo "hello" > test.py', True),
        ('python3 script.py', False),
        ('cat file.txt', False),
        ('cp a.py b.py', True),
        ('mv old.json new.json', True),
        ('rm -f temp.md', True),
        ('sed -i "s/a/b/g" config.yaml', True),
        ('git status', False),
        ('python3 -c "open(\'x.py\',\'w\').write(\'x\')"', True),
        ('tee output.log', True),
        ('cat data.csv > results.json', True),
        ('grep pattern *.py', False),
    ]
    for cmd, expected in tests:
        result = bool(detect_writes(cmd, os.getcwd()))
        status = "PASS" if result == expected else "FAIL"
        print(f"[{status}] {cmd[:60]:<60} => {result} (expected {expected})")
