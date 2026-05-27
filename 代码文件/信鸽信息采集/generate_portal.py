# L0 -- Generate the 3-tab portal static site (GitHub Pages)
# Usage: python generate_portal.py
# Output: ../../docs/index.html + deep_analysis/ + daily_reports/

import json
import os
import glob
import shutil
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.normpath(os.path.join(SCRIPT_DIR, "..", ".."))
DATA_DIR = os.path.join(PROJECT_ROOT, "重点股票", "消息面数据")
CONFIG_PATH = os.path.join(SCRIPT_DIR, "pigeon_config.json")
TEMPLATE_PATH = os.path.join(SCRIPT_DIR, "portal_template.html")
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "docs")
OUTPUT_PATH = os.path.join(OUTPUT_DIR, "index.html")

# Source directories
DEEP_SRC = os.path.join(PROJECT_ROOT, "重点股票", "深度分析", "深度分析报告")
DAILY_SRC = os.path.join(PROJECT_ROOT, "重点股票", "股票报告")

# Output subdirectories
DEEP_OUT = os.path.join(OUTPUT_DIR, "deep_analysis")
DAILY_OUT = os.path.join(OUTPUT_DIR, "daily_reports")

print("=== 信鸽门户静态站点生成器 ===")

# [1/5] Read event data
print("[1/5] Reading event data...")
with open(os.path.join(DATA_DIR, "events_db.json"), "r", encoding="utf-8-sig") as f:
    events_db = json.load(f)
print(f"  Events: {len(events_db)} records")

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
print(f"  Daily stats: {len(daily_stats)} days")

with open(CONFIG_PATH, "r", encoding="utf-8-sig") as f:
    config = json.load(f)
stocks = config.get("target_stocks", [])
print(f"  Stocks: {len(stocks)}")

# [2/5] Scan & copy deep analysis reports (weekly dedup: per (stock, ISO week) keep latest only)
print("[2/5] Scanning deep analysis reports...")
os.makedirs(DEEP_OUT, exist_ok=True)

import re as _re

# R2: whitelist from pigeon_config.json target_stocks
target_codes = {s['code'] for s in config.get('target_stocks', [])}

# Clean up old files from previous builds (both flat and nested)
for old_dir in glob.glob(os.path.join(DEEP_OUT, "*")):
    if os.path.isdir(old_dir):
        for old_file in glob.glob(os.path.join(old_dir, "report.*")):
            os.remove(old_file)
        for old_sub in glob.glob(os.path.join(old_dir, "*/report.*")):
            os.remove(old_sub)

# Phase 1: collect all raw entries across all stock dirs
raw_entries = []

if os.path.isdir(DEEP_SRC):
    for stock_dir in sorted(os.listdir(DEEP_SRC)):
        stock_path = os.path.join(DEEP_SRC, stock_dir)
        if not os.path.isdir(stock_path):
            continue
        code = ""
        name = stock_dir
        if "(" in stock_dir and ")" in stock_dir:
            code = stock_dir[stock_dir.index("(")+1:stock_dir.index(")")]
            name = stock_dir[:stock_dir.index("(")]

        # R2: skip stocks not in config target_stocks whitelist
        if code not in target_codes:
            print(f"  {name}({code}): SKIP (不在重点股票清单)")
            continue

        html_files = sorted(glob.glob(os.path.join(stock_path, "*深度分析报告_*.html")), reverse=True)
        pdf_files = sorted(glob.glob(os.path.join(stock_path, "*深度分析报告_*.pdf")), reverse=True)

        if not html_files and not pdf_files:
            continue

        date_html = {}
        for f in html_files:
            m = _re.search(r'(\d{8})', os.path.basename(f))
            if m and m.group(1) not in date_html:
                date_html[m.group(1)] = f

        date_pdf = {}
        for f in pdf_files:
            m = _re.search(r'(\d{8})', os.path.basename(f))
            if m and m.group(1) not in date_pdf:
                date_pdf[m.group(1)] = f

        all_dates = sorted(set(list(date_html.keys()) + list(date_pdf.keys())), reverse=True)

        for date_str in all_dates:
            raw_entries.append({
                "code": code, "name": name, "date_str": date_str,
                "html_file": date_html.get(date_str),
                "pdf_file": date_pdf.get(date_str)
            })

