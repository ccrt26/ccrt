#!/usr/bin/env python3
"""飞书即时通信桥接：轮询群消息 → 指令队列 → 结果回传。零入站，纯标准库。

用法:
  python3 feishu_bridge.py --init        首次联通性验证
  python3 feishu_bridge.py --once        单次执行（launchd 调用）
  python3 feishu_bridge.py --config PATH 指定配置路径
"""

import argparse
import json
import os
import re
import stat
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------
FEISHU_AUTH_URL = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
FEISHU_MESSAGES_URL = "https://open.feishu.cn/open-apis/im/v1/messages"
FEISHU_REPLY_URL = "https://open.feishu.cn/open-apis/im/v1/messages/{msg_id}/reply"
FEISHU_SEND_URL = "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id"

CONNECT_TIMEOUT = 10
READ_TIMEOUT = 30
MAX_DEDUP = 200
PAGE_SIZE = 10

DANGEROUS_PATTERNS = [
    (r"\brm\s+(-[^\s]*r[^\s]*\s+|.*/.*)", "文件删除: rm"),
    (r"\b(rmdir|del)\b", "文件删除"),
    (r"\bgit\s+reset\s+--hard", "Git硬重置"),
    (r"\bgit\s+push\s+--force", "Git强制推送"),
    (r"\bgit\s+push\s+-f\b", "Git强制推送"),
    (r"\.(env|pem|key|pfx|p12)\b", "读取凭证文件"),
    (r"\b(credentials|secret|password|token)\s*[:=]", "凭证赋值"),
    (r"\b(private_key|privatekey|id_rsa|id_ed25519)\b", "私钥访问"),
    (r"\.claude[/\\]hooks", "修改Hook脚本"),
    (r"\.git[/\\]hooks", "修改Git Hook"),
    (r"\bchmod\s+777\b", "权限绕过"),
    (r"--no-verify|--no-gpg-sign", "绕过Git验证"),
    (r"\bsubprocess\b", "Shell执行"),
    (r"\bos\.system\b", "Shell执行"),
    (r"\beval\s*\(|exec\s*\(|__import__\s*\(", "代码注入"),
    (r"\bexport\s+\w*KEY", "导出凭证"),
    (r"\bcurl\s+.*\.env\b", "外部泄露凭证"),
    (r"\bcat\s+\S*secret", "读取凭证文件"),
]

DEFAULT_CONFIG_PATH = os.path.expanduser("~/.feishu_bot_tmp.json")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
IM_QUEUE_DIR = os.path.join(PROJECT_ROOT, ".claude", "im_queue")
LOG_DIR = os.path.join(PROJECT_ROOT, "临时报告", "对话日志")


def _ensure_dirs():
    os.makedirs(IM_QUEUE_DIR, exist_ok=True)
    os.makedirs(LOG_DIR, exist_ok=True)


