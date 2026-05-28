# L0 — 生成信鸽Web面板纯静态站点（用于 GitHub Pages / Vercel 等静态托管）
# 用法: .\generate_static_site.ps1
# 输出: docs/index.html（自包含，数据内嵌，零后端依赖）

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Resolve-Path "$ScriptDir\..\.."
$DataDir = "$ProjectRoot\重点股票\消息面数据"
$ConfigFile = "$ScriptDir\pigeon_config.json"
$TemplateFile = "$ScriptDir\pigeon_dashboard.html"
$OutputDir = "$ProjectRoot\docs"
$OutputFile = "$OutputDir\index.html"

Write-Host "=== 信鸽静态站点生成器 ===" -ForegroundColor Cyan

# 1. 读取数据
Write-Host "[1/4] 读取数据..." -ForegroundColor Gray

$eventsDb = Get-Content "$DataDir\events_db.json" -Raw -Encoding UTF8 | ConvertFrom-Json
Write-Host "  事件: $($eventsDb.Count) 条" -ForegroundColor Green

$dailyStats = @()
Get-ChildItem "$DataDir\*-*-*_events.json" | Sort-Object Name -Descending | ForEach-Object {
    $s = Get-Content $_.FullName -Raw -Encoding UTF8 | ConvertFrom-Json
    $dailyStats += @{
        date = $s.fetch_date
        fetch_time = $s.fetch_time
        total_raw = $s.total_raw
        total_filtered = $s.total_filtered
        filter_stats = $s.filter_stats
    }
}
Write-Host "  每日统计: $($dailyStats.Count) 天" -ForegroundColor Green

$config = Get-Content $ConfigFile -Raw -Encoding UTF8 | ConvertFrom-Json
$stocks = $config.target_stocks
Write-Host "  股票: $($stocks.Count) 只" -ForegroundColor Green

# 2. 构建内嵌数据 JSON
Write-Host "[2/4] 构建内嵌数据..." -ForegroundColor Gray

$embeddedData = @{
    events = $eventsDb
    stocks = $stocks
    daily_stats = $dailyStats
    last_update = (Get-Date -Format "yyyy-MM-dd HH:mm:ss")
} | ConvertTo-Json -Depth 10 -Compress

$dataScript = "<script>window.__PIGEON_DATA__ = $embeddedData;</script>"
Write-Host "  数据大小: $($dataScript.Length) 字符" -ForegroundColor Green

# 3. 读取模板并替换
Write-Host "[3/4] 生成静态页面..." -ForegroundColor Gray

$html = Get-Content $TemplateFile -Raw -Encoding UTF8

# 替换: 在 </head> 前注入数据
$html = $html.Replace('</head>', "$dataScript`n</head>")

# 替换: 把 api() fetch 调用替换为本地数据读取
# 核心替换: 函数 api(path) → 本地数据函数
$newApiFunc = @'
function api(path) {
    var D = window.__PIGEON_DATA__ || { events: [], stocks: [], daily_stats: [], last_update: "" };

    // /api/events — 返回所有事件（筛选在 loadEvents 中处理）
    if (path.startsWith("/api/events")) {
        var url = new URL(path, "http://localhost");
        var params = Object.fromEntries(url.searchParams);
        var events = D.events || [];

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
        var events = D.events || [];
        var stockCodes = (D.stocks || []).map(function(s) { return s.code; });
        var covered = {};
        var todayDate = "";
        var todayCount = 0;
        var totalImpact = 0;
        var byCat = {};
        var byDir = { positive: 0, negative: 0, neutral: 0 };

        events.forEach(function(e) {
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

        var avgImpact = events.length > 0 ? Math.round(totalImpact / events.length * 10) / 10 : 0;
        var lastFetch = D.daily_stats && D.daily_stats.length > 0
            ? D.daily_stats[0].date + " " + D.daily_stats[0].fetch_time
            : "";

        return Promise.resolve({
            total_events: events.length,
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
    if (path === "/api/stocks") {
        return Promise.resolve(D.stocks || []);
    }

    // /api/daily_stats
    if (path === "/api/daily_stats") {
        return Promise.resolve(D.daily_stats || []);
    }

    // /api/event-content — 返回预嵌入的 content 字段
    if (path.startsWith("/api/event-content")) {
        var u = new URL(path, "http://localhost");
        var evId = u.searchParams.get("event_id");
        var ev = (D.events || []).find(function(e) { return e.event_id === evId; });
        if (ev && ev.content) {
            return Promise.resolve({ event_id: evId, content: ev.content, cached: true });
        }
        return Promise.resolve(null);
    }

    // /api/health
    if (path === "/api/health") {
        return Promise.resolve({ status: "ok", static: true, last_update: D.last_update });
    }

    return Promise.resolve(null);
}
'@

# 找到原 api 函数并替换
$oldApiPattern = 'function api\(path\) \{\s*return fetch\(path\)[\s\S]*?\.catch\(function\(e\) \{ console\.error\("API error:", path, e\); return null; \}\);\s*\}'
$html = $html -replace $oldApiPattern, $newApiFunc

# 4. 输出文件
Write-Host "[4/4] 输出静态站点..." -ForegroundColor Gray

New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$html | Set-Content -Path $OutputFile -Encoding UTF8

Write-Host ""
Write-Host "✓ 静态站点已生成: $OutputFile" -ForegroundColor Green
Write-Host "  文件大小: $((Get-Item $OutputFile).Length) 字节" -ForegroundColor Gray
Write-Host ""
Write-Host "下一步:" -ForegroundColor Cyan
Write-Host "  1. git add docs/ && git commit -m 'update static site' && git push"
Write-Host "  2. GitHub → Settings → Pages → Source: 'Deploy from a branch' → Branch: 'master' → Folder: '/docs'"
Write-Host "  3. 访问 https://ccrt26.github.io/ccrt/"