# R1: group by (code, ISO week), keep only latest date per week
week_groups = {}
for entry in raw_entries:
    ds = entry['date_str']
    d = datetime.strptime(ds, "%Y%m%d")
    iso_year, iso_week, _ = d.isocalendar()
    week_label = f"{iso_year}-W{iso_week:02d}"
    key = (entry['code'], week_label)
    if key not in week_groups or ds > week_groups[key]['date_str']:
        e = entry.copy()
        e['week_label'] = week_label
        week_groups[key] = e

# Phase 2: copy deduped files & build index (output uses actual date_str, not week label)
deep_index = []
for (code, _), entry in sorted(week_groups.items()):
    date_str = entry['date_str']
    out_dir = os.path.join(DEEP_OUT, code, date_str)
    os.makedirs(out_dir, exist_ok=True)

    html_url = None
    html_size = None
    if entry['html_file']:
        dest = os.path.join(out_dir, "report.html")
        shutil.copy2(entry['html_file'], dest)
        html_url = f"deep_analysis/{code}/{date_str}/report.html"
        html_size = f"{os.path.getsize(dest)/1024:.0f}KB"

    pdf_url = None
    pdf_size = None
    if entry['pdf_file']:
        dest = os.path.join(out_dir, "report.pdf")
        shutil.copy2(entry['pdf_file'], dest)
        pdf_url = f"deep_analysis/{code}/{date_str}/report.pdf"
        pdf_size = f"{os.path.getsize(dest)/1024:.0f}KB"

    deep_index.append({
        "code": code,
        "name": entry['name'],
        "date": date_str,
        "html_url": html_url,
        "html_size": html_size,
        "pdf_url": pdf_url,
        "pdf_size": pdf_size,
        "missing": []
    })
    print(f"  {entry['name']}({code}): {date_str}")

print(f"  Deep analysis: {len(deep_index)} entries ({len(set(e['code'] for e in deep_index))} stocks)")

# [3/5] Scan & copy daily reports (all historical dates, whitelist-filtered)
print("[3/5] Scanning daily reports...")
os.makedirs(DAILY_OUT, exist_ok=True)
daily_index = []

# Clean up old flat-path files from previous builds
for old_dir in glob.glob(os.path.join(DAILY_OUT, "*")):
    if os.path.isdir(old_dir):
        for old_file in glob.glob(os.path.join(old_dir, "report.*")):
            os.remove(old_file)
        for old_sub in glob.glob(os.path.join(old_dir, "*/report.*")):
            os.remove(old_sub)

