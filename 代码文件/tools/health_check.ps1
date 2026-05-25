<#
.SYNOPSIS
  铁律量化 · 数据健康检测 (L1)
.DESCRIPTION
  开机 + 流水线前置共享入口。检测API连通性、数据完整性、回填覆盖率。
  输出JSON + 可选HTML报告。L3阻断时 exit 1。
.PARAMETER Mode
  boot (开机模式, 不检查数据文件) / daily_sim / key_stock / eval
.PARAMETER DataFile
  待检数据文件路径 (boot模式可选)
.PARAMETER RootDir
  项目根目录
.PARAMETER OutputHtml
  输出HTML报告路径 (L2/L3时默认生成)
.OUTPUT
  JSON质检报告 → stdout
#>
[CmdletBinding()]
param(
    [ValidateSet("boot", "daily_sim", "key_stock", "eval")]
    [string]$Mode = "boot",
    [string]$DataFile = "",
    [string]$RootDir = "",
    [string]$OutputHtml = ""
)

if (-not $RootDir) {
    $RootDir = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
}

$result = [PSCustomObject]@{
    CheckedAt      = (Get-Date -Format "yyyy-MM-ddTHH:mm:ss")
    Mode           = $Mode
    Flag           = "normal"
    AlertLevel     = "L0"
    Passed         = $true
    T0_Status      = @{}
    T1_Status      = @{}
    T2_Status      = @{}
    BackfillCoverage = $null
    ApiLatencyMs   = 0
    Messages       = @()
    HtmlReportPath = ""
}

function Add-Msg {
    param([string]$Text, [string]$Color = "White")
    $result.Messages += "[$Color]$Text"
}

# ============================================================
# 1. API连通性检测 (主→备, 3s超时)
# ============================================================
$apiStart = Get-Date

# 腾讯行情 [1]
try {
    $tencentUrl = "http://qt.gtimg.cn/q=sh000001"
    $tencentResp = Invoke-WebRequest -Uri $tencentUrl -TimeoutSec 3 -UseBasicParsing
    $latency = [Math]::Round(((Get-Date) - $apiStart).TotalMilliseconds, 0)
    $result.ApiLatencyMs = $latency
    if ($tencentResp.Content -match "sh000001") {
        Add-Msg "腾讯API[1]正常 (${latency}ms)" "Green"
    } else {
        Add-Msg "腾讯API[1]响应异常" "Yellow"
        $result.Flag = "degraded"
    }
} catch {
    Add-Msg "腾讯API[1]不可达: $_" "Red"
    $result.Flag = "degraded"
}

# 新浪行情 [2]
try {
    $sinaUrl = "http://hq.sinajs.cn/list=sh000001"
    $sinaResp = Invoke-WebRequest -Uri $sinaUrl -TimeoutSec 3 -UseBasicParsing
    if ($sinaResp.Content -match "上证指数") {
        Add-Msg "新浪API[2]备源可用" "Green"
    } else {
        Add-Msg "新浪API[2]备源响应异常" "Yellow"
        if ($result.Flag -eq "degraded") { $result.Flag = "cached" }
    }
} catch {
    Add-Msg "新浪API[2]备源不可达" "Red"
    if ($result.Flag -eq "degraded") { $result.Flag = "cached" }
}

# 双源全挂 → L2缓存态
if ($result.Flag -eq "cached") {
    Add-Msg "双源全挂, 仅缓存可用" "Red"
}

