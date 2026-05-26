<#
.SYNOPSIS
  铁律量化 · 启动时追赶调度器
.DESCRIPTION
  电脑开机时由 Windows Task Scheduler "At startup" 触发器调用。
  检查是否有因关机而错过的定时任务，如有则立即补执行。

  追赶原则：
    - 只补今天到期但未执行的任务（eval 19:00 / daily_latest 20:00）
    - 检查上一个 daily 是否有对应的 eval，缺口补上
    - 始终追跑 backfill（K线历史数据可补任意时长关机窗口）
    - 不做跨多日的历史 daily 重跑（推荐有时效性，过期无意义）
    - 【新增 v2】多日离线补偿：检测离线天数，按优先级回填数据缓存

  数据兜底：backfill_returns.py 使用新浪K线（100日窗口）回填 score_history.jsonl，
  关机期间的 ret_t1/t3/t5 在下次开机后自动补齐。

  多日离线数据补偿：
    - P1: KLine 缓存刷新（评分引擎核心依赖）
    - P2: FundFlow, Margin, Northbound 缓存刷新
    - P3: Research 缓存刷新
    - 状态持久化到 _last_run_state.json，支持幂等重入

.PARAMETER DryRun
  预览模式，仅显示会执行什么，不实际执行。
.PARAMETER SkipDelay
  跳过启动延迟（测试用）。
.PARAMETER SkipDataBackfill
  跳过多日离线数据补偿（仅追赶 workflow 任务 + backfill_returns）。
.EXAMPLE
  .\catchup_launcher.ps1
  .\catchup_launcher.ps1 -DryRun
  .\catchup_launcher.ps1 -SkipDataBackfill
#>

param(
    [switch]$DryRun,
    [switch]$SkipDelay,
    [switch]$SkipDataBackfill
)
. "$PSScriptRoot/../../lib/init_encoding.ps1"

$rootDir = "Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))"
$scriptsDir = Join-Path $rootDir "代码文件\每日荐股\scripts"
$recordFile = Join-Path $rootDir "每日荐股\运营记录\workflow_records.csv"
$marketCheckScript = Join-Path $scriptsDir "is_market_open.ps1"
$workflowScript = Join-Path $scriptsDir "daily_workflow.ps1"
$backfillScript = Join-Path $scriptsDir "backfill_returns.py"
$stateFile = Join-Path $scriptsDir "_last_run_state.json"
$poolFile = Join-Path $rootDir "代码文件\数据\dynamic_pool.json"
$dataModule = Join-Path $scriptsDir "stock_data_fetcher.psm1"

# ---- 启动延迟：等网络就绪 ----
if (-not $SkipDelay) {
    $delaySeconds = 60
    Write-Host "[catchup] 等待 ${delaySeconds}s 确保网络就绪..."
    Start-Sleep -Seconds $delaySeconds
}

$today = Get-Date -Format "yyyy-MM-dd"
$now = Get-Date
$hourDecimal = $now.Hour + $now.Minute / 60.0

Write-Host "=============================================" -ForegroundColor Cyan
Write-Host "[catchup] 启动时追赶检查" -ForegroundColor Cyan
Write-Host "[catchup] 当前时间: $($now.ToString('yyyy-MM-dd HH:mm:ss'))" -ForegroundColor Cyan
Write-Host "[catchup] 交易日: $today" -ForegroundColor Cyan
Write-Host "=============================================" -ForegroundColor Cyan

# ================================================================
# 通用函数
# ================================================================

function Write-CatchupLog {
    param([string]$Msg, [string]$Level = "INFO")
    $time = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $color = switch ($Level) {
        "ERROR" { "Red" }
        "WARN"  { "DarkYellow" }
        "OK"    { "Green" }
        "SKIP"  { "Gray" }
        default { "Gray" }
    }
    Write-Host "[catchup][$Level] $Msg" -ForegroundColor $color
}

# ================================================================
# 交易日历函数（与 is_market_open.ps1 使用同一套节假日清单）
# ================================================================

