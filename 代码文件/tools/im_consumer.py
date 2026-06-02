#!/usr/bin/env python3
"""IM指令消费者：轮询 pending.json → claude CLI 并行执行 → 写入 done.json。

用法:
  python3 im_consumer.py --once   单次执行（launchd 调用）
  python3 im_consumer.py --init   检查 claude CLI 可用性
"""

import argparse
import json
import os
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
IM_QUEUE_DIR = os.path.join(PROJECT_ROOT, ".claude", "im_queue")
LOG_DIR = os.path.join(PROJECT_ROOT, "临时报告", "对话日志")
PENDING_PATH = os.path.join(IM_QUEUE_DIR, "pending.json")
DONE_PATH = os.path.join(IM_QUEUE_DIR, "done.json")
EXEC_TIMEOUT = 300  # 每条指令最长 5 min
PROCESSING_TIMEOUT = 600  # 10 min: stuck processing → reset to new
CLAUDE_BIN = "/usr/local/bin/claude"
LOG_RETENTION_DAYS = 30
MAX_WORKERS = 3  # 最多同时处理 3 条

_file_lock = threading.Lock()


def _ensure_dirs():
    os.makedirs(IM_QUEUE_DIR, exist_ok=True)
    os.makedirs(LOG_DIR, exist_ok=True)


def _log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, file=sys.stderr)
    log_file = os.path.join(LOG_DIR, f"im_consumer_{datetime.now().strftime('%Y-%m-%d')}.log")
    try:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def _rotate_logs(prefix):
    try:
        now = time.time()
        for fn in os.listdir(LOG_DIR):
            if not fn.startswith(prefix):
                continue
            fpath = os.path.join(LOG_DIR, fn)
            if os.path.getmtime(fpath) < now - LOG_RETENTION_DAYS * 86400:
                os.remove(fpath)
    except OSError:
        pass


def _read_json(path, key):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f).get(key, [])
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _write_json(path, data):
    _ensure_dirs()
    with _file_lock:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)


def reset_stuck():
    queue = _read_json(PENDING_PATH, "queue")
    now = datetime.now(timezone.utc)
    changed = False
    for item in queue:
        if item.get("status") != "processing":
            continue
        ts_str = item.get("ts_processing", "")
        try:
            ts = datetime.fromisoformat(ts_str)
            if (now - ts).total_seconds() > PROCESSING_TIMEOUT:
                item["status"] = "new"
                item.pop("ts_processing", None)
                changed = True
                _log(f"重置超时: {item['id'][:30]}...")
        except (ValueError, TypeError):
            item["status"] = "new"
            changed = True
    if changed:
        _write_json(PENDING_PATH, {"queue": queue})


def pick_all_new():
    """取所有 status=new 且有 route 的指令，标记为 processing。

    无 route 的项标记为 rejected，不被消费。
    """
    queue = _read_json(PENDING_PATH, "queue")
    items = []
    changed = False
    for item in queue:
        if item.get("status") != "new":
            continue
        if not item.get("route"):
            item["status"] = "rejected"
            item["reject_reason"] = "no route"
            changed = True
            _log(f"拒绝无路由: {item['id'][:30]}... → {item.get('cmd', '?')[:80]}")
            continue
        item["status"] = "processing"
        item["ts_processing"] = datetime.now(timezone.utc).isoformat()
        items.append(item)
        changed = True
    if changed:
        _write_json(PENDING_PATH, {"queue": queue})
    return items


def execute_one(item):
    """调用 claude -p 执行单条指令，返回 (item, reply, rc)。"""
    cmd = item["cmd"]
    _log(f"执行: {item['id'][:30]}... → {cmd}")
    try:
        result = subprocess.run(
            [CLAUDE_BIN, "-p", cmd, "--output-format", "text"],
            capture_output=True,
            text=True,
            timeout=EXEC_TIMEOUT,
            cwd=PROJECT_ROOT,
        )
        reply = result.stdout.strip()
        err = result.stderr.strip()
        if result.returncode != 0:
            _log(f"claude 返回非零: {item['id'][:30]}... rc={result.returncode}")
        if err:
            _log(f"stderr: {err[:200]}")
        return item, reply[:2000] or "(空输出)", result.returncode
    except subprocess.TimeoutExpired:
        _log(f"超时({EXEC_TIMEOUT}s): {item['id'][:30]}...")
        return item, f"指令超时（{EXEC_TIMEOUT}s）：{cmd}", -1
    except FileNotFoundError:
        _log("FATAL: claude CLI 不可用")
        return item, "Claude Code CLI 未安装或不在 PATH 中", -255


def write_done(item, reply, rc):
    status = "done" if rc == 0 else "rejected"
    reject_reason = None if rc == 0 else f"exit_code={rc}"
    results = _read_json(DONE_PATH, "results")
    results.append({
        "id": item["id"],
        "status": status,
        "reply": reply[:2000],
        "error": reject_reason,
        "ts_done": datetime.now(timezone.utc).isoformat(),
        "ts_replied": None,
    })
    _write_json(DONE_PATH, {"results": results})

    queue = _read_json(PENDING_PATH, "queue")
    for it in queue:
        if it.get("id") == item["id"]:
            it["status"] = status
            it["ts_done"] = datetime.now(timezone.utc).isoformat()
            if reject_reason:
                it["reject_reason"] = reject_reason
    _write_json(PENDING_PATH, {"queue": queue})


def run():
    _rotate_logs("im_consumer")
    reset_stuck()

    items = pick_all_new()
    if not items:
        return

    _log(f"并行处理 {len(items)} 条指令 (max_workers={MAX_WORKERS})")

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(execute_one, item): item for item in items}
        for future in as_completed(futures):
            item, reply, rc = future.result()
            write_done(item, reply, rc)
            _log(f"完成: {item['id'][:30]}... → rc={rc}, len={len(reply)}")


def main():
    parser = argparse.ArgumentParser(description="IM指令消费者")
    parser.add_argument("--once", action="store_true", help="单次执行")
    parser.add_argument("--init", action="store_true", help="检查 claude CLI 可用性")
    args = parser.parse_args()

    if args.init:
        try:
            result = subprocess.run([CLAUDE_BIN, "--version"], capture_output=True, text=True, timeout=10)
            print(f"Claude CLI: {result.stdout.strip() or result.stderr.strip()}")
        except Exception as e:
            print(f"Claude CLI 不可用: {e}")
            sys.exit(1)
        return

    _ensure_dirs()
    run()


if __name__ == "__main__":
    main()
