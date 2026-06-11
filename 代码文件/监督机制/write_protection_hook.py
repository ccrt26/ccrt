#!/usr/bin/env python3
"""write_protection_hook.py — Code file write protection hook (v4.0).

Multi-channel input (argv/stdin/env). Actor-bound authorization with stage/scope
validation. All write attempts logged to write_events.jsonl.

Replaces v3.0. Used by .claude/settings.json PreToolUse hooks.
Code level: L2 (security infrastructure)
"""
import json
import os
import sys
import re
from datetime import datetime, timezone
from pathlib import Path

HOOK_DIR = Path(__file__).resolve().parent.parent.parent / ".claude" / "hooks"
sys.path.insert(0, str(HOOK_DIR / "shared"))

# Lazy import to avoid circular deps
def _import_auth():
    import pipeline_auth
    return pipeline_auth

PROJECT_ROOT = str(HOOK_DIR.parent.parent)
WRITE_EVENTS_FILE = os.path.join(PROJECT_ROOT, "logs", "security", "write_events.jsonl")


def parse_input():
    """Parse tool_input from argv, stdin, or env. Multi-channel with fallback."""
    tool_input_str = ""

    # Channel 1: argv
    if len(sys.argv) > 1:
        tool_input_str = sys.argv[1]

    # Channel 2: stdin (try if argv is empty or just "-")
    if not tool_input_str or tool_input_str == "-":
        try:
            if not sys.stdin.isatty():
                stdin_data = sys.stdin.read()
                if stdin_data and stdin_data.strip():
                    tool_input_str = stdin_data.strip()
        except Exception:
            pass

    # Channel 3: environment variable
    if not tool_input_str:
        tool_input_str = os.environ.get("CLAUDE_TOOL_INPUT", "")

    result = {"tool_name": "", "file_path": "", "command": ""}

    if not tool_input_str:
        return result

    # Try JSON parse
    try:
        data = json.loads(tool_input_str)
        result["tool_name"] = data.get("tool_name", data.get("tool", ""))
        result["file_path"] = data.get("file_path", "")
        result["command"] = data.get("command", "")
        return result
    except json.JSONDecodeError:
        pass

    # Regex fallback
    for key, pattern in [("file_path", r'"file_path"\s*:\s*"([^"]+)"'),
                          ("command", r'"command"\s*:\s*"([^"]*?)"(?=\s*[,}])'),
                          ("tool_name", r'"tool_name"\s*:\s*"([^"]+)"')]:
        m = re.search(pattern, tool_input_str)
        if m:
            result[key] = m.group(1)

    return result


def get_context():
    """Get actor/role/run_id from environment."""
    return {
        "actor": os.environ.get("CLAUDE_CURRENT_ACTOR", os.environ.get("CURRENT_ACTOR", "")),
        "role": os.environ.get("CLAUDE_CURRENT_ROLE", os.environ.get("CURRENT_ROLE", "")),
        "run_id": os.environ.get("CLAUDE_CURRENT_RUN_ID", os.environ.get("CURRENT_RUN_ID", "")),
    }