function Get-TradingDays {
    <#
    .SYNOPSIS
      计算两个日期之间（含首尾）的所有A股交易日。
    .PARAMETER FromDate
      起始日期，格式 yyyy-MM-dd。
    .PARAMETER ToDate
      结束日期，格式 yyyy-MM-dd。
    .OUTPUTS
      [string[]] 交易日数组，按日期升序。
    #>
    param(
        [Parameter(Mandatory=$true)][string]$FromDate,
        [Parameter(Mandatory=$true)][string]$ToDate
    )
    # 与 is_market_open.ps1 保持一致的节假日清单
    $holidays = @(
        "2026-01-01"   # 元旦
        "2026-02-16", "2026-02-17", "2026-02-18", "2026-02-19", "2026-02-20"  # 春节
        "2026-04-06"   # 清明
        "2026-05-01", "2026-05-04", "2026-05-05"  # 劳动节
        "2026-06-19"   # 端午
        "2026-10-01", "2026-10-02", "2026-10-05", "2026-10-06", "2026-10-07", "2026-10-08"  # 国庆+中秋
    )

    $start = Get-Date $FromDate -ErrorAction Stop
    $end   = Get-Date $ToDate -ErrorAction Stop
    if ($start -gt $end) { return @() }

    $tradingDays = [System.Collections.ArrayList]::new()
    $current = $start

    while ($current -le $end) {
        $dateStr = $current.ToString("yyyy-MM-dd")
        $isWeekend = ($current.DayOfWeek -eq [DayOfWeek]::Saturday -or
                      $current.DayOfWeek -eq [DayOfWeek]::Sunday)
        $isHoliday = ($dateStr -in $holidays)

        if (-not $isWeekend -and -not $isHoliday) {
            [void]$tradingDays.Add($dateStr)
        }
        $current = $current.AddDays(1)
    }
    return $tradingDays.ToArray()
}

# ================================================================
# 状态文件管理（持久化最后成功运行日期，按数据类型分轨）
# ================================================================

function Get-RunState {
    <#
    .SYNOPSIS
      读取 _last_run_state.json，不存在则返回默认初始状态。
    .OUTPUTS
      [hashtable] 状态字典。
    #>
    $default = @{
        last_run_date         = "1970-01-01"
        last_kline_date       = "1970-01-01"
        last_fundflow_date    = "1970-01-01"
        last_margin_date      = "1970-01-01"
        last_northbound_date  = "1970-01-01"
        last_research_date    = "1970-01-01"
    }

    if (-not (Test-Path $stateFile)) {
        return $default
    }
    try {
        $raw = Get-Content $stateFile -Encoding UTF8 -Raw
        if ([string]::IsNullOrWhiteSpace($raw)) { return $default }
        $state = $raw | ConvertFrom-Json
        # 确保所有键都存在
        $result = @{}
        foreach ($key in $default.Keys) {
            $val = $state.$key
            if (-not $val) { $val = $default[$key] }
            $result[$key] = $val
        }
        return $result
    } catch {
        Write-CatchupLog "状态文件读取失败，使用默认值: $_" -Level "WARN"
        return $default
    }
}

function Save-RunState {
    param([hashtable]$State)
    $dir = Split-Path $stateFile -Parent
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
    try {
        $State | ConvertTo-Json -Depth 3 | Set-Content $stateFile -Encoding UTF8
        Write-CatchupLog "状态文件已更新: $stateFile" -Level "OK"
    } catch {
        Write-CatchupLog "状态文件写入失败: $_" -Level "ERROR"
    }
}

# ================================================================
# 数据缓存刷新（导入 stock_data_fetcher 模块，为池内股票刷新指定类型缓存）
# ================================================================

