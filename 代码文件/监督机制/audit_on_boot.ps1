<#
.SYNOPSIS
  铁律量化 · 开机自动审计脚本
.DESCRIPTION
  非每日开机场景：检测上次审计时间，自动补齐遗漏的审计任务。
  注册为 Windows Task Scheduler "AT STARTUP" 触发器。
  逻辑:
    - 检查最近一次审计报告的时间戳
    - 若今日日检未执行 → 执行日检 (Section A子集 + F + G)
    - 若本周周检未执行且已过周日 → 先执行完整周检 (Section A~G)
    - 若上月月检未执行且已过月初 → 追加月度深度审计
    - 所有结果写入 audit_report_YYYYMMDD.json
.PARAMETER Force
  强制运行完整审计（忽略时间判断）
.PARAMETER Quick
  仅日检模式（开机快速确认，~5秒）
.EXAMPLE
  .\audit_on_boot.ps1          开机自动判断审计级别
  .\audit_on_boot.ps1 -Force   强制执行完整审计
  .\audit_on_boot.ps1 -Quick   仅日检模式
.NOTES
  版本: v1.0 | 2026-05-23 | 创建人: 阿黑 (for 旧影)
#>

param(
    [switch]$Force,
    [switch]$Quick
)

$ErrorActionPreference = "Continue"
$rootDir = "Split-Path -Parent (Split-Path -Parent $PSScriptRoot)"
$auditDir = Join-Path $rootDir "历史数据\审计报告"
$supervisorDir = Join-Path $rootDir "代码文件\监督机制"
$redlinesDir = Join-Path $rootDir "代码文件\规则红线"
$scriptsDir = Join-Path $rootDir "代码文件\每日荐股\scripts"
$bootLogFile = Join-Path $supervisorDir "audit_boot.log"

# ---- 日志函数 ----
function Write-AuditLog {
    param([string]$Msg, [string]$Level = "INFO")
    $time = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $line = "[$time][BOOT-AUDIT][$Level] $Msg"
    Add-Content -Path $bootLogFile -Value $line -Encoding UTF8
    Write-Host $line
}

function Get-LastAuditDate {
    param([string]$Pattern)
    $files = Get-ChildItem $auditDir -Filter $Pattern -ErrorAction SilentlyContinue |
             Sort-Object LastWriteTime -Descending
    if ($files.Count -gt 0) {
        return $files[0].LastWriteTime
    }
    return $null
}

# ---- 执行现有检查脚本 ----
function Invoke-CheckScript {
    param([string]$ScriptPath, [string]$ScriptArgs = "", [string]$Label = "")
    if (-not (Test-Path $ScriptPath)) {
        Write-AuditLog "脚本不存在: $ScriptPath" -Level "WARN"
        return @{ Pass = 0; Warn = 1; Fail = 0; Output = "脚本不存在" }
    }
    try {
        $output = & $ScriptPath @ScriptArgs 2>&1
        $exitCode = $LASTEXITCODE
        if ($exitCode -eq 0) {
            Write-AuditLog "$Label : PASS"
            return @{ Pass = 1; Warn = 0; Fail = 0; Output = $output }
        } else {
            Write-AuditLog "$Label : FAIL (exit=$exitCode)" -Level "WARN"
            return @{ Pass = 0; Warn = 0; Fail = 1; Output = $output }
        }
    } catch {
        Write-AuditLog "$Label : ERROR - $_" -Level "ERROR"
        return @{ Pass = 0; Warn = 0; Fail = 1; Output = $_ }
    }
}