def log_write_event(record):
    """Append to write_events.jsonl."""
    try:
        os.makedirs(os.path.dirname(WRITE_EVENTS_FILE), exist_ok=True)
        with open(WRITE_EVENTS_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass


def resolve_file_path(raw_path):
    """Resolve file_path to a relative path within PROJECT_ROOT. Returns (rel_path, abs_path) or (None, None)."""
    if not raw_path:
        return None, None
    abs_path = os.path.abspath(raw_path)
    try:
        rel_path = os.path.relpath(abs_path, PROJECT_ROOT)
    except ValueError:
        return None, None
    if rel_path.startswith(".."):
        return None, None
    return rel_path.replace(os.sep, "/"), abs_path


def block_and_log(reason, parsed, ctx, auth_result, extra=None):
    """Log BLOCK event + print block message + exit 1."""
    ts = datetime.now(timezone.utc).isoformat()
    record = {
        "timestamp": ts,
        "actor": ctx["actor"],
        "role": ctx["role"],
        "run_id": ctx["run_id"],
        "stage": auth_result.get("stage", ""),
        "tool": parsed.get("tool_name", ""),
        "command": parsed.get("command", "")[:200],
        "file_path": parsed.get("file_path", ""),
        "decision": "BLOCK",
        "reason": reason,
        "matched_rule": extra.get("matched_rule", "") if extra else "",
        "auth_details": {k: auth_result.get(k, "") for k in ["actor", "role", "stage", "run_id", "scope_match", "gate1"]},
    }
    log_write_event(record)

    print()
    print("=" * 40)
    print("  BLOCKED — 写入保护闸门拦截")
    print("=" * 40)
    print(f"  文件: {parsed.get('file_path', '(unknown)')}")
    print(f"  原因: {reason}")
    if ctx["actor"]:
        print(f"  Actor: {ctx['actor']}  Role: {ctx['role']}  Run: {ctx['run_id']}")
    print(f"  解决: 启动标准流程 → coding 阶段 → 红结实现")
    print("=" * 40)
    print()
    sys.exit(1)


def pass_and_log(parsed, ctx, auth_result):
    """Log PASS event + exit 0."""
    ts = datetime.now(timezone.utc).isoformat()
    record = {
        "timestamp": ts,
        "actor": ctx["actor"],
        "role": ctx["role"],
        "run_id": ctx["run_id"],
        "stage": auth_result.get("stage", ""),
        "tool": parsed.get("tool_name", ""),
        "command": parsed.get("command", "")[:200],
        "file_path": parsed.get("file_path", ""),
        "decision": "PASS",
        "reason": auth_result.get("reason", ""),
        "matched_rule": "",
        "auth_details": {k: auth_result.get(k, "") for k in ["actor", "role", "stage", "run_id", "scope_match", "gate1"]},
    }
    log_write_event(record)
    sys.exit(0)


def _import_log_utils():
    sys.path.insert(0, os.path.join(PROJECT_ROOT, "scripts"))
    import log_utils
    return log_utils


def get_auth_token():
    """Read CLAUDE_AUTH_TOKEN from environment."""
    return os.environ.get("CLAUDE_AUTH_TOKEN", "").strip()


def verify_token_for_action(token_id, actor, role, action, file_path, run_id):
    """Verify token, return (ok, reason)."""
    try:
        lu = _import_log_utils()
        return lu.verify_auth_token(token_id, actor, role, action, file_path, run_id)
    except Exception as e:
        return False, f"token 校验异常: {e}"


def token_block_and_log(reason, parsed, ctx, token_id=""):
    """Log token-related block event."""
    ts = datetime.now(timezone.utc).isoformat()
    record = {
        "timestamp": ts,
        "actor": ctx["actor"],
        "role": ctx["role"],
        "run_id": ctx["run_id"],
        "tool": parsed.get("tool_name", ""),
        "command": parsed.get("command", "")[:200],
        "file_path": parsed.get("file_path", ""),
        "decision": "TOKEN_BLOCK",
        "reason": reason,
        "token_id": token_id,
    }
    log_write_event(record)
    print()
    print("=" * 40)
    print("  BLOCKED — 工程鉴权 Token 拦截")
    print("=" * 40)
    print(f"  操作: {parsed.get('tool_name', '?')}")
    print(f"  文件: {parsed.get('file_path', '(unknown)')}")
    print(f"  原因: {reason}")
    if token_id:
        print(f"  Token: {token_id}")
    if ctx["actor"]:
        print(f"  Actor: {ctx['actor']}  Role: {ctx['role']}  Run: {ctx['run_id']}")
    print(f"  解决: 通过 pipeline gate → 签发 auth token → 设置 CLAUDE_AUTH_TOKEN")
    print("=" * 40)
    print()
    sys.exit(1)


def require_auth_token(parsed, ctx, action, target_rel, targets_list):
    """Require valid auth token for the given action and target.

    Returns True if token passes. Exits with BLOCK if fails.
    """
    token_id = get_auth_token()
    if not token_id:
        token_block_and_log(
            f"缺少工程鉴权 token（{action} {target_rel}）",
            parsed, ctx, "")
        return False  # never reached

    ok, reason = verify_token_for_action(
        token_id, ctx["actor"], ctx["role"],
        action, target_rel, ctx["run_id"])
    if not ok:
        token_block_and_log(
            f"Token 验证失败: {reason}",
            parsed, ctx, token_id)
        return False

    # Bash action: check all detected targets
    if action == "Bash" and targets_list:
        for t_rel, _ in targets_list:
            ok2, reason2 = verify_token_for_action(
                token_id, ctx["actor"], ctx["role"],
                "Write", t_rel, ctx["run_id"])
            if not ok2:
                token_block_and_log(
                    f"Bash 目标路径 '{t_rel}' 不在 token 授权范围: {reason2}",
                    parsed, ctx, token_id)
                return False
    return True


def main():
    auth = _import_auth()
    parsed = parse_input()
    ctx = get_context()

    tool_name = parsed["tool_name"]
    file_path = parsed["file_path"]
    command = parsed.get("command", "")

    # ======== 工程鉴权 Token 准入 (B1/B2/B3) ========
    # 所有受保护路径的 Edit/Write/MultiEdit/Bash 都需要 token
    # AUTH_PROTECTED_PATHS 保护的路径 Read 也需要 token

    token_targets = []  # 需要 token 验证的目标路径

    if tool_name in ("Write", "Edit", "MultiEdit"):
        rel, _ = resolve_file_path(file_path)
        if rel:
            lu = _import_log_utils()
            if lu.is_auth_write_protected(rel):
                require_auth_token(parsed, ctx, tool_name, rel, [])
            # else: non-protected write path → pass without token, fall through to existing hook

    elif tool_name == "Bash":
        if command:
            try:
                from bash_write_detector import detect_writes
                detected = detect_writes(command, PROJECT_ROOT)
                if detected:
                    lu = _import_log_utils()
                    protected_targets = [d for d in detected if lu.is_auth_write_protected(d["path"])]
                    if protected_targets:
                        token_targets = [(d["path"], d["certainty"]) for d in protected_targets]
                        all_paths_str = ", ".join(d["path"] for d in protected_targets)
                        require_auth_token(parsed, ctx, "Bash", all_paths_str, token_targets)
                    # else: no protected targets → pass without token
            except ImportError:
                if re.search(r'[>]|tee\s|cp\s|mv\s|rm\s|sed\s+-i|perl\s+-pi', command):
                    token_targets.append(("(bash_write_detected)", "low"))
                    require_auth_token(parsed, ctx, "Bash", "(bash_write)", token_targets)

    elif tool_name == "Read":
        rel, _ = resolve_file_path(file_path)
        if rel:
            # Check if the path is Read-protected
            try:
                lu = _import_log_utils()
                if lu.is_auth_read_protected(rel):
                    token_targets.append((rel, "high"))
                    require_auth_token(parsed, ctx, "Read", rel, [])
                # else: Non-protected Read: pass without token
            except Exception as e:
                token_block_and_log(
                    f"Read 保护路径 token 校验异常: {e}",
                    parsed, ctx, "")

    # --- Existing protection logic ---
    # --- Determine write targets ---
    targets = []  # list of (rel_path, certainty)

    if tool_name in ("Write", "Edit", "MultiEdit"):
        rel, abs_p = resolve_file_path(file_path)
        if rel:
            targets.append((rel, "high"))
        else:
            # Write/Edit/MultiEdit with unparseable path → BLOCK
            # We can't determine the target, but the tool IS a write tool
            # Default: assume protected territory
            block_and_log(
                "Write/Edit/MultiEdit invoked but file_path could not be resolved from input. "
                "All protected-path writes require valid pipeline authorization.",
                parsed, ctx, {}, {"matched_rule": "unresolvable_write_tool"}
            )

    elif tool_name in ("Bash",):
        if command:
            try:
                from bash_write_detector import detect_writes
                detected = detect_writes(command, PROJECT_ROOT)
                for d in detected:
                    targets.append((d["path"], d["certainty"]))
            except ImportError:
                # Fallback: if bash_write_detector not available, check for redirect patterns
                if re.search(r'[>]|tee\s|cp\s|mv\s|rm\s|sed\s+-i|perl\s+-pi', command):
                    targets.append(("(bash_write_detected)", "low"))
        else:
            # Bash without command? Unusual but pass (can't determine)
            sys.exit(0)

    # --- If no targets found, pass ---
    if not targets:
        sys.exit(0)

    # --- Check each target ---
    for target_rel, certainty in targets:
        auth_result = auth.test_pipeline_authorization(
            target_rel, PROJECT_ROOT,
            actor=ctx["actor"], role=ctx["role"],
            run_id=ctx["run_id"], tool_name=tool_name
        )

        if not auth_result["authorized"]:
            # For low-certainty detections, block with a softer message
            if certainty == "low" and "(uncertain)" in target_rel:
                block_and_log(
                    f"Bash command may write files but target could not be definitively determined. "
                    f"Suspicious command detected. Use formal pipeline (coding stage) for file modifications.",
                    parsed, ctx, auth_result, {"matched_rule": "uncertain_bash_write"}
                )
            block_and_log(
                f"Write to '{target_rel}' not authorized: {auth_result['reason']}",
                parsed, ctx, auth_result, {"matched_rule": f"protected_{certainty}"}
            )

    # All targets passed
    pass_and_log(parsed, ctx, auth_result if targets else {})


if __name__ == "__main__":
    main()
