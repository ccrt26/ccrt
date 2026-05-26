# L0 — 生成信鸽Web面板纯静态站点（GitHub Pages 等静态托管）
# 用法: python generate_static_site.py
# 输出: ../../docs/index.html（自包含，数据内嵌，零后端依赖）

import json
import os
import glob
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.normpath(os.path.join(SCRIPT_DIR, "..", ".."))
DATA_DIR = os.path.join(PROJECT_ROOT, "重点股票", "消息面数据")
CONFIG_PATH = os.path.join(SCRIPT_DIR, "pigeon_config.json")
TEMPLATE_PATH = os.path.join(SCRIPT_DIR, "pigeon_dashboard.html")
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "docs")
OUTPUT_PATH = os.path.join(OUTPUT_DIR, "index.html")

print("=== 信鸽静态站点生成器 ===")

# 1. 读取数据
print("[1/4] 读取数据...")
with open(os.path.join(DATA_DIR, "events_db.json"), "r", encoding="utf-8-sig") as f:
    events_db = json.load(f)
print(f"  事件: {len(events_db)} 条")

daily_stats = []
for fp in sorted(glob.glob(os.path.join(DATA_DIR, "[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]_events.json")), reverse=True):
    with open(fp, "r", encoding="utf-8-sig") as f:
        s = json.load(f)
    daily_stats.append({
        "date": s.get("fetch_date", ""),
        "fetch_time": s.get("fetch_time", ""),
        "total_raw": s.get("total_raw", 0),
        "total_filtered": s.get("total_filtered", 0),
        "filter_stats": s.get("filter_stats", {})
    })
print(f"  每日统计: {len(daily_stats)} 天")

with open(CONFIG_PATH, "r", encoding="utf-8-sig") as f:
    config = json.load(f)
stocks = config.get("target_stocks", [])
print(f"  股票: {len(stocks)} 只")

# 2. 构建内嵌数据
print("[2/4] 构建内嵌数据...")
embedded = {
    "events": events_db,
    "stocks": stocks,
    "daily_stats": daily_stats,
    "last_update": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
}
data_json = json.dumps(embedded, ensure_ascii=False)
data_script = f"<script>window.__PIGEON_DATA__ = {data_json};</script>"
print(f"  数据大小: {len(data_json)} 字符")

# 3. 读取模板
print("[3/4] 读取模板...")
with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
    html = f.read()

# 注入数据到 </head> 前
html = html.replace("</head>", f"{data_script}\n</head>")

# 替换 API 函数 — 用精确的起止标记
OLD_API_START = """  function api(path) {
    return fetch(path)
      .then(function(r) { if (!r.ok) throw new Error(r.status); return r.json(); })
      .catch(function(e) { console.error("API error:", path, e); return null; });
  }"""

