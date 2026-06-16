#!/usr/bin/env python3
"""Terminal streaming adapter for CCRT model execution.

Default mode is mock, which prints live terminal events and writes the same
events to a log file without calling a model. Real Claude Code streaming is
available only through --mode claude-stream.
"""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "代码文件" / "tools" / "ccrt_langgraph_config.json"


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def load_json(path):
    with Path(path).open("r", encoding="utf-8") as f:
        return json.load(f)


def safe_name(value):
    keep = []
    for ch in value or "stream":
        if ch.isalnum() or ch in ("-", "_", "."):
            keep.append(ch)
        else:
            keep.append("-")
    cleaned = "".join(keep).strip("-")
    return cleaned[:100] or "stream"


def open_log(config, task_id):
    log_root = Path(config.get("terminal_streaming", {}).get("log_root", "/private/tmp/ccrt_langgraph_streams"))
    log_dir = log_root / safe_name(task_id)
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{safe_name(task_id)}_terminal_stream.jsonl"
    return log_path


def emit(log_file, event):
    event = {"ts": utc_now(), **event}
    line = json.dumps(event, ensure_ascii=False)
    print(line, flush=True)
    log_file.write(line + "\n")
    log_file.flush()


def run_claude_preflight(runtime, timeout=20):
    """Verify the live model bridge before sending the real G3 prompt."""
    cmd = [
        runtime["bin"],
        "-p",
        "只回复 OK",
        "--output-format",
        "text",
    ]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return {
            "status": "BLOCK",
            "cmd": [runtime["bin"], "-p", "<preflight>", "--output-format", "text"],
            "returncode": -1,
            "stdout": "",
            "stderr": f"TIMEOUT after {timeout}s",
            "diagnosis": "live_model_bridge_preflight_timeout",
        }

    stdout = (proc.stdout or "").strip()
    stderr = (proc.stderr or "").strip()
    status = "PASS" if proc.returncode == 0 and "OK" in stdout else "BLOCK"
    diagnosis = ""
    if status != "PASS":
        combined = f"{stdout}\n{stderr}"
        if "FailedToOpenSocket" in combined or "Unable to connect to API" in combined:
            diagnosis = "live_model_bridge_network_unavailable_or_sandbox_blocked"
        else:
            diagnosis = "live_model_bridge_preflight_failed"
    return {
        "status": status,
        "cmd": [runtime["bin"], "-p", "<preflight>", "--output-format", "text"],
        "returncode": proc.returncode,
        "stdout": stdout[:200],
        "stderr": stderr[:500],
        "diagnosis": diagnosis,
        "proxy_env_present": any(os.environ.get(k) for k in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY")),
    }


def mock_stream(config, task_id, prompt):
    log_path = open_log(config, task_id)
    with log_path.open("a", encoding="utf-8") as log_file:
        emit(log_file, {
            "event": "stream_start",
            "task_id": task_id,
            "mode": "mock",
            "message": "终端直播模拟开始，不调用真实模型。",
        })
        steps = [
            ("dispatch_received", "红结@DeepSeek 已收到派单。"),
            ("read_context", "读取任务目标、允许范围、禁止事项。"),
            ("plan_execution", "生成执行计划：本次为 dry-run，不修改业务文件。"),
            ("run_validation", "模拟运行验收命令。"),
            ("self_check", "生成 G4 自检候选。"),
            ("stream_complete", "终端直播模拟完成。"),
        ]
        for event, message in steps:
            time.sleep(0.05)
            emit(log_file, {
                "event": event,
                "task_id": task_id,
                "role_runtime": "红结@DeepSeek",
                "message": message,
                "prompt_excerpt": prompt[:120],
            })
    return {
        "status": "COMPLETE",
        "task_id": task_id,
        "mode": "mock",
        "log_path": str(log_path),
    }


def claude_stream(config, task_id, prompt):
    runtime = config["model_runtimes"]["deepseek_via_claude_code"]
    cmd = (
        [runtime["bin"], "-p", prompt]
        + runtime.get("stream_args", ["--output-format", "stream-json"])
        + runtime.get("live_args", [])
    )
    log_path = open_log(config, task_id)
    with log_path.open("a", encoding="utf-8") as log_file:
        emit(log_file, {
            "event": "stream_start",
            "task_id": task_id,
            "mode": "claude-stream",
            "message": "Claude Code stream-json 已启动。",
            "cmd": [runtime["bin"], "-p", "<prompt>", *runtime.get("stream_args", []), *runtime.get("live_args", [])],
        })
        preflight = run_claude_preflight(runtime)
        emit(log_file, {
            "event": "live_model_preflight",
            "task_id": task_id,
            "status": preflight["status"],
            "returncode": preflight["returncode"],
            "diagnosis": preflight.get("diagnosis", ""),
            "proxy_env_present": preflight.get("proxy_env_present", False),
            "stderr": preflight.get("stderr", ""),
        })
        if preflight["status"] != "PASS":
            emit(log_file, {
                "event": "stream_end",
                "task_id": task_id,
                "returncode": 2,
                "reason": preflight.get("diagnosis", "live_model_bridge_preflight_failed"),
            })
            return {
                "status": "BLOCK",
                "task_id": task_id,
                "mode": "claude-stream",
                "returncode": 2,
                "log_path": str(log_path),
                "reason": preflight.get("diagnosis", "live_model_bridge_preflight_failed"),
            }
        proc = subprocess.Popen(
            cmd,
            cwd=str(ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        assert proc.stdout is not None
        for line in proc.stdout:
            line = line.rstrip("\n")
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                payload = {"raw": line}
            emit(log_file, {
                "event": "claude_stream",
                "task_id": task_id,
                "payload": payload,
            })
        stderr = proc.stderr.read() if proc.stderr else ""
        rc = proc.wait()
        if stderr.strip():
            emit(log_file, {
                "event": "stderr",
                "task_id": task_id,
                "message": stderr.strip(),
            })
        emit(log_file, {
            "event": "stream_end",
            "task_id": task_id,
            "returncode": rc,
        })
    return {
        "status": "COMPLETE" if rc == 0 else "BLOCK",
        "task_id": task_id,
        "mode": "claude-stream",
        "returncode": rc,
        "log_path": str(log_path),
    }


def main():
    parser = argparse.ArgumentParser(description="CCRT terminal streaming adapter")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--task-id", default="CCRT-TERMINAL-STREAM-SMOKE")
    parser.add_argument("--mode", choices=["mock", "claude-stream"], default="mock")
    parser.add_argument("--prompt", default="请进行一次终端直播连通性测试，不修改任何文件。")
    parser.add_argument("--summary-json", action="store_true")
    args = parser.parse_args()

    config = load_json(args.config)
    if args.mode == "mock":
        summary = mock_stream(config, args.task_id, args.prompt)
    else:
        summary = claude_stream(config, args.task_id, args.prompt)

    if args.summary_json:
        print(json.dumps({"summary": summary}, ensure_ascii=False, indent=2))
    return 0 if summary["status"] == "COMPLETE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