function Invoke-DataRefresh {
    <#
    .SYNOPSIS
      为动态池内所有股票刷新指定数据类型的缓存。
      模块仅加载一次（脚本级缓存）。
    .PARAMETER DataType
      数据类型: KLine, FundFlow, Margin, Northbound, Research。
    .PARAMETER DryRun
      预览模式，不实际执行。
    .OUTPUTS
      [bool] 是否全部成功。
    #>
    param(
        [Parameter(Mandatory=$true)][string]$DataType,
        [bool]$IsDryRun = $false
    )

    # 加载池文件
    if (-not (Test-Path $poolFile)) {
        Write-CatchupLog "[$DataType] 动态池不存在: $poolFile，跳过缓存刷新" -Level "WARN"
        return $false
    }

    $pool = Get-Content $poolFile -Encoding UTF8 | ConvertFrom-Json
    $stocks = $pool.Stocks
    if (-not $stocks -or $stocks.Count -eq 0) {
        Write-CatchupLog "[$DataType] 动态池为空，跳过缓存刷新" -Level "WARN"
        return $false
    }
    $codes = $stocks | ForEach-Object { $_.Code }

    Write-CatchupLog "[$DataType] 开始刷新 $($codes.Count) 只股票的缓存..." -Level "INFO"

    if ($IsDryRun) {
        Write-CatchupLog "[$DataType] DRY RUN — 跳过实际刷新" -Level "SKIP"
        return $true
    }

    # 导入模块（仅一次）
    if (-not (Get-Module -Name "stock_data_fetcher")) {
        if (Test-Path $dataModule) {
            Import-Module $dataModule -Force -DisableNameChecking -ErrorAction Stop
            Write-CatchupLog "[$DataType] 已加载数据获取模块" -Level "OK"
        } else {
            Write-CatchupLog "[$DataType] 数据模块不存在: $dataModule" -Level "ERROR"
            return $false
        }
    }

    $successCount = 0
    $failCount = 0

    foreach ($code in $codes) {
        try {
            switch ($DataType) {
                "KLine" {
                    $result = Invoke-ThrottledApiCall { Get-StockKLine -Code $code -Scale "240" -Count 100 }
                    if ($result -and $result.Count -gt 0) { $successCount++ } else { $failCount++ }
                }
                "FundFlow" {
                    $result = Invoke-ThrottledApiCall { Get-StockFundFlow -Code $code -Days 5 }
                    if ($result -and $result.Count -gt 0) { $successCount++ } else { $failCount++ }
                }
                "Margin" {
                    $result = Invoke-ThrottledApiCall { Get-MarginData -Code $code -Days 5 }
                    if ($result -and $result.Count -gt 0) { $successCount++ } else { $failCount++ }
                }
                "Northbound" {
                    $result = Invoke-ThrottledApiCall { Get-NorthboundHold -Code $code }
                    if ($result) { $successCount++ } else { $failCount++ }
                }
                "Research" {
                    $result = Invoke-ThrottledApiCall { Get-StockResearch -Code $code -Count 5 -DaysBack "30" }
                    if ($result -and $result.Count -gt 0) { $successCount++ } else { $failCount++ }
                }
            }
        } catch {
            $failCount++
            Write-CatchupLog "[$DataType] $code 刷新异常: $_" -Level "WARN"
        }
    }

    $total = $codes.Count
    Write-CatchupLog "[$DataType] 刷新完成: $successCount/$total 成功" -Level $(if ($failCount -eq 0) { "OK" } else { "WARN" })
    return ($failCount -eq 0)
}

# ================================================================
# Step 1: 今天是不是交易日
# ================================================================

$null = & $marketCheckScript -Date $today
if ($LASTEXITCODE -ne 0) {
    Write-CatchupLog "$today 非交易日，退出" -Level "SKIP"
    exit 0
}

# ================================================================
# Step 2: 加载执行记录
# ================================================================

$records = @()
if (Test-Path $recordFile) {
    $records = Import-Csv $recordFile -Encoding UTF8
}

function Test-AlreadyDone {
    param([string]$Date, [string]$Mode)
    $match = $records | Where-Object {
        $_.Date -eq $Date -and $_.Mode -eq $Mode -and $_.Status -eq "SUCCESS"
    }
    return ($null -ne $match -and $match.Count -gt 0)
}

# ================================================================
# Step 3: 判断今天哪些任务过期未执行
# ================================================================

$actions = [System.Collections.ArrayList]::new()