# ============================================================
# 2. 数据文件检查 (boot模式跳过)
# ============================================================
if ($DataFile -and (Test-Path $DataFile)) {
    $fileAge = [Math]::Round(((Get-Date) - (Get-Item $DataFile).LastWriteTime).TotalHours, 1)
    if ($fileAge -gt 6) {
        Add-Msg "数据文件$($fileAge)h未更新" "Yellow"
        if ($result.Flag -ne "cached") { $result.Flag = "degraded" }
    } else {
        Add-Msg "数据文件新鲜 ($($fileAge)h)" "Green"
    }

    try {
        $data = Get-Content $DataFile -Raw -Encoding UTF8 | ConvertFrom-Json
        $records = if ($data.Recommendations) { $data.Recommendations }
                   elseif ($data.Stocks) { $data.Stocks }
                   else { @() }
        $total = @($records).Count

        if ($total -eq 0) {
            Add-Msg "数据文件无记录" "Red"
            $result.Passed = $false
            $result.Flag = "blocked"
        }

        # ---- T0字段检查 (阻断级) ----
        $t0Fields = @("Price", "PE", "TotalScore")
        $t0Missing = 0
        foreach ($r in $records) {
            foreach ($f in $t0Fields) {
                $val = $r.$f
                if ($null -eq $val -or $val -lt 0) {
                    $t0Missing++
                }
            }
        }
        $result.T0_Status = @{
            Total    = $total
            Fields   = $t0Fields
            Missing  = $t0Missing
            Passed   = ($t0Missing -eq 0)
        }
        if ($t0Missing -gt 0) {
            Add-Msg "T0字段缺失${t0Missing}处 (Price/PE/TotalScore)" "Red"
            $result.Passed = $false
            $result.Flag = "blocked"
        } else {
            Add-Msg "T0字段完整" "Green"
        }

        # ---- T1字段检查 (降级级) ----
        $t1Fields = @("FundMainNet", "NorthboundSharesRatio", "MarginRZYE")
        $t1Missing = 0
        foreach ($r in $records) {
            foreach ($f in $t1Fields) {
                if ($null -eq $r.$f) { $t1Missing++ }
            }
        }
        $t1Ratio = if ($total -gt 0) { [Math]::Round($t1Missing / ($total * $t1Fields.Count) * 100, 1) } else { 100 }
        $result.T1_Status = @{
            Total    = $total
            Fields   = $t1Fields
            Missing  = $t1Missing
            Ratio    = $t1Ratio
        }
        if ($t1Ratio -gt 50) {
            Add-Msg "T1字段缺失率${t1Ratio}% (>50%)" "Yellow"
            if ($result.Flag -eq "normal") { $result.Flag = "degraded" }
        } else {
            Add-Msg "T1字段缺失率${t1Ratio}%" "Green"
        }

        # ---- T2字段检查 (可选级, 仅记录) ----
        $t2Fields = @("PB", "PS", "PEG", "ConsensusGrowth")
        $t2Missing = 0
        foreach ($r in $records) {
            foreach ($f in $t2Fields) {
                if ($null -eq $r.$f) { $t2Missing++ }
            }
        }
        $result.T2_Status = @{
            Total   = $total
            Fields  = $t2Fields
            Missing = $t2Missing
        }
    } catch {
        Add-Msg "数据文件解析失败: $_" "Red"
        $result.Passed = $false
        $result.Flag = "blocked"
    }
} elseif ($Mode -ne "boot") {
    Add-Msg "数据文件不存在: $DataFile" "Red"
    $result.Passed = $false
    $result.Flag = "blocked"
}

# ============================================================
# 3. 回填覆盖率 (从score_history.jsonl)
# ============================================================
$historyFile = Join-Path $RootDir "代码文件\数据\score_history.jsonl"
if (Test-Path $historyFile) {
    try {
        $lines = Get-Content $historyFile -Encoding UTF8 | Where-Object { $_.Trim() -ne "" }
        $totalLines = @($lines).Count
        $filledLines = 0
        foreach ($line in $lines) {
            try {
                $rec = $line | ConvertFrom-Json
                if ($rec.ret_t1 -ne $null) { $filledLines++ }
            } catch {}
        }
        $coverage = if ($totalLines -gt 0) { [Math]::Round($filledLines / $totalLines * 100, 1) } else { 0 }
        $result.BackfillCoverage = $coverage
        if ($coverage -lt 50) {
            if ($Mode -eq "boot") {
                Add-Msg "回填覆盖率${coverage}% (boot模式, 仅告警不阻断)" "Yellow"
            } else {
                Add-Msg "回填覆盖率${coverage}% (<50%, T0阻断)" "Red"
                $result.Passed = $false
                $result.Flag = "blocked"
            }
        } elseif ($coverage -lt 80) {
            Add-Msg "回填覆盖率${coverage}% (<80%)" "Yellow"
        } else {
            Add-Msg "回填覆盖率${coverage}%" "Green"
        }
    } catch {
        Add-Msg "回填覆盖率检查失败: $_" "Yellow"
    }
} else {
    Add-Msg "score_history.jsonl不存在, 跳过回填检查" "Yellow"
    $result.BackfillCoverage = 0
}

# ============================================================
# 4. 告警级别判定
# ============================================================
if ($result.Flag -eq "blocked") {
    $result.AlertLevel = "L3"
} elseif ($result.Flag -eq "cached") {
    $result.AlertLevel = "L2"
} elseif ($result.Flag -eq "degraded") {
    $result.AlertLevel = "L1"
} else {
    $result.AlertLevel = "L0"
}

