# L0 — 信鸽消息面Web面板服务器
# 设计文档: 审计报告/架构设计/design_pigeon_web_v1.0.md
# 云部署: 支持 Render/Railway，PORT/DATA_DIR/AUTH_TOKEN 从环境变量读取

import http.server
import json
import os
import glob
import urllib.parse
import urllib.request
import sys
import io

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.normpath(os.path.join(SCRIPT_DIR, "..", ".."))

# 环境变量覆盖（云部署用），本地默认值向后兼容
DATA_DIR = os.environ.get("DATA_DIR", os.path.join(PROJECT_ROOT, "重点股票", "消息面数据"))
CONTENT_CACHE_DIR = os.path.join(DATA_DIR, "content_cache")
CONFIG_PATH = os.environ.get("CONFIG_PATH", os.path.join(SCRIPT_DIR, "pigeon_config.json"))
AUTH_TOKEN = os.environ.get("AUTH_TOKEN", "")


def load_json(path):
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8-sig") as f:
        return json.load(f)


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_events_db():
    db_path = os.path.join(DATA_DIR, "events_db.json")
    data = load_json(db_path)
    if data is None:
        return []
    if isinstance(data, list):
        return data
    return []


def load_daily_stats():
    stats = []
    pattern = os.path.join(DATA_DIR, "[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]_events.json")
    for f in sorted(glob.glob(pattern), reverse=True):
        data = load_json(f)
        if data:
            stats.append({
                "date": data.get("fetch_date", ""),
                "fetch_time": data.get("fetch_time", ""),
                "total_raw": data.get("total_raw", 0),
                "total_filtered": data.get("total_filtered", 0),
                "filter_stats": data.get("filter_stats", {})
            })
    return stats


def load_stocks():
    config = load_json(CONFIG_PATH)
    if config:
        return config.get("target_stocks", [])
    return []