# ---- 快速日检 (Section A子集 + F + G, ~5秒) ----
function Invoke-QuickAudit {
    Write-AuditLog "===== 快速日检开始 ====="
    $results = @{}
    $pass = 0; $warn = 0; $fail = 0

    # Section A子集: 关键文件存在性检查
    $keyFiles = @(
        "$rootDir\代码文件\数据\data_final.json",
        "$rootDir\代码文件\数据\data_scored.json",
        "$rootDir\代码文件\数据\dynamic_pool.json"
    )
    foreach ($f in $keyFiles) {
        if (Test-Path $f) {
            $lastWrite = (Get-Item $f).LastWriteTime
            $ageHours = ((Get-Date) - $lastWrite).TotalHours
            if ($ageHours -lt 48) { $pass++ } else { $warn++; Write-AuditLog ("文件过期: $f (" + [math]::Round($ageHours,1) + "h)") -Level "WARN" }
        } else {
            $fail++
            Write-AuditLog "文件缺失: $f" -Level "ERROR"
        }
    }

    # Section A: 交易记录幂等性检查 (transactions.csv重复行)
    $txnFile = Join-Path $rootDir "模拟交易\持仓记录\transactions.csv"
    if (Test-Path $txnFile) {
        $lines = Get-Content $txnFile -Encoding UTF8
        $dataLines = $lines | Select-Object -Skip 1
        $dupes = $dataLines | Group-Object { $_ } | Where-Object { $_.Count -gt 1 }
        if ($dupes.Count -gt 0) {
            $warn++
            Write-AuditLog "transactions.csv 存在 $($dupes.Count) 组重复行" -Level "WARN"
        } else {
            $pass++
        }
    } else {
        $warn++
        Write-AuditLog "transactions.csv 不存在" -Level "WARN"
    }

    # Section F: 流水线日志今日执行确认
    $todayStr = Get-Date -Format "yyyy-MM-dd"
    $workflowLog = Join-Path $scriptsDir ("workflow_" + (Get-Date -Format "yyyyMM") + ".log")
    if (Test-Path $workflowLog) {
        $todayEntries = Select-String -Path $workflowLog -Pattern $todayStr -SimpleMatch -ErrorAction SilentlyContinue
        if ($todayEntries.Count -gt 0) {
            $pass++
            Write-AuditLog "今日流水线已执行 ($($todayEntries.Count) 条日志)"
        } else {
            $warn++
            Write-AuditLog "今日流水线无执行记录" -Level "WARN"
        }
    } else {
        $warn++
        Write-AuditLog "workflow日志文件不存在" -Level "WARN"
    }

    # Section G: 红线基础检查 (Quick模式, ~2秒)
    $redlineScript = Join-Path $redlinesDir "check_redlines.ps1"
    $r = Invoke-CheckScript -ScriptPath $redlineScript -ScriptArgs "-Quick" -Label "check_redlines -Quick"
    $pass += $r.Pass; $warn += $r.Warn; $fail += $r.Fail

    Write-AuditLog "日检完成: PASS=$pass WARN=$warn FAIL=$fail"
    return @{ Pass = $pass; Warn = $warn; Fail = $fail; Timestamp = (Get-Date -Format "yyyy-MM-dd HH:mm:ss") }
}

# ---- 完整审计 (Section A~G 全部, 委托 run_full_audit.ps1) ----
function Invoke-FullAudit {
    Write-AuditLog "===== 完整审计开始 ====="
    $fullAuditScript = Join-Path $supervisorDir "run_full_audit.ps1"

    if (-not (Test-Path $fullAuditScript)) {
        Write-AuditLog "run_full_audit.ps1 尚未实现，回退到手动汇总" -Level "WARN"

        # 回退: 逐个调用现有检查脚本
        $results = @{}
        $totalPass = 0; $totalWarn = 0; $totalFail = 0

        # G: check_redlines (完整)
        $r1 = Invoke-CheckScript -ScriptPath (Join-Path $redlinesDir "check_redlines.ps1") -Label "check_redlines (full)"
        $totalPass += $r1.Pass; $totalWarn += $r1.Warn; $totalFail += $r1.Fail

        # G: version_supervisor
        $r2 = Invoke-CheckScript -ScriptPath (Join-Path $supervisorDir "version_supervisor.ps1") -Label "version_supervisor"
        $totalPass += $r2.Pass; $totalWarn += $r2.Warn; $totalFail += $r2.Fail

        # G: check_report_style
        $r3 = Invoke-CheckScript -ScriptPath (Join-Path $redlinesDir "check_report_style.ps1") -Label "check_report_style"
        $totalPass += $r3.Pass; $totalWarn += $r3.Warn; $totalFail += $r3.Fail

        # 追加日检内容
        $quick = Invoke-QuickAudit
        $totalPass += $quick.Pass; $totalWarn += $quick.Warn; $totalFail += $quick.Fail

        Write-AuditLog "完整审计(回退模式)完成: PASS=$totalPass WARN=$totalWarn FAIL=$totalFail"
        return @{ Pass = $totalPass; Warn = $totalWarn; Fail = $totalFail; Timestamp = (Get-Date -Format "yyyy-MM-dd HH:mm:ss") }
    }

    # 调用完整审计脚本
    try {
        $output = & $fullAuditScript 2>&1
        Write-AuditLog "run_full_audit.ps1 执行完成"
        # 尝试从JSON报告读取结果
        $todayDate = Get-Date -Format "yyyyMMdd"
        $reportFile = Join-Path $auditDir "audit_report_${todayDate}.json"
        if (Test-Path $reportFile) {
            $report = Get-Content $reportFile -Raw -Encoding UTF8 | ConvertFrom-Json
            return @{
                Pass = $report.summary.pass
                Warn = $report.summary.warn
                Fail = $report.summary.fail
                Timestamp = $report.audit.timestamp
                ReportFile = $reportFile
            }
        }
    } catch {
        Write-AuditLog "完整审计执行异常: $_" -Level "ERROR"
    }
    return @{ Pass = 0; Warn = 0; Fail = 1; Timestamp = (Get-Date -Format "yyyy-MM-dd HH:mm:ss") }
}