# ============================================================
# 5. 终端彩色输出
# ============================================================
$colorMap = @{ L0 = "Green"; L1 = "Yellow"; L2 = "Yellow"; L3 = "Red" }
$alertColor = $colorMap[$result.AlertLevel]
Write-Host "`n===== 数据健康检测 [$(Get-Date -Format 'HH:mm:ss')] =====" -ForegroundColor $alertColor
Write-Host "  级别: $($result.AlertLevel) | 标记: $($result.Flag) | 通过: $($result.Passed)" -ForegroundColor $alertColor
foreach ($msg in $result.Messages) {
    $cleanMsg = $msg -replace '^\[(Green|Yellow|Red|White)\]', ''
    $msgColor = if ($msg -match '\[Red\]') { "Red" }
                elseif ($msg -match '\[Yellow\]') { "Yellow" }
                elseif ($msg -match '\[Green\]') { "Green" }
                else { "White" }
    Write-Host "  $cleanMsg" -ForegroundColor $msgColor
}
Write-Host "========================================`n" -ForegroundColor $alertColor

# ============================================================
# 6. HTML报告 (L2/L3时生成)
# ============================================================
if ($result.AlertLevel -in @("L2", "L3")) {
    $templatePath = Join-Path $PSScriptRoot "health_report_template.html"
    $dateLabel = (Get-Date -Format "yyyyMMdd_HHmmss")
    if (-not $OutputHtml) {
        $reportDir = Join-Path $RootDir "临时报告"
        if (-not (Test-Path $reportDir)) { New-Item -ItemType Directory -Path $reportDir -Force | Out-Null }
        $OutputHtml = Join-Path $reportDir "health_report_${dateLabel}.html"
    }
    $result.HtmlReportPath = $OutputHtml

    $alertLabel = @{ L0 = "正常"; L1 = "降级"; L2 = "缓存态"; L3 = "阻断" }
    $alertBadge = @{ L0 = "green"; L1 = "orange"; L2 = "orange"; L3 = "red" }
    $badge = $alertBadge[$result.AlertLevel]
    $label = $alertLabel[$result.AlertLevel]

    $msgItems = ($result.Messages | ForEach-Object {
        $clean = $_ -replace '^\[(Green|Yellow|Red|White)\]', ''
        "<li>$clean</li>"
    }) -join "`n"

    $t0Color = if ($result.T0_Status.Passed) { "green" } else { "red" }

    $html = @"
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>数据健康报告 - $dateLabel</title>
<style>
body{font-family:'Microsoft YaHei',sans-serif;max-width:700px;margin:40px auto;padding:20px;color:#1a1a2e}
.badge{display:inline-block;padding:4px 16px;border-radius:12px;color:#fff;font-weight:bold;background:$badge}
h1{font-size:1.4em;margin:16px 0}
.section{border:1px solid #e0e0e0;border-radius:8px;padding:16px;margin:16px 0}
.section h2{font-size:1.1em;margin:0 0 12px 0}
.pass{color:#27ae60}.fail{color:#e74c3c}.warn{color:#e67e22}
table{width:100%;border-collapse:collapse;font-size:0.9em}
th,td{padding:6px 12px;text-align:left;border-bottom:1px solid #eee}
th{background:#f5f5f5}
.footer{margin-top:24px;font-size:0.8em;color:#999}
</style>
</head>
<body>
<h1>铁律量化 · 数据健康报告</h1>
<p>检测时间: $($result.CheckedAt) | 模式: $($result.Mode) | 状态: <span class="badge">$label</span></p>

<div class="section">
<h2>检测消息</h2>
<ul>$msgItems</ul>
</div>

<div class="section">
<h2>T0 阻断字段</h2>
<p class="$t0Color">$($result.T0_Status | ConvertTo-Json -Compress)</p>
</div>

<div class="section">
<h2>T1 降级字段</h2>
<p>$($result.T1_Status | ConvertTo-Json -Compress)</p>
</div>

<div class="section">
<h2>T2 可选字段</h2>
<p>$($result.T2_Status | ConvertTo-Json -Compress)</p>
</div>

<div class="section">
<h2>回填覆盖率</h2>
<p>$($result.BackfillCoverage)%</p>
</div>

<div class="footer">
<p>铁律量化系统 · 自动生成 · $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')</p>
</div>
</body>
</html>
"@
    try {
        $html | Set-Content $OutputHtml -Encoding UTF8
        Add-Msg "HTML报告: $OutputHtml" "White"
        Write-Host "  报告已生成: $OutputHtml" -ForegroundColor White
    } catch {
        Add-Msg "HTML报告生成失败: $_" "Yellow"
    }

    # 清理7天前的旧报告
    try {
        $reportDir = Split-Path $OutputHtml -Parent
        Get-ChildItem $reportDir -Filter "health_report_*.html" |
            Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-7) } |
            Remove-Item -Force
    } catch {}
}

# ============================================================
# 7. 输出JSON
# ============================================================
$json = $result | ConvertTo-Json -Depth 4 -Compress
Write-Output $json

# L3阻断退出
if ($result.Flag -eq "blocked") {
    exit 1
}
exit 0