# 3a. 每日荐股分析 (daily/daily_latest) — 应于今日 20:00 执行
if ($hourDecimal -ge 20.0) {
    $dailyDone = (Test-AlreadyDone $today "daily") -or (Test-AlreadyDone $today "daily_latest")
    if (-not $dailyDone) {
        [void]$actions.Add(@{Mode="daily_latest"; Date=$today; Priority=2; Reason="今日20:00每日荐股分析未执行"})
        Write-CatchupLog "MISS: 今日 daily_latest (应20:00执行)" -Level "WARN"
    } else {
        Write-CatchupLog "OK : 今日 daily/daily_latest 已执行" -Level "OK"
    }
} else {
    Write-CatchupLog "待定: 今日 daily_latest (当前${hourDecimal}h < 20:00，留给定时任务)"
}

# 3b. 次日后评估 (eval) — 应于今日 19:00 执行
if ($hourDecimal -ge 19.0) {
    if (-not (Test-AlreadyDone $today "eval")) {
        [void]$actions.Add(@{Mode="eval"; Date=$today; Priority=1; Reason="今日19:00次日后评估未执行"})
        Write-CatchupLog "MISS: 今日 eval (应19:00执行)" -Level "WARN"
    } else {
        Write-CatchupLog "OK : 今日 eval 已执行" -Level "OK"
    }
} else {
    Write-CatchupLog "待定: 今日 eval (当前${hourDecimal}h < 19:00，留给定时任务)"
}

# ================================================================
# Step 4: 检查上一个 daily 是否缺 eval
# ================================================================

# 辅助函数：找下一个交易日（跳过周末+节假日，最多往后找5天）
function Get-NextTradingDay {
    param([string]$FromDate)
    $d = Get-Date $FromDate
    for ($i = 1; $i -le 5; $i++) {
        $candidate = $d.AddDays($i).ToString("yyyy-MM-dd")
        $null = & $marketCheckScript -Date $candidate
        if ($LASTEXITCODE -eq 0) { return $candidate }
    }
    return $null
}

$lastDaily = $records | Where-Object { $_.Mode -in @("daily", "daily_latest") -and $_.Status -eq "SUCCESS" } |
    Sort-Object Date -Descending | Select-Object -First 1

if ($lastDaily) {
    $lastDailyDate = $lastDaily.Date
    $evalDate = Get-NextTradingDay $lastDailyDate

    if ($evalDate -and $evalDate -le $today) {
        # 如果 evalDate 就是今天但还没到19:00，留给定时任务
        if ($evalDate -eq $today -and $hourDecimal -lt 19.0) {
            Write-CatchupLog "待定: ${evalDate} eval (当前${hourDecimal}h < 19:00，留给定时任务)"
        } elseif (-not (Test-AlreadyDone $evalDate "eval")) {
            # 避免重复添加（已在 Step 3b 中加入）
            $alreadyInActions = $actions | Where-Object { $_.Mode -eq "eval" -and $_.Date -eq $evalDate }
            if (-not $alreadyInActions) {
                [void]$actions.Add(@{Mode="eval"; Date=$evalDate; Priority=1; Reason="补跑 ${lastDailyDate} 荐股的次日评估(应${evalDate}19:00执行)"})
                Write-CatchupLog "MISS: ${evalDate} eval 未执行 (评估 ${lastDailyDate} 荐股)" -Level "WARN"
            }
        } else {
            Write-CatchupLog "OK : ${evalDate} eval 已执行" -Level "OK"
        }
    } elseif (-not $evalDate) {
        Write-CatchupLog "WARN: 无法确定 ${lastDailyDate} 的下一个交易日" -Level "WARN"
    } else {
        Write-CatchupLog "待定: ${evalDate} eval (尚未到日期)"
    }
} else {
    Write-CatchupLog "INFO: 无历史 daily 记录，跳过 eval 追赶检查"
}

# ================================================================
# Step 5: 按优先级排序执行
# ================================================================
# Priority 1 = eval（先评估，可能产出白皮书优化）
# Priority 2 = daily_latest（后分析，使用最新白皮书）

$actions = $actions | Sort-Object Date, Priority

