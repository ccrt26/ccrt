<#
.SYNOPSIS
  铁律量化 · 月度学习调度包装脚本
.DESCRIPTION
  每月30号（或月末最后一天）21:00 由 TieLv-MonthlyLearn 定时任务触发。
  按顺序执行：
    a. monthly_summary.ps1       -- 收集月度数据生成 JSON
    b. run_meta_evaluation.ps1   -- 评估系统自检（中循环）
    c. gen_monthly_report.ps1    -- 生成带外部研究对比的月度学习报告 PDF
    d. 记录执行日志
.PARAMETER Month
  目标月份，格式 yyyy-MM。默认上个月。
.PARAMETER SourceDir
  项目根目录。
#>

param(
    [string]$Month = (Get-Date).AddMonths(-1).ToString("yyyy-MM"),
    [string]$SourceDir = "Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))"
)
. "$PSScriptRoot/../../lib/init_encoding.ps1"

# ============================================================
# 路径配置
# ============================================================
$scriptsDir = Join-Path $SourceDir "代码文件\每日荐股\scripts"
$logDir     = Join-Path $scriptsDir "logs"
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir -Force | Out-Null }

$logFile = Join-Path $logDir "monthly_learn_$(Get-Date -Format 'yyyyMM').log"

$monthlySummary   = Join-Path $scriptsDir "monthly_summary.ps1"
$metaEvaluation   = Join-Path $SourceDir "代码文件\重点股票\次日评估\run_meta_evaluation.ps1"
$monthlyReport    = Join-Path $scriptsDir "gen_monthly_report.ps1"

$startTime = Get-Date

# ============================================================
# 日志函数
# ============================================================
function Write-Log {
    param(
        [string]$Msg,
        [string]$Level = "INFO"
    )
    $time = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $line = "[$time][LEARN][$Level] $Msg"
    Add-Content -Path $logFile -Value $line -Encoding UTF8
    Write-Host $line
}

function Write-Step {
    param([string]$Msg)
    Write-Log -Msg "" -Level "SEP"
    Write-Log -Msg ">>> $Msg <<<" -Level "STEP"
}

# ============================================================
# 开始
# ============================================================
Write-Log -Msg "================================================================"
Write-Log -Msg "  铁律量化 · 月度学习任务启动"
Write-Log -Msg "  月份: $Month"
Write-Log -Msg "  启动时间: $($startTime.ToString('yyyy-MM-dd HH:mm:ss'))"
Write-Log -Msg "================================================================"

# 验证 PowerShell 版本
$psVer = $PSVersionTable.PSVersion.ToString()
Write-Log -Msg "PowerShell 版本: $psVer"

# 验证所有依赖脚本存在
$requiredScripts = @(
    @{ Path = $monthlySummary; Name = "monthly_summary.ps1" },
    @{ Path = $metaEvaluation; Name = "run_meta_evaluation.ps1" },
    @{ Path = $monthlyReport;  Name = "gen_monthly_report.ps1" }
)

$allExist = $true
foreach ($rs in $requiredScripts) {
    if (Test-Path $rs.Path) {
        Write-Log -Msg "  [OK] $($rs.Name) 就绪"
    } else {
        Write-Log -Msg "  [MISSING] $($rs.Name) 未找到: $($rs.Path)" -Level "ERROR"
        $allExist = $false
    }
}

if (-not $allExist) {
    Write-Log -Msg "严重错误: 依赖脚本缺失，终止执行" -Level "ERROR"
    exit 1
}

# ============================================================
# 变量追踪
# ============================================================
$results = @()
$hasError = $false

# ============================================================
# Step a: monthly_summary.ps1 -- 收集月度数据
# ============================================================
Write-Step "Step a: 收集月度数据 -- monthly_summary.ps1"
try {
    $stepStart = Get-Date
    Write-Log -Msg "执行: $monthlySummary -Month '$Month' -SourceDir '$SourceDir'"

    $output = & $monthlySummary -Month $Month -SourceDir $SourceDir 2>&1
    $exitCode = $LASTEXITCODE

    $duration = [Math]::Round(((Get-Date) - $stepStart).TotalSeconds, 1)

    foreach ($line in $output) {
        Write-Log -Msg "  [OUT] $line"
    }

    if ($exitCode -ne 0 -and $exitCode -ne $null) {
        Write-Log -Msg "monthly_summary.ps1 退出码: $exitCode" -Level "WARN"
    }

    $results += [PSCustomObject]@{
        Step = "a"
        Name = "月度数据收集"
        Duration = $duration
        Status = "完成"
    }
    Write-Log -Msg "Step a 完成，耗时 ${duration}s"
} catch {
    $duration = [Math]::Round(((Get-Date) - $stepStart).TotalSeconds, 1)
    Write-Log -Msg "Step a 异常: $_" -Level "ERROR"
    $results += [PSCustomObject]@{ Step = "a"; Name = "月度数据收集"; Duration = $duration; Status = "失败: $_" }
    $hasError = $true
}

