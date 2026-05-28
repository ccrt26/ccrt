<#
.SYNOPSIS
    模拟交易统一调度器 v1.0
.DESCRIPTION
    统一调度重点股票赛道 + 每日荐股赛道，合并持仓/快照/绩效视图。
    设计文档：模拟交易/架构设计/模拟交易_架构重设计_v2.0.md §九 Phase 2
.PARAMETER Date
    交易日期 (yyyyMMdd)，默认当天
.PARAMETER RootDir
    项目根目录
.PARAMETER DryRun
    试运行模式
.PARAMETER Force
    绕过09:45时间检查
#>

[CmdletBinding()]
param(
    [string]$Date = (Get-Date -Format "yyyyMMdd"),
    [string]$RootDir = "",
    [switch]$DryRun = $false,
    [switch]$Force = $false
)

if (-not $RootDir) {
    if ($PSScriptRoot) {
        $RootDir = (Resolve-Path "$PSScriptRoot/..").Path
    } else {
        $RootDir = "C:\Users\34269\Documents\Claude\股票分析"
    }
}

$simDir = Join-Path $RootDir "模拟交易"
$canonBase = Join-Path $RootDir "历史数据"
$orchestratorLogDir = Join-Path $simDir "日志"
if (-not $DryRun -and -not (Test-Path $orchestratorLogDir)) {
    New-Item $orchestratorLogDir -ItemType Directory -Force | Out-Null
}

$logLines = @()
function Write-Log {
    param([string]$Msg, [string]$Level = "INFO")
    $line = "[ORCH][$Level] $Msg"
    $script:logLines += $line
    Write-Output $line
}

Write-Log "===== 模拟交易统一调度器 v1.0 | Date ${Date} ====="

# ---- Step 1: 读取腰子指令 ----
$instructionFile = Join-Path $simDir "交易决策/交易指令_${Date}.json"
$hasInstructions = Test-Path $instructionFile
if ($hasInstructions) {
    Write-Log "腰子指令已就绪: $instructionFile"
} else {
    Write-Log "无腰子指令，使用纯自动模式"
}

# ---- Step 2: 设置资金池 ----
$totalCapital = 1000000  # 100万统一资金池
$keyStockRatio = 0.60    # 重点股票赛道 60%
$dailyRecRatio = 0.40    # 每日荐股赛道 40%

Write-Log "统一资金池: $totalCapital (Key Stock: $keyStockRatio | Daily Rec: $dailyRecRatio)"

# ---- Step 3: 运行重点股票赛道 ----
Write-Log ""
Write-Log "=== 赛道1: 重点股票 ==="
$keyStockEngine = Join-Path $simDir "交易引擎/sim_trading.ps1"
$keyStockArgs = @(
    "-Date", $Date,
    "-RootDir", $RootDir,
    "-InstructionFile", $instructionFile
)
if ($Force) { $keyStockArgs += "-Force" }
if ($DryRun) { $keyStockArgs += "-DryRun" }

try {
    & $keyStockEngine @keyStockArgs
    if ($LASTEXITCODE -ne 0) {
        Write-Log "重点股票引擎退出码: $LASTEXITCODE" "ERROR"
    } else {
        Write-Log "重点股票引擎完成"
    }
} catch {
    Write-Log "重点股票引擎异常: $_" "ERROR"
}

# ---- Step 4: 运行每日荐股赛道 ----
Write-Log ""
Write-Log "=== 赛道2: 每日荐股 ==="
$dailyRecEngine = Join-Path $simDir "每日荐股赛道/交易引擎/sim_trading_daily.ps1"
$dailyRecArgs = @(
    "-Date", $Date,
    "-RootDir", $RootDir,
    "-InstructionFile", $instructionFile
)
if ($Force) { $dailyRecArgs += "-Force" }
if ($DryRun) { $dailyRecArgs += "-DryRun" }

try {
    & $dailyRecEngine @dailyRecArgs
    if ($LASTEXITCODE -ne 0) {
        Write-Log "每日荐股引擎退出码: $LASTEXITCODE" "ERROR"
    } else {
        Write-Log "每日荐股引擎完成"
    }
} catch {
    Write-Log "每日荐股引擎异常: $_" "ERROR"
}

# ---- Step 5: 合并持仓快照 ----
Write-Log ""
Write-Log "=== 合并持仓视图 ==="

$keyPositionsFile = Join-Path $canonBase "00_核心交易/positions.json"
$dailyPositionsFile = Join-Path $simDir "每日荐股赛道/持仓记录/positions_daily.json"

$mergedValue = 0
$mergedCash = 0
$mergedStockValue = 0
$allPositions = @()