NEW_API_FUNC = """  function api(path) {
    var D = window.__PIGEON_DATA__ || {};
    D.events = D.events || [];
    D.stocks = D.stocks || [];
    D.daily_stats = D.daily_stats || [];

    // /api/events — 筛选在 loadEvents 中使用 query string 传递
    if (path.indexOf("/api/events") === 0) {
      var qs = path.indexOf("?") >= 0 ? path.slice(path.indexOf("?")) : "";
      var params = new URLSearchParams(qs);
      var events = D.events.slice();

      if (params.get("code")) {
        var codes = params.get("code").split(",").map(function(c) { return c.trim(); });
        events = events.filter(function(e) { return codes.indexOf(e.code) !== -1; });
      }
      if (params.get("date")) {
        events = events.filter(function(e) { return e.fetch_date === params.get("date"); });
      }
      if (params.get("category")) {
        var cats = params.get("category").split(",").map(function(c) { return c.trim(); });
        events = events.filter(function(e) { return cats.indexOf(e.category) !== -1; });
      }
      if (params.get("direction")) {
        var dirs = params.get("direction").split(",").map(function(d) { return parseInt(d.trim()); });
        events = events.filter(function(e) { return dirs.indexOf(e.direction) !== -1; });
      }
      if (params.get("search")) {
        var q = params.get("search").toLowerCase();
        events = events.filter(function(e) { return e.title && e.title.toLowerCase().indexOf(q) !== -1; });
      }

      events.sort(function(a, b) { return (b.impact_score || 0) - (a.impact_score || 0); });
      return Promise.resolve(events);
    }

    // /api/summary
    if (path === "/api/summary") {
      var stockCodes = D.stocks.map(function(s) { return s.code; });
      var covered = {};
      var todayDate = "";
      var todayCount = 0;
      var totalImpact = 0;
      var byCat = {};
      var byDir = { positive: 0, negative: 0, neutral: 0 };

      D.events.forEach(function(e) {
        var fd = e.fetch_date || "";
        if (fd) {
          covered[e.code] = true;
          totalImpact += (e.impact_score || 0);
          var cat = e.category || "其他";
          byCat[cat] = (byCat[cat] || 0) + 1;
          var d = e.direction || 0;
          if (d > 0) byDir.positive++;
          else if (d < 0) byDir.negative++;
          else byDir.neutral++;
          if (!todayDate || fd > todayDate) todayDate = fd;
          if (fd === todayDate) todayCount++;
        }
      });

      var avgImpact = D.events.length > 0 ? Math.round(totalImpact / D.events.length * 10) / 10 : 0;
      var lastFetch = D.daily_stats.length > 0
        ? D.daily_stats[0].date + " " + D.daily_stats[0].fetch_time
        : "";

      return Promise.resolve({
        total_events: D.events.length,
        today_events: todayCount,
        today_date: todayDate,
        stocks_covered: Object.keys(covered).length,
        total_stocks: stockCodes.length,
        avg_impact_score: avgImpact,
        by_category: byCat,
        by_direction: byDir,
        last_fetch_time: lastFetch
      });
    }

    // /api/stocks
    if (path === "/api/stocks") return Promise.resolve(D.stocks);

    // /api/daily_stats
    if (path === "/api/daily_stats") return Promise.resolve(D.daily_stats);

    // /api/event-content
    if (path.indexOf("/api/event-content") === 0) {
      var u = new URL(path, "http://localhost");
      var evId = u.searchParams.get("event_id");
      var ev = D.events.find(function(e) { return e.event_id === evId; });
      if (ev && ev.content) return Promise.resolve({ event_id: evId, content: ev.content, cached: true });
      return Promise.resolve(null);
    }

    return Promise.resolve(null);
  }"""

if OLD_API_START in html:
    html = html.replace(OLD_API_START, NEW_API_FUNC)
    print("  API函数已替换为本地数据模式")
else:
    print("  [WARN] 未找到原api函数，尝试模糊匹配...")
    # 回退: 替换包含 "function api(path)" 的行到下一个独立的 "}"
    import re
    pattern = r'  function api\(path\) \{\s*\n\s*return fetch\(path\)[\s\S]*?\.catch\(function\(e\) \{ console\.error\("API error:", path, e\); return null; \}\);\s*\n\s*\}'
    if re.search(pattern, html):
        html = re.sub(pattern, NEW_API_FUNC, html)
        print("  API函数已替换（回退匹配）")
    else:
        print("  [ERROR] 无法找到api函数定义，请检查模板文件")

# 4. 输出
print("[4/4] 输出静态站点...")
os.makedirs(OUTPUT_DIR, exist_ok=True)
with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
    f.write(html)

size_kb = os.path.getsize(OUTPUT_PATH) / 1024
print(f"\n[OK] Static site generated: {OUTPUT_PATH}")
print(f"  Size: {size_kb:.1f} KB")
print(f"\nNext steps:")
print(f"  1. git add docs/ && git commit -m 'update static site' && git push")
print(f"  2. GitHub -> Settings -> Pages -> Source: Deploy from branch -> /docs")
print(f"  3. Visit https://ccrt26.github.io/ccrt/")
