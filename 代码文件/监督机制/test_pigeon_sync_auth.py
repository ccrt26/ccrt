#!/usr/bin/env python3
"""test_pigeon_sync_auth.py — pigeon_server /api/sync 安全守卫回归测试。

验收口径：
1. 云环境无 AUTH_TOKEN → 启动失败
2. 无 token → 401
3. 错误 token → 401
4. 合法 token + 合法 payload → 200
5. 超大 body → 413
"""
import http.client
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import urllib.request
import urllib.error
from pathlib import Path

PROJECT_ROOT = str(Path(__file__).resolve().parent.parent.parent)
SERVER_SCRIPT = os.path.join(PROJECT_ROOT, "代码文件", "信鸽信息采集", "pigeon_server.py")
TEST_TOKEN = "test-secret-token-p1-02"
TEST_PORT = 18888

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


def api_call(path, method="GET", body=None, token=None, timeout=5):
    """Helper to call the server."""
    url = f"http://127.0.0.1:{TEST_PORT}{path}"
    data = json.dumps(body).encode("utf-8") if body else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        try:
            return e.code, json.loads(body)
        except json.JSONDecodeError:
            return e.code, {"error": body[:200]}
    except Exception as e:
        return None, {"error": str(e)}


# ── T1: Cloud env + no AUTH_TOKEN → startup fails ────────

print("=" * 60)
print("  T1: 云环境无 AUTH_TOKEN → 启动失败")
print("=" * 60)

env = os.environ.copy()
env["RENDER"] = "1"
env["AUTH_TOKEN"] = ""  # explicitly empty
env["DATA_DIR"] = tempfile.mkdtemp()
env["PORT"] = str(TEST_PORT)

proc = subprocess.Popen(
    [sys.executable, SERVER_SCRIPT],
    env=env,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
)
time.sleep(1.5)
rc = proc.poll()
test("T1: 云环境无 AUTH_TOKEN → 进程退出", rc is not None and rc != 0,
     f"rc={rc}, still running={rc is None}")
if proc.poll() is None:
    proc.kill()
    proc.wait()

# ── T2-T5: Start server with AUTH_TOKEN ──────────────────

print()
print("=" * 60)
print("  T2-T5: 认证 + body 上限 + date 校验 + 路径防护")
print("=" * 60)

tmpdir = tempfile.mkdtemp()
env["AUTH_TOKEN"] = TEST_TOKEN
env["RENDER"] = ""  # clear cloud flag
env["DATA_DIR"] = tmpdir

proc = subprocess.Popen(
    [sys.executable, SERVER_SCRIPT],
    env=env,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
)
time.sleep(1)
if proc.poll() is not None:
    out, err = proc.communicate()
    print(f"SERVER FAILED TO START: stdout={out[:500]} stderr={err[:500]}")
    sys.exit(1)

try:
    # T2: No token → 401
    status, body = api_call("/api/sync", method="POST", body={"test": 1})
    test("T2: 无 token → 401", status == 401, f"got {status}")

    # T3: Wrong token → 401
    status, body = api_call("/api/sync", method="POST", body={"test": 1}, token="wrong-token")
    test("T3: 错误 token → 401", status == 401, f"got {status}")

    # T4: Valid token + valid payload → 200
    valid_payload = {
        "events_db": [{"event_id": "test_001", "title": "测试事件"}],
        "daily_stats": [{"date": "2026-05-31", "fetch_time": "10:00", "total_raw": 5, "total_filtered": 3}],
    }
    status, body = api_call("/api/sync", method="POST", body=valid_payload, token=TEST_TOKEN)
    test("T4: 合法 token + 合法 payload → 200", status == 200, f"got {status}: {body}")
    if status == 200:
        test("T4a: events_db 已保存", body.get("saved", {}).get("events_db") == 1, f"got {body}")
        test("T4b: daily_stats 已保存", body.get("saved", {}).get("daily_stats_files") == 1, f"got {body}")

    # T5: Oversized body → 413 (send Content-Length > 5MB, small body)
    conn = http.client.HTTPConnection("127.0.0.1", TEST_PORT, timeout=5)
    oversized_len = 6 * 1024 * 1024  # 6MB Content-Length
    conn.request("POST", "/api/sync", body='{"test":1}',
                 headers={"Content-Type": "application/json",
                          "Authorization": f"Bearer {TEST_TOKEN}",
                          "Content-Length": str(oversized_len)})
    resp = conn.getresponse()
    status = resp.status
    body_data = json.loads(resp.read().decode("utf-8", errors="replace"))
    conn.close()
    test("T5: 超大 body → 413", status == 413,
         f"got {status}: {body_data.get('error', body_data)[:100]}")

    # T6: Invalid date format → skipped
    print()
    print("=" * 60)
    print("  T6: date 格式校验")
    print("=" * 60)
    bad_date_payload = {
        "daily_stats": [
            {"date": "2026-05-31", "fetch_time": "ok"},
            {"date": "not-a-date", "fetch_time": "bad"},
            {"date": "../../etc/passwd", "fetch_time": "escape"},
            {"date": "2026/05/31", "fetch_time": "slash"},
        ]
    }
    status, body = api_call("/api/sync", method="POST", body=bad_date_payload, token=TEST_TOKEN)
    test("T6: 含非法日期 → 仍然 200", status == 200, f"got {status}")
    # Check that only the valid date file was created
    valid_file = os.path.join(tmpdir, "2026-05-31_events.json")
    bad_file = os.path.join(tmpdir, "not-a-date_events.json")
    escape_file = os.path.join(tmpdir, ".._.._etc_passwd_events.json")
    test("T6a: 合法日期文件已创建", os.path.exists(valid_file), f"exists={os.path.exists(valid_file)}")
    test("T6b: 非法日期文件未创建", not os.path.exists(bad_file), f"exists={os.path.exists(bad_file)}")
    test("T6c: 路径逃逸文件未创建", not os.path.exists(escape_file), f"exists={os.path.exists(escape_file)}")

    # T7: Health endpoint doesn't expose data_dir
    print()
    print("=" * 60)
    print("  T7: /api/health 脱敏")
    print("=" * 60)
    status, body = api_call("/api/health")
    test("T7: /api/health → 200", status == 200, f"got {status}")
    test("T7a: 不含 data_dir", "data_dir" not in body, f"body keys: {list(body.keys())}")
    test("T7b: 含 events_count", "events_count" in body)

finally:
    proc.terminate()
    proc.wait()
    # Cleanup tmpdir
    import shutil
    shutil.rmtree(tmpdir, ignore_errors=True)


# ── Summary ─────────────────────────────────────────────
print()
print("=" * 60)
if failed == 0:
    print(f"  全部 {total}/{total} PASS")
else:
    print(f"  {failed}/{total} FAIL")
print("=" * 60)
sys.exit(0 if failed == 0 else 1)