if os.path.isdir(DAILY_SRC):
    for stock_dir in sorted(os.listdir(DAILY_SRC)):
        stock_path = os.path.join(DAILY_SRC, stock_dir)
        if not os.path.isdir(stock_path):
            continue

        code = ""
        name = stock_dir
        if "(" in stock_dir and ")" in stock_dir:
            code = stock_dir[stock_dir.index("(")+1:stock_dir.index(")")]
            name = stock_dir[:stock_dir.index("(")]

        # R2: skip stocks not in config target_stocks whitelist
        if code not in target_codes:
            print(f"  {name}({code}): SKIP (不在重点股票清单)")
            continue

        html_files = sorted(glob.glob(os.path.join(stock_path, "*日报_*.html")), reverse=True)
        # Daily PDF: prefer 日报_*.pdf, fallback to 分析日报_*.pdf
        pdf_files_main = sorted(glob.glob(os.path.join(stock_path, "*日报_*.pdf")), reverse=True)
        pdf_files_analysis = sorted(glob.glob(os.path.join(stock_path, "*分析日报_*.pdf")), reverse=True)

        # Build date→file mapping
        date_html = {}
        for f in html_files:
            m = _re.search(r'(\d{8})', os.path.basename(f))
            if m and m.group(1) not in date_html:
                date_html[m.group(1)] = f

        date_pdf = {}
        # Prefer 日报 PDF over 分析日报 PDF for the same date
        for f in pdf_files_analysis:
            m = _re.search(r'(\d{8})', os.path.basename(f))
            if m and m.group(1) not in date_pdf:
                date_pdf[m.group(1)] = f
        for f in pdf_files_main:
            m = _re.search(r'(\d{8})', os.path.basename(f))
            if m:
                date_pdf[m.group(1)] = f  # 日报 PDF overrides 分析日报

        all_dates = sorted(set(list(date_html.keys()) + list(date_pdf.keys())), reverse=True)

        for date_str in all_dates:
            html_file = date_html.get(date_str)
            pdf_file = date_pdf.get(date_str)

            missing = []
            if not html_file:
                missing.append("html")
            if not pdf_file:
                missing.append("pdf")

            out_dir = os.path.join(DAILY_OUT, code, date_str)
            os.makedirs(out_dir, exist_ok=True)

            html_url = None
            html_size = None
            if html_file:
                dest = os.path.join(out_dir, "report.html")
                shutil.copy2(html_file, dest)
                html_url = f"daily_reports/{code}/{date_str}/report.html"
                html_size = f"{os.path.getsize(dest)/1024:.0f}KB"

            pdf_url = None
            pdf_size = None
            if pdf_file:
                dest = os.path.join(out_dir, "report.pdf")
                shutil.copy2(pdf_file, dest)
                pdf_url = f"daily_reports/{code}/{date_str}/report.pdf"
                pdf_size = f"{os.path.getsize(dest)/1024:.0f}KB"

            daily_index.append({
                "code": code,
                "name": name,
                "date": date_str,
                "html_url": html_url,
                "html_size": html_size,
                "pdf_url": pdf_url,
                "pdf_size": pdf_size,
                "missing": missing
            })

        status = "OK"
        print(f"  {name}({code}): {len(all_dates)} dates, HTML={len(date_html)} PDF={len(date_pdf)}")

print(f"  Daily reports: {len(daily_index)} entries ({len(set(e['code'] for e in daily_index))} stocks)")

# [4/5] Build embedded data & inject into template
print("[4/5] Building embedded data...")

portal_data = {
    "last_update": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    "events": events_db,
    "stocks": stocks,
    "daily_stats": daily_stats,
    "deep_analysis": deep_index,
    "daily_reports": daily_index
}

data_json = json.dumps(portal_data, ensure_ascii=False)
data_script = f"<script>window.__PORTAL_DATA__ = {data_json};</script>"
print(f"  Portal data size: {len(data_json)} chars")

# Read template
with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
    html = f.read()

# Inject data before </head>
html = html.replace("</head>", f"{data_script}\n</head>")

# Replace api() function -- same exact-match approach as generate_static_site.py
OLD_API_START = """  function api(path) {
    return fetch(path)
      .then(function(r) { if (!r.ok) throw new Error(r.status); return r.json(); })
      .catch(function(e) { console.error("API error:", path, e); return null; });
  }"""

NEW_API_FUNC = """  function api(path) {
    var D = window.__PORTAL_DATA__ || {};
    D.events = D.events || [];
    D.stocks = D.stocks || [];
    D.daily_stats = D.daily_stats || [];

    // /api/events
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
    print("  API function replaced (exact match)")
else:
    print("  [WARN] Exact match failed, trying regex fallback...")
    import re
    pattern = r'  function api\(path\) \{\s*\n\s*return fetch\(path\)[\s\S]*?\.catch\(function\(e\) \{ console\.error\("API error:", path, e\); return null; \}\);\s*\n\s*\}'
    if re.search(pattern, html):
        html = re.sub(pattern, NEW_API_FUNC, html)
        print("  API function replaced (regex fallback)")
    else:
        print("  [ERROR] Cannot find api() function in template!")

# [5/5] Output
print("[5/5] Writing portal site...")
os.makedirs(OUTPUT_DIR, exist_ok=True)
with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
    f.write(html)

size_kb = os.path.getsize(OUTPUT_PATH) / 1024
print(f"\n[OK] Portal site generated: {OUTPUT_PATH}")
print(f"  Size: {size_kb:.1f} KB")
print(f"  Deep analysis reports: {len(deep_index)} stocks")
print(f"  Daily reports: {len(daily_index)} stocks")
print(f"\nNext steps:")
print(f"  1. git add docs/ && git commit -m 'update portal site' && git push")
print(f"  2. Visit https://ccrt26.github.io/ccrt/")