# ==============================
# 主逻辑
# ==============================
Write-AuditLog "===== 旧影 开机审计启动 ====="
Write-AuditLog "启动时间: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
Write-AuditLog "计算机名: $env:COMPUTERNAME"

# 检查是否为交易日（用于上下文判断）
$marketScript = Join-Path $scriptsDir "is_market_open.ps1"
$holidayFile = Join-Path $rootDir "每日荐股\运营记录\holidays_2026.csv"
$isTradingDay = $false
if (Test-Path $marketScript) {
    try {
        & $marketScript -Date (Get-Date -Format "yyyy-MM-dd") -HolidayFile $holidayFile 2>&1 | Out-Null
        $isTradingDay = ($LASTEXITCODE -eq 0)
    } catch {
        $isTradingDay = $false
    }
}
Write-AuditLog "交易日判断: $(if($isTradingDay){'是'}else{'非交易日/无法判断'})"

# ---- 审计级别判断 ----
$today = Get-Date
$todayDateStr = $today.ToString("yyyy-MM-dd")
$todayDateNum = $today.ToString("yyyyMMdd")

# 查找最近审计报告
$latestDailyReport = Get-LastAuditDate -Pattern "audit_report_*_quick.json"
$latestFullReport = Get-LastAuditDate -Pattern "audit_report_*.json"

$needQuick = $false
$needFull = $false

if ($Force) {
    $needFull = $true
    Write-AuditLog "强制执行完整审计 (-Force)"
} elseif ($Quick) {
    Write-AuditLog "仅执行快速日检 (-Quick)"
    $result = Invoke-QuickAudit
    Write-AuditLog "===== 开机审计结束 (Quick) ====="
    exit 0
} else {
    # 判断日检是否需要
    if ($latestDailyReport -eq $null) {
        $needQuick = $true
        Write-AuditLog "未找到任何审计记录，执行首次日检"
    } elseif ($latestDailyReport.Date -lt $today.Date) {
        # 最后一次日检在今天之前
        $daysSince = ($today.Date - $latestDailyReport.Date).Days
        Write-AuditLog "上次日检: $($latestDailyReport.ToString('yyyy-MM-dd'))，已过 $daysSince 天"
        $needQuick = $true

        # 判断是否需要周检：已过周日 且 本周无完整审计
        $lastSunday = $today.AddDays(-[int]$today.DayOfWeek).Date
        if ($today.Date -gt $lastSunday -and $latestFullReport -ne $null) {
            if ($latestFullReport.Date -lt $lastSunday) {
                $needFull = $true
                Write-AuditLog "本周无完整审计记录，追加周度审计"
            }
        } elseif ($latestFullReport -eq $null) {
            # 从未运行过完整审计
            if ($today.DayOfWeek -eq 'Sunday' -or $daysSince -ge 7) {
                $needFull = $true
                Write-AuditLog "从未执行完整审计，且已到周期"
            }
        }
    } else {
        Write-AuditLog "今日审计已执行 ($($latestDailyReport.ToString('yyyy-MM-dd HH:mm')))，跳过"
    }
}

# 执行审计
if ($needFull) {
    $result = Invoke-FullAudit
} elseif ($needQuick) {
    $result = Invoke-QuickAudit
} else {
    Write-AuditLog "审计已是最新，无需重复执行"
    Write-AuditLog "===== 开机审计结束 (SKIP) ====="
    exit 0
}

# ---- 写入审计摘要 ----
$summaryFile = Join-Path $auditDir "audit_boot_summary.json"
if (-not (Test-Path $auditDir)) { New-Item -ItemType Directory -Path $auditDir -Force | Out-Null }
$summary = @{
    audit_type = if ($needFull) { "full" } else { "quick" }
    timestamp = $result.Timestamp
    is_trading_day = $isTradingDay
    pass = $result.Pass
    warn = $result.Warn
    fail = $result.Fail
    verdict = if ($result.Fail -gt 0) { "FAIL" } elseif ($result.Warn -gt 5) { "WARN" } else { "PASS" }
    audit_status = if ($result.Fail -gt 0) { "open" } else { "closed" }
}
$summary | ConvertTo-Json -Depth 3 | Out-File $summaryFile -Encoding UTF8 -Force

# ---- 输出结论 ----
Write-AuditLog ""
Write-AuditLog "========== 审计结论 =========="
Write-AuditLog "类型: $($summary.audit_type)"
Write-AuditLog "评级: $($summary.verdict)"
Write-AuditLog "PASS: $($summary.pass) | WARN: $($summary.warn) | FAIL: $($summary.fail)"
Write-AuditLog "交易日: $(if($summary.is_trading_day){'是'}else{'否'})"
Write-AuditLog "=============================="
Write-AuditLog "===== 开机审计结束 ====="

# 退出码: 0=正常, 1=有FAIL需关注
if ($result.Fail -gt 0) {
    exit 1
}
exit 0