if ($actions.Count -eq 0) {
    Write-CatchupLog "无需追赶，所有任务已就绪" -Level "OK"
} else {
    Write-Host "`n[catchup] ===== 需要执行 $($actions.Count) 个追赶任务 =====" -ForegroundColor Cyan
    foreach ($a in $actions) {
        Write-Host ("  [{0}] {1} {2} — {3}" -f $a.Priority, $a.Mode, $a.Date, $a.Reason) -ForegroundColor Yellow
    }

    if ($DryRun) {
        Write-Host "[catchup] DRY RUN — 不实际执行" -ForegroundColor Magenta
    } else {
        foreach ($a in $actions) {
            Write-Host ("`n[catchup] >>> 执行: daily_workflow.ps1 -Mode {0} -Date {1} -SkipMarketCheck" -f $a.Mode, $a.Date) -ForegroundColor Cyan
            $sw = [System.Diagnostics.Stopwatch]::StartNew()
            try {
                & $workflowScript -Mode $a.Mode -Date $a.Date -SkipMarketCheck
                if ($LASTEXITCODE -ne 0) {
                    Write-CatchupLog "失败: $($a.Mode) $($a.Date) (exit=$LASTEXITCODE)" -Level "ERROR"
                } else {
                    Write-CatchupLog "完成: $($a.Mode) $($a.Date) (耗时 $([math]::Round($sw.Elapsed.TotalSeconds, 0))s)" -Level "OK"
                }
            } catch {
                Write-CatchupLog "异常: $($a.Mode) $($a.Date) — $_" -Level "ERROR"
            } finally {
                $sw.Stop()
            }
        }
    }
}

# ================================================================
# Step 5b: 多日离线数据补偿（v2 新增）
# ================================================================