def extract_pdf_text(pdf_url):
    try:
        from PyPDF2 import PdfReader
        req = urllib.request.Request(pdf_url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        with urllib.request.urlopen(req, timeout=15) as resp:
            pdf_bytes = resp.read()
        reader = PdfReader(io.BytesIO(pdf_bytes))
        full_text = ""
        for page in reader.pages:
            t = page.extract_text()
            if t:
                full_text += t + "\n"
        return full_text.strip() if full_text.strip() else None
    except ImportError:
        return None
    except Exception as e:
        print(f"[pigeon-web] PDF extract error: {e}")
        return None


def get_event_content(event_id):
    os.makedirs(CONTENT_CACHE_DIR, exist_ok=True)
    cache_file = os.path.join(CONTENT_CACHE_DIR, f"{event_id}.txt")

    if os.path.exists(cache_file):
        with open(cache_file, "r", encoding="utf-8") as f:
            cached = f.read()
        if cached.strip():
            return {"content": cached, "cached": True}

    events = load_events_db()
    event = next((e for e in events if e.get("event_id") == event_id), None)
    if not event or not event.get("pdf_url"):
        return None

    pdf_url = event["pdf_url"]
    if not pdf_url.startswith("http"):
        return None

    print(f"[pigeon-web] Downloading PDF: {pdf_url}")
    text = extract_pdf_text(pdf_url)
    if text:
        with open(cache_file, "w", encoding="utf-8") as f:
            f.write(text)
        return {"content": text, "cached": False}

    return None


class PigeonHandler(http.server.SimpleHTTPRequestHandler):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=SCRIPT_DIR, **kwargs)

    def log_message(self, format, *args):
        print(f"[pigeon-web] {args[0]}")

    def send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def send_error_json(self, status, message, detail=""):
        self.send_json({"error": message, "detail": detail}, status)

    def check_auth(self):
        """检查 Authorization Bearer token（仅当 AUTH_TOKEN 已配置时）"""
        if not AUTH_TOKEN:
            return True
        auth = self.headers.get("Authorization", "")
        expected = f"Bearer {AUTH_TOKEN}"
        return auth == expected

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        params = urllib.parse.parse_qs(parsed.query)

        if path == "/api/health":
            self.send_json({
                "status": "ok",
                "version": "1.1",
                "data_dir": DATA_DIR,
                "events_count": len(load_events_db()),
                "auth_enabled": bool(AUTH_TOKEN)
            })
        elif path == "/api/events":
            self.handle_events(params)
        elif path == "/api/event-content":
            self.handle_event_content(params)
        elif path == "/api/summary":
            self.handle_summary()
        elif path == "/api/daily_stats":
            self.handle_daily_stats()
        elif path == "/api/stocks":
            self.handle_stocks()
        elif path == "/" or path == "":
            self.send_response(302)
            self.send_header("Location", "/pigeon_dashboard.html")
            self.end_headers()
        else:
            super().do_GET()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/api/sync":
            self.handle_sync()
        else:
            self.send_error_json(404, "not found")

    def handle_sync(self):
        if not self.check_auth():
            self.send_error_json(401, "unauthorized", "需要有效的 AUTH_TOKEN")
            return

        content_length = int(self.headers.get("Content-Length", 0))
        if content_length == 0:
            self.send_error_json(400, "empty body")
            return

        body = self.rfile.read(content_length)
        try:
            data = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError as e:
            self.send_error_json(400, "invalid json", str(e))
            return

        saved = {}

        if "events_db" in data:
            db_path = os.path.join(DATA_DIR, "events_db.json")
            save_json(db_path, data["events_db"])
            saved["events_db"] = len(data["events_db"])

        if "daily_stats" in data:
            for stat in data["daily_stats"]:
                date = stat.get("date", "")
                if date:
                    stat_path = os.path.join(DATA_DIR, f"{date}_events.json")
                    save_json(stat_path, stat)
            saved["daily_stats_files"] = len(data["daily_stats"])

        if "config" in data:
            save_json(CONFIG_PATH, data["config"])

        self.send_json({"status": "ok", "saved": saved})

    def handle_summary(self):
        events = load_events_db()
        stocks = load_stocks()
        covered = set()

        total = len(events)
        today_events = 0
        today_date = ""
        total_impact = 0
        by_category = {}
        by_direction = {"positive": 0, "negative": 0, "neutral": 0}

        for e in events:
            fd = e.get("fetch_date", "")
            if fd:
                covered.add(e.get("code", ""))
                total_impact += e.get("impact_score", 0)
                cat = e.get("category", "其他")
                by_category[cat] = by_category.get(cat, 0) + 1
                d = e.get("direction", 0)
                if d > 0:
                    by_direction["positive"] += 1
                elif d < 0:
                    by_direction["negative"] += 1
                else:
                    by_direction["neutral"] += 1
                if not today_date or fd > today_date:
                    today_date = fd
                if fd == today_date:
                    today_events += 1

        daily = load_daily_stats()
        last_fetch_time = ""
        if daily:
            last_fetch_time = f"{daily[0]['date']} {daily[0]['fetch_time']}"

        avg_impact = round(total_impact / total, 1) if total > 0 else 0

        self.send_json({
            "total_events": total,
            "today_events": today_events,
            "today_date": today_date,
            "stocks_covered": len(covered),
            "total_stocks": len(stocks),
            "avg_impact_score": avg_impact,
            "by_category": by_category,
            "by_direction": by_direction,
            "last_fetch_time": last_fetch_time
        })

    def handle_events(self, params):
        events = load_events_db()
        codes = params.get("code", [None])[0]
        date = params.get("date", [None])[0]
        category = params.get("category", [None])[0]
        direction = params.get("direction", [None])[0]
        search = params.get("search", [None])[0]

        if codes:
            code_list = [c.strip() for c in codes.split(",") if c.strip()]
            events = [e for e in events if e.get("code") in code_list]

        if date:
            events = [e for e in events if e.get("fetch_date") == date]

        if category:
            cat_list = [c.strip() for c in category.split(",") if c.strip()]
            events = [e for e in events if e.get("category") in cat_list]

        if direction is not None and direction != "":
            try:
                dir_vals = [int(d.strip()) for d in direction.split(",") if d.strip()]
                events = [e for e in events if e.get("direction") in dir_vals]
            except ValueError:
                pass

        if search:
            q = search.lower()
            events = [e for e in events if q in e.get("title", "").lower()]

        events.sort(key=lambda e: e.get("impact_score", 0), reverse=True)
        self.send_json(events)

    def handle_daily_stats(self):
        self.send_json(load_daily_stats())

    def handle_stocks(self):
        self.send_json(load_stocks())

    def handle_event_content(self, params):
        event_id = params.get("event_id", [None])[0]
        if not event_id:
            self.send_error_json(400, "missing event_id parameter")
            return
        result = get_event_content(event_id)
        if result is None:
            self.send_error_json(404, "content not available for this event")
            return
        self.send_json({
            "event_id": event_id,
            "content": result["content"],
            "cached": result["cached"]
        })


def main():
    port = int(os.environ.get("PORT", 8888))
    for i, arg in enumerate(sys.argv):
        if arg == "--port" and i + 1 < len(sys.argv):
            port = int(sys.argv[i + 1])

    host = "0.0.0.0" if os.environ.get("RENDER") or os.environ.get("RAILWAY_ENVIRONMENT") else "127.0.0.1"
    # --public 参数强制监听 0.0.0.0（本地测试用）
    if "--public" in sys.argv:
        host = "0.0.0.0"

    server = http.server.HTTPServer((host, port), PigeonHandler)
    print(f"[pigeon-web] 信鸽消息面面板服务启动 v1.1")
    print(f"[pigeon-web] 地址: http://{host}:{port}/pigeon_dashboard.html")
    print(f"[pigeon-web] 数据目录: {DATA_DIR}")
    print(f"[pigeon-web] 认证: {'已启用' if AUTH_TOKEN else '未启用（sync API 开放）'}")
    print(f"[pigeon-web] 按 Ctrl+C 停止服务")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[pigeon-web] 服务已停止")
        server.server_close()


if __name__ == "__main__":
    main()