# ============================================================
# Step b: run_meta_evaluation.ps1 -- 评估系统自检
# ============================================================
Write-Step "Step b: 系统自检 -- run_meta_evaluation.ps1"
try {
    $stepStart = Get-Date
    Write-Log -Msg "执行: $metaEvaluation -GenerateReport:`$true"

    $output = & $metaEvaluation -GenerateReport:$true 2>&1
    $exitCode = $LASTEXITCODE

    $duration = [Math]::Round(((Get-Date) - $stepStart).TotalSeconds, 1)

    foreach ($line in $output) {
        Write-Log -Msg "  [OUT] $line"
    }

    if ($exitCode -eq 1) {
        # exit 1 = 元评估数据不足，非严重错误（可继续）
        Write-Log -Msg "run_meta_evaluation.ps1 报告数据不足，跳过自检（非错误）" -Level "WARN"
    } elseif ($exitCode -ne 0 -and $exitCode -ne $null) {
        Write-Log -Msg "run_meta_evaluation.ps1 退出码: $exitCode" -Level "WARN"
    }

    $results += [PSCustomObject]@{
        Step = "b"
        Name = "系统自检"
        Duration = $duration
        Status = "完成"
    }
    Write-Log -Msg "Step b 完成，耗时 ${duration}s"
} catch {
    $duration = [Math]::Round(((Get-Date) - $stepStart).TotalSeconds, 1)
    Write-Log -Msg "Step b 异常: $_" -Level "ERROR"
    $results += [PSCustomObject]@{ Step = "b"; Name = "系统自检"; Duration = $duration; Status = "失败: $_" }
    $hasError = $true
}

# ============================================================
# Step c: gen_monthly_report.ps1 -- 生成月度学习报告
# ============================================================
Write-Step "Step c: 生成月度学习报告 -- gen_monthly_report.ps1"
try {
    $stepStart = Get-Date
    Write-Log -Msg "执行: $monthlyReport -Month '$Month' -SourceDir '$SourceDir'"

    $output = & $monthlyReport -Month $Month -SourceDir $SourceDir 2>&1
    $exitCode = $LASTEXITCODE

    $duration = [Math]::Round(((Get-Date) - $stepStart).TotalSeconds, 1)

    foreach ($line in $output) {
        Write-Log -Msg "  [OUT] $line"
    }

    if ($exitCode -ne 0 -and $exitCode -ne $null) {
        Write-Log -Msg "gen_monthly_report.ps1 退出码: $exitCode" -Level "WARN"
    }

    $results += [PSCustomObject]@{
        Step = "c"
        Name = "月度学习报告"
        Duration = $duration
        Status = "完成"
    }
    Write-Log -Msg "Step c 完成，耗时 ${duration}s"
} catch {
    $duration = [Math]::Round(((Get-Date) - $stepStart).TotalSeconds, 1)
    Write-Log -Msg "Step c 异常: $_" -Level "ERROR"
    $results += [PSCustomObject]@{ Step = "c"; Name = "月度学习报告"; Duration = $duration; Status = "失败: $_" }
    $hasError = $true
}

# ============================================================
# Step d: 执行摘要
# ============================================================
$endTime = Get-Date
$totalDuration = [Math]::Round(($endTime - $startTime).TotalSeconds, 1)

Write-Step "执行完成摘要"

Write-Log -Msg "  月份: $Month"
Write-Log -Msg "  开始: $($startTime.ToString('yyyy-MM-dd HH:mm:ss'))"
Write-Log -Msg "  结束: $($endTime.ToString('yyyy-MM-dd HH:mm:ss'))"
Write-Log -Msg "  总耗时: ${totalDuration}s"

foreach ($r in $results) {
    Write-Log -Msg "  Step $($r.Step) [$($r.Name)]: $($r.Status) ($($r.Duration)s)"
}

if ($hasError) {
    Write-Log -Msg "整体状态: 部分步骤异常，请检查上述日志" -Level "WARN"
} else {
    Write-Log -Msg "整体状态: 全部成功完成" -Level "INFO"
}

Write-Log -Msg "================================================================"
Write-Log -Msg "  月度学习任务结束"
Write-Log -Msg "================================================================"

# 输出关键信息到控制台
Write-Host ""
Write-Host "============================================"
Write-Host "  铁律量化 · 月度学习完成"
Write-Host "  月份: $Month"
Write-Host "  日志: $logFile"
Write-Host "  状态: $(if ($hasError) { '部分异常' } else { '全部成功' })"
Write-Host "  耗时: ${totalDuration}s"
Write-Host "============================================"

if ($hasError) { exit 1 } else { exit 0 }