if (-not $SkipDataBackfill) {
    Write-Host "`n[catchup] ===== 多日离线数据补偿 =====" -ForegroundColor Cyan

    # 读取状态文件
    $runState = Get-RunState
    $lastRunDate = $runState["last_run_date"]

    Write-CatchupLog "上次运行日期: $lastRunDate" -Level "INFO"
    Write-CatchupLog "当前日期: $today" -Level "INFO"

    # 计算错过的交易日（不含今天，今天由 Step 3-5 的 workflow 覆盖）
    $yesterday = (Get-Date $today).AddDays(-1).ToString("yyyy-MM-dd")
    if ($lastRunDate -eq "1970-01-01" -or $lastRunDate -ge $today) {
        # 从未运行过 或 今天已经跑过，无需补偿
        $missedDays = @()
        Write-CatchupLog "首次运行或状态已是最新，无错过交易日" -Level "OK"
    } else {
        # 查找 lastRunDate 之后（不含）到今天之前（不含）的交易日
        $dayAfter = (Get-Date $lastRunDate).AddDays(1).ToString("yyyy-MM-dd")
        $missedDays = Get-TradingDays -FromDate $dayAfter -ToDate $yesterday
    }

    if ($missedDays.Count -eq 0) {
        Write-CatchupLog "无错过的交易日，数据缓存已是最新" -Level "OK"
    } else {
        Write-CatchupLog "检测到 $($missedDays.Count) 个错过的交易日: $($missedDays -join ', ')" -Level "WARN"

        # 检查各数据类型是否已经回填到最新
        $backfillQueue = [System.Collections.ArrayList]::new()

        $dataTypeConfig = @(
            @{ Name="KLine";      Priority=1; StateKey="last_kline_date";      Label="K线数据" }
            @{ Name="FundFlow";   Priority=2; StateKey="last_fundflow_date";   Label="资金流向" }
            @{ Name="Margin";     Priority=2; StateKey="last_margin_date";     Label="融资融券" }
            @{ Name="Northbound"; Priority=2; StateKey="last_northbound_date"; Label="北向资金" }
            @{ Name="Research";   Priority=3; StateKey="last_research_date";   Label="研报数据" }
        )

        foreach ($dt in $dataTypeConfig) {
            $lastDtDate = $runState[$dt.StateKey]
            # 如果该数据类型的最后刷新日期 < 最近一个错过的交易日, 则需要回填
            if ($lastDtDate -lt $missedDays[-1]) {
                $daysBehind = ($missedDays | Where-Object { $_ -gt $lastDtDate }).Count
                [void]$backfillQueue.Add(@{
                    DataType   = $dt.Name
                    Priority   = $dt.Priority
                    Label      = $dt.Label
                    StateKey   = $dt.StateKey
                    LastDate   = $lastDtDate
                    DaysBehind = $daysBehind
                    Reason     = "${lastDtDate} 之后有 $daysBehind 个交易日的数据未刷新"
                })
            } else {
                Write-CatchupLog "[$($dt.Label)] 已是最新 (上次: $lastDtDate)" -Level "OK"
            }
        }

        if ($backfillQueue.Count -eq 0) {
            Write-CatchupLog "所有数据类型已为最新，无需补偿" -Level "OK"
        } else {
            # 按优先级排序
            $backfillQueue = $backfillQueue | Sort-Object Priority

            Write-Host "`n[catchup] ----- 补偿队列 ($($backfillQueue.Count) 项) -----" -ForegroundColor Cyan
            foreach ($bt in $backfillQueue) {
                Write-Host ("  [P{0}] {1} — {2}" -f $bt.Priority, $bt.Label, $bt.Reason) -ForegroundColor Yellow
            }

            if ($DryRun) {
                Write-CatchupLog "DRY RUN — 跳过数据补偿" -Level "SKIP"
            } else {
                # 按优先级顺序执行
                $currentPriority = 0
                foreach ($bt in $backfillQueue) {
                    if ($bt.Priority -ne $currentPriority) {
                        $currentPriority = $bt.Priority
                        $pLabel = switch ($currentPriority) {
                            1 { "P1-KLine" }
                            2 { "P2-资金/融资/北向" }
                            3 { "P3-研报" }
                        }
                        Write-Host ("`n[catchup] >>> {0} 批次开始 >>>" -f $pLabel) -ForegroundColor Cyan
                    }

                    $sw = [System.Diagnostics.Stopwatch]::StartNew()
                    try {
                        $ok = Invoke-DataRefresh -DataType $bt.DataType -IsDryRun $false
                        if ($ok) {
                            $runState[$bt.StateKey] = $today
                            $runState["last_run_date"] = $today
                            Write-CatchupLog "补偿完成: $($bt.Label) (耗时 $([math]::Round($sw.Elapsed.TotalSeconds, 0))s)" -Level "OK"
                        } else {
                            Write-CatchupLog "补偿部分失败: $($bt.Label) — 部分股票数据刷新失败" -Level "WARN"
                            # 仍然更新状态（已尝试）
                            $runState[$bt.StateKey] = $today
                            $runState["last_run_date"] = $today
                        }
                    } catch {
                        Write-CatchupLog "补偿异常: $($bt.Label) — $_" -Level "ERROR"
                    } finally {
                        $sw.Stop()
                    }
                    # 每批次完成后立即持久化状态，防止中途崩溃丢失进度
                    Save-RunState -State $runState
                }
            }
        }
    }

    # 即使没有错过交易日，也更新 last_run_date
    if (-not $DryRun) {
        $runState["last_run_date"] = $today
        Save-RunState -State $runState
    }
} else {
    Write-CatchupLog "SkipDataBackfill 已设置，跳过多日离线数据补偿" -Level "SKIP"
}

# ================================================================
# Step 6: 始终跑 backfill（K线收益回填，数据兜底）
# ================================================================

Write-Host "`n[catchup] ----- 数据回填 (K线历史) -----" -ForegroundColor Cyan
if ($DryRun) {
    Write-Host "[catchup] DRY RUN — 跳过 backfill" -ForegroundColor Magenta
} else {
    try {
        $backfillResult = & python $backfillScript --catch-up 2>&1
        Write-Host "[catchup] backfill: $($backfillResult -join '; ')" -ForegroundColor Gray
    } catch {
        Write-CatchupLog "backfill 异常: $_" -Level "ERROR"
    }
}

# ================================================================
# 完成
# ================================================================

Write-Host "`n[catchup] ===== 追赶检查完成 =====" -ForegroundColor Cyan
exit 0