# 重点股票持仓
if (Test-Path $keyPositionsFile) {
    try {
        $keyPos = Get-Content $keyPositionsFile -Raw -Encoding UTF8 | ConvertFrom-Json
        $mergedCash += $keyPos.Cash
        $mergedValue += $keyPos.TotalValue
        if ($keyPos.Positions) {
            $keyPos.Positions.PSObject.Properties | ForEach-Object {
                $p = $_.Value
                $mergedStockValue += $p.CurrentPrice * $p.Shares
                $allPositions += [PSCustomObject]@{
                    Code = $p.Code
                    Name = $p.Name
                    Shares = $p.Shares
                    AvgCost = $p.AvgCost
                    CurrentPrice = $p.CurrentPrice
                    UnrealizedPnL = $p.UnrealizedPnL
                    UnrealizedPnLPct = $p.UnrealizedPnLPct
                    Track = "重点股票"
                    EntryScore = if ($p.EntryScore) { $p.EntryScore } else { $null }
                }
            }
        }
    } catch {
        Write-Log "重点股票持仓读取失败: $_" "WARN"
    }
}

# 每日荐股持仓
if (Test-Path $dailyPositionsFile) {
    try {
        $dailyPos = Get-Content $dailyPositionsFile -Raw -Encoding UTF8 | ConvertFrom-Json
        $mergedCash += $dailyPos.Cash
        $mergedValue += $dailyPos.TotalValue
        if ($dailyPos.Positions) {
            $dailyPos.Positions.PSObject.Properties | ForEach-Object {
                $p = $_.Value
                $mergedStockValue += $p.CurrentPrice * $p.Shares
                $allPositions += [PSCustomObject]@{
                    Code = $p.Code
                    Name = $p.Name
                    Shares = $p.Shares
                    AvgCost = $p.AvgCost
                    CurrentPrice = $p.CurrentPrice
                    UnrealizedPnL = $p.UnrealizedPnL
                    UnrealizedPnLPct = $p.UnrealizedPnLPct
                    Track = "每日荐股"
                    EntryScore = if ($p.EntryScore) { $p.EntryScore } else { $null }
                }
            }
        }
    } catch {
        Write-Log "每日荐股持仓读取失败: $_" "WARN"
    }
}

# ---- Step 6: 输出合并快照 ----
$mergedSnapshotFile = Join-Path $canonBase "01_交易快照/unified_snapshot_${Date}.json"
$mergedSnapshot = @{
    Date = $Date
    GeneratedAt = (Get-Date -Format "yyyy-MM-ddTHH:mm:ss")
    TotalValue = [Math]::Round($mergedValue, 2)
    Cash = [Math]::Round($mergedCash, 2)
    StockValue = [Math]::Round($mergedStockValue, 2)
    PositionCount = $allPositions.Count
    Tracks = @{
        KeyStock = @($allPositions | Where-Object { $_.Track -eq "重点股票" }).Count
        DailyRec = @($allPositions | Where-Object { $_.Track -eq "每日荐股" }).Count
    }
    Positions = @($allPositions | Sort-Object { -$_.UnrealizedPnLPct })
}

if (-not $DryRun) {
    $mergedSnapshot | ConvertTo-Json -Depth 5 | Set-Content -Encoding UTF8 $mergedSnapshotFile
    Write-Log "合并快照已写入: $mergedSnapshotFile"
}

# ---- Step 7: 控制台简报 ----
Write-Log ""
Write-Log "===== 统一调度器 日报 ${Date} ====="
Write-Log "合并净值: ¥$([Math]::Round($mergedValue, 2))"
Write-Log "现金: ¥$([Math]::Round($mergedCash, 2)) | 持仓市值: ¥$([Math]::Round($mergedStockValue, 2))"
Write-Log "持仓数: $($allPositions.Count) 只 (重点: $(($allPositions | Where-Object {$_.Track -eq '重点股票'}).Count) | 荐股: $(($allPositions | Where-Object {$_.Track -eq '每日荐股'}).Count))"
Write-Log "仓位: $([Math]::Round($mergedStockValue / $mergedValue * 100, 1))%"

if ($allPositions.Count -gt 0) {
    Write-Log ""
    foreach ($p in $allPositions) {
        $sign = if ($p.UnrealizedPnLPct -ge 0) { "+" } else { "" }
        $trackTag = if ($p.Track -eq "重点股票") { "[K]" } else { "[D]" }
        Write-Log "  ${trackTag} $($p.Name) $($p.Shares)股 成本¥$($p.AvgCost) 现价¥$($p.CurrentPrice) 浮动${sign}$($p.UnrealizedPnLPct)%"
    }
}

Write-Log "===== END ====="

if (-not $DryRun) {
    $logContent = $logLines -join "`n"
    $logContent | Out-File -Encoding utf8 (Join-Path $orchestratorLogDir "orchestrator_${Date}.log")
    Write-Log "[DONE]"
}