# ---------------------------------------------------------------------------
# FeishuBridge
# ---------------------------------------------------------------------------
class FeishuBridge:
    def __init__(self, config_path=None):
        path = config_path or DEFAULT_CONFIG_PATH
        self._check_file_permission(path)
        with open(path, "r", encoding="utf-8") as f:
            self.cfg = json.load(f)
        self._validate_config()
        self._token = None
        self._token_expires_at = 0
        self._dedup_path = os.path.join(IM_QUEUE_DIR, "processed_ids.json")
        self._pending_path = os.path.join(IM_QUEUE_DIR, "pending.json")
        self._done_path = os.path.join(IM_QUEUE_DIR, "done.json")
        self._log_file = os.path.join(LOG_DIR, f"feishu_bridge_{datetime.now().strftime('%Y-%m-%d')}.log")
        _ensure_dirs()

    # ---- config validation ----

    @staticmethod
    def _check_file_permission(path):
        if not os.path.exists(path):
            _log_stderr("FATAL", f"配置文件不存在: {path}")
            sys.exit(1)
        mode = os.stat(path).st_mode
        perm = mode & 0o777
        if perm != 0o600:
            _log_stderr("FATAL", f"配置文件权限错误: {path} (期望 600, 实际 {oct(perm)[2:]})")
            sys.exit(1)

    def _validate_config(self):
        for key in ("app_id", "app_secret", "chat_id"):
            if key not in self.cfg:
                _log_stderr("FATAL", f"配置文件缺少必填字段: {key}")
                sys.exit(1)
        # P1-01 安全守卫：缺少安全配置拒绝启动
        if not self.cfg.get("allowed_users"):
            _log_stderr("FATAL", "配置文件缺少 allowed_users（发送者白名单），拒绝启动")
            sys.exit(1)
        if not self.cfg.get("command_whitelist"):
            _log_stderr("FATAL", "配置文件缺少 command_whitelist（命令白名单），拒绝启动")
            sys.exit(1)
        if not self.cfg.get("route_table"):
            _log_stderr("FATAL", "配置文件缺少 route_table（路由映射），拒绝启动")
            sys.exit(1)

    # ---- logging ----

    def _log(self, level, msg):
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{ts}] {level:<6} {msg}"
        print(line, file=sys.stderr)
        try:
            with open(self._log_file, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError:
            pass

    # ---- HTTP ----

    def _request(self, url, data=None, method="GET", timeout=None):
        """统一 HTTP 请求，含超时和基础异常处理。返回 (body_dict, ok)"""
        to = timeout or READ_TIMEOUT
        try:
            body = json.dumps(data).encode("utf-8") if data else None
            req = urllib.request.Request(
                url,
                data=body,
                headers={
                    "Content-Type": "application/json; charset=utf-8",
                    "Authorization": f"Bearer {self._token}",
                },
                method=method,
            )
            with urllib.request.urlopen(req, timeout=to) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                code = result.get("code", -1)
                if code != 0:
                    self._log("WARN", f"飞书API返回错误: code={code} msg={result.get('msg', '')}")
                    return result, False
                return result, True
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            self._log("WARN", f"HTTP {e.code}: {url} body={body[:200]}")
            if e.code == 401:
                self._token = None  # 强制刷新
            return None, False
        except urllib.error.URLError as e:
            self._log("WARN", f"网络错误: {url} reason={e.reason}")
            return None, False
        except Exception as e:
            self._log("WARN", f"请求异常: {url} {e}")
            return None, False

    # ---- auth ----

    def _get_token(self):
        if self._token and time.time() < self._token_expires_at - 60:
            return True  # token still valid
        self._log("INFO", "获取 tenant_access_token ...")
        try:
            body = json.dumps({
                "app_id": self.cfg["app_id"],
                "app_secret": self.cfg["app_secret"],
            }).encode("utf-8")
            req = urllib.request.Request(
                FEISHU_AUTH_URL,
                data=body,
                headers={"Content-Type": "application/json; charset=utf-8"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=CONNECT_TIMEOUT) as resp:
                result = json.loads(resp.read().decode("utf-8"))
            if result.get("code") != 0:
                self._log("FATAL", f"获取token失败: {result.get('msg')}")
                return False
            self._token = result["tenant_access_token"]
            self._token_expires_at = time.time() + result.get("expire", 7200)
            self._log("INFO", f"Token就绪 (expires_in={result.get('expire')}s)")
            return True
        except Exception as e:
            self._log("FATAL", f"获取token异常: {e}")
            return False

    # ---- messages ----

    def fetch_messages(self):
        """拉取群最新消息。返回消息列表或空列表。"""
        if not self._get_token():
            return []
        url = f"{FEISHU_MESSAGES_URL}?container_id_type=chat&container_id={self.cfg['chat_id']}&page_size={PAGE_SIZE}&sort_type=ByCreateTimeDesc"
        result, ok = self._request(url, timeout=READ_TIMEOUT)
        if not ok or result is None:
            return []
        items = result.get("data", {}).get("items", [])
        self._log("INFO", f"拉取消息: {len(items)} 条")
        return items

    def _dedup(self, msg_id):
        """检查 msg_id 是否已处理；未处理则记录并返回 False。环形裁剪。"""
        processed = self._load_processed()
        if msg_id in processed:
            return True
        processed.append(msg_id)
        if len(processed) > MAX_DEDUP:
            processed = processed[-MAX_DEDUP:]
        self._save_processed(processed)
        return False

    def _load_processed(self):
        try:
            with open(self._dedup_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    def _save_processed(self, ids):
        _ensure_dirs()
        with open(self._dedup_path, "w", encoding="utf-8") as f:
            json.dump(ids, f, ensure_ascii=False)

    def filter_new(self, messages):
        """去重 + 安全检查 + 提取 @机器人 指令文本。返回 [(msg_id, cmd_text), ...]。

        三层防护：发送者白名单 → 危险模式 → 命令白名单
        """
        commands = []
        allowed_users = self.cfg.get("allowed_users", [])
        cmd_whitelist = self.cfg.get("command_whitelist", [])

        for msg in messages:
            msg_id = msg.get("message_id", "")
            if not msg_id or self._dedup(msg_id):
                continue
            sender = msg.get("sender", {})
            sender_id = sender.get("id", "")

            # 跳过机器人自己的消息
            if sender.get("id_type") == "app_id" and sender_id == self.cfg["app_id"]:
                continue

            # L1: 发送者白名单
            if allowed_users and sender_id not in allowed_users:
                self._log("REJECT", f"非授权用户: {sender_id} → 消息不入队")
                continue

            content = json.loads(msg.get("body", {}).get("content", "{}"))
            text = content.get("text", "")
            if not text:
                continue
            cmd = self._extract_command(text)
            if not cmd:
                continue

            # L2: 危险指令拦截
            dangerous, reason = self._is_dangerous(cmd)
            if dangerous:
                self._log("REJECT", f"危险指令 [{reason}]: {cmd[:100]}")
                continue

            # L3: 命令白名单（根命令匹配）
            root = cmd.split()[0] if cmd.split() else ""
            if cmd_whitelist and root not in cmd_whitelist:
                self._log("REJECT", f"非授权指令: {cmd[:100]}")
                continue

            # L4: 子命令正则校验
            route = self.cfg.get("route_table", {}).get(root, None)
            if route:
                patterns = self.cfg.get("command_patterns", {})
                pattern = patterns.get(route)
                if pattern and not re.match(pattern, cmd):
                    self._log("REJECT", f"子命令格式不匹配 [{route}]: {cmd[:100]}")
                    continue

            commands.append((msg_id, cmd))
        self._log("INFO", f"新指令: {len(commands)} 条")
        return commands

    def _extract_command(self, text):
        """从 @机器人 文本中提取纯指令。"""
        text = text.strip()
        for prefix in ("@铁律量化助手 ", "@铁律量化助手", ""):
            if text.startswith(prefix) and prefix:
                return text[len(prefix):].strip()
        return text if text else None

    def _is_dangerous(self, cmd):
        """检查指令是否匹配危险模式。返回 (True, reason) 或 (False, "")。"""
        for pattern, label in DANGEROUS_PATTERNS:
            if re.search(pattern, cmd, re.IGNORECASE):
                return True, label
        return False, ""

    # ---- queue ----

    def write_pending(self, commands, chat_id):
        """将新指令写入 pending.json。"""
        if not commands:
            return
        _ensure_dirs()
        queue = self._read_json(self._pending_path, "queue")
        existing_ids = {item["id"] for item in queue}
        for msg_id, cmd in commands:
            if msg_id in existing_ids:
                continue
            item = {
                "id": msg_id,
                "cmd": cmd,
                "chat_id": chat_id,
                "msg_id": msg_id,
                "status": "new",
                "ts_created": datetime.now(timezone.utc).isoformat(),
            }
            root = cmd.split()[0] if cmd.split() else ""
            route = self.cfg.get("route_table", {}).get(root, None)
            if not route:
                self._log("REJECT", f"无路由映射: {cmd[:100]}")
                continue
            item["route"] = route
            queue.append(item)
            self._log("INFO", f"入队: {msg_id[:20]}... → {cmd}")
        self._write_json(self._pending_path, {"queue": queue})

    def read_done(self):
        """读取 done.json 中 status=done 且未回传的结果。"""
        results = self._read_json(self._done_path, "results")
        pending_reply = [r for r in results if r.get("status") == "done" and r.get("ts_replied") is None]
        return results, pending_reply

    def mark_replied(self, results, replied_ids):
        """标记已回传的 done 结果。"""
        replied_set = set(replied_ids)
        for r in results:
            if r.get("id") in replied_set:
                r["ts_replied"] = datetime.now(timezone.utc).isoformat()
        self._write_json(self._done_path, {"results": results})

    # ---- reply ----

    def reply_message(self, msg_id, text):
        """回复飞书群消息。"""
        if not self._get_token():
            return False
        url = FEISHU_REPLY_URL.format(msg_id=msg_id)
        body = {
            "content": json.dumps({"text": text}, ensure_ascii=False),
            "msg_type": "text",
        }
        _, ok = self._request(url, data=body, method="POST")
        if ok:
            self._log("INFO", f"回传: {msg_id[:20]}... → 已回复")
        return ok

    # ---- active push ----

    def send_message_to_chat(self, text):
        """主动发送消息到群（不依赖 msg_id，不写 pending.json）。
        用于 Cron 盘前简报、竞价校准、复盘提醒、异常告警。
        """
        if not self._get_token():
            return False
        body = {
            "receive_id": self.cfg["chat_id"],
            "msg_type": "text",
            "content": json.dumps({"text": text}, ensure_ascii=False),
        }
        _, ok = self._request(FEISHU_SEND_URL, data=body, method="POST")
        if ok:
            self._log("INFO", "主动推送: → 群聊")
        return ok

    # ---- helpers ----

    def _read_json(self, path, key):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f).get(key, [])
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    def _write_json(self, path, data):
        _ensure_dirs()
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    # ---- main routine ----

    def run(self, init_mode=False):
        chat_id = self.cfg["chat_id"]

        # 1. fetch messages
        messages = self.fetch_messages()
        if not messages:
            if init_mode:
                print("飞书API连通正常（无消息或空群）")
            return

        # 2. filter & dedup
        commands = self.filter_new(messages)

        # 3. write pending
        if commands and not init_mode:
            self.write_pending(commands, chat_id)

        # 4. read done & reply
        results, pending_reply = self.read_done()
        replied = []
        for r in pending_reply:
            rid = r["id"]
            if init_mode:
                continue  # --init 模式不实际回复
            if self.reply_message(rid, r.get("reply", "（无内容）")):
                replied.append(rid)
                time.sleep(0.3)
        if replied:
            self.mark_replied(results, replied)

        if init_mode:
            print(f"连通性验证通过: chat_id={chat_id}, 消息数={len(messages)}, 新指令数={len(commands)}")
            print("--init 模式：未写入队列，未实际回复。")


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _log_stderr(level, msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {level:<6} {msg}", file=sys.stderr)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="飞书桥接 — Claude Code 指令通道")
    parser.add_argument("--init", action="store_true", help="首次联通性验证（不写队列、不回复）")
    parser.add_argument("--once", action="store_true", help="单次执行模式（launchd 调用）")
    parser.add_argument("--config", type=str, default=None, help="配置文件路径（默认 ~/.feishu_bot_tmp.json）")
    args = parser.parse_args()

    bridge = FeishuBridge(config_path=args.config)
    bridge.run(init_mode=args.init)


if __name__ == "__main__":
    main()
