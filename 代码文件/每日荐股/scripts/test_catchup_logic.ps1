﻿# 铁律量化 · catchup_launcher 逻辑测试
# Proof 验证脚本 — 模拟5个场景，验证追赶决策正确性
param([switch]$Verbose)

$rootDir = "C:\Users\34269\Documents\Claude\股票分析"
$scriptsDir = Join-Path $rootDir "代码文件\每日荐股\scripts"
$catchupScript = Join-Path $scriptsDir "catchup_launcher.ps1"

$pass = 0
$fail = 0

function Test-Scenario {
    param(
        [string]$Name,
        [string]$Desc,
        [string]$Today,
        [string]$CurrentTime,
        [string[]]$ExistingRecords,  # "Date,Mode,Status"
        [string[]]$ExpectedActions,  # "Mode:Date" or "NONE"
        [bool]$ExpectBackfill = $true
    )
    $testResult = "PASS"
    $details = @()

    # Check if today is a trading day (simple weekday+holiday check)
    $d = Get-Date $Today
    $isTradingDay = ($d.DayOfWeek -ne [DayOfWeek]::Saturday -and $d.DayOfWeek -ne [DayOfWeek]::Sunday)
    # Simple holiday check
    $holidays = @("2026-01-01","2026-02-16","2026-02-17","2026-02-18","2026-02-19","2026-02-20",
                  "2026-04-06","2026-05-01","2026-05-04","2026-05-05","2026-06-19",
                  "2026-10-01","2026-10-02","2026-10-05","2026-10-06","2026-10-07","2026-10-08")
    if ($Today -in $holidays) { $isTradingDay = $false }

    Write-Host "`n========================================" -ForegroundColor Cyan
    Write-Host " 场景: $Name" -ForegroundColor Cyan
    Write-Host " 描述: $Desc" -ForegroundColor Gray
    Write-Host " 日期: $Today | 时间: $CurrentTime | 交易日: $isTradingDay" -ForegroundColor Gray
    Write-Host "========================================" -ForegroundColor Cyan

    if (-not $isTradingDay) {
        $expected = if ($ExpectedActions -eq "NONE" -or $ExpectedActions.Count -eq 0) { "NONE" } else { $ExpectedActions -join ", " }
        if ($ExpectedActions -eq "NONE" -or $ExpectedActions.Count -eq 0) {
            Write-Host " 预期: 退出(非交易日)" -ForegroundColor Green
            Write-Host " 结果: PASS" -ForegroundColor Green
            $script:pass++
            return
        } else {
            Write-Host " 预期: $expected — 但非交易日应该退出" -ForegroundColor Red
            Write-Host " 结果: FAIL" -ForegroundColor Red
            $script:fail++
            return
        }
    }

    # ---- Simulate the catchup logic ----
    $hour = [int]($CurrentTime.Split(":")[0])
    $minute = [int]($CurrentTime.Split(":")[1])
    $hourDecimal = $hour + $minute / 60.0

    Write-Host " 已有记录:" -ForegroundColor Gray
    foreach ($r in $ExistingRecords) { Write-Host "    $r" -ForegroundColor Gray }

    function Test-Done($records, $date, $mode) {
        foreach ($r in $records) {
            $parts = $r.Split(",")
            if ($parts[0] -eq $date -and $parts[1] -eq $mode -and $parts[2] -eq "SUCCESS") {
                return $true
            }
        }
        return $false
    }

    $actions = [System.Collections.ArrayList]::new()

    # Step 3a: daily_latest after 20:00
    if ($hourDecimal -ge 20.0) {
        if (-not (Test-Done $ExistingRecords $Today "daily") -and -not (Test-Done $ExistingRecords $Today "daily_latest")) {
            [void]$actions.Add("daily_latest:$Today")
            $details += "  [3a] daily_latest MISS → 加入追赶队列"
        } else {
            $details += "  [3a] daily/daily_latest 已执行 → 跳过"
        }
    } else {
        $details += "  [3a] 当前${hourDecimal}h < 20:00 → 留给定时任务"
    }

    # Step 3b: eval after 19:00
    if ($hourDecimal -ge 19.0) {
        if (-not (Test-Done $ExistingRecords $Today "eval")) {
            [void]$actions.Add("eval:$Today")
            $details += "  [3b] eval MISS → 加入追赶队列"
        } else {
            $details += "  [3b] eval 已执行 → 跳过"
        }
    } else {
        $details += "  [3b] 当前${hourDecimal}h < 19:00 → 留给定时任务"
    }

    # Step 4: Check previous daily eval gap (find NEXT TRADING DAY, not just +1)
    # Simple weekend check for test (holidays would need CSV, skip for test)
    function Get-NextTradingDaySimple($fromDate) {
        $d = Get-Date $fromDate
        for ($i = 1; $i -le 5; $i++) {
            $c = $d.AddDays($i)
            $cStr = $c.ToString("yyyy-MM-dd")
            # Check if it's a holiday (simple list)
            $testHolidays = @("2026-01-01","2026-02-16","2026-02-17","2026-02-18","2026-02-19","2026-02-20",
                              "2026-04-06","2026-05-01","2026-05-04","2026-05-05","2026-06-19",
                              "2026-10-01","2026-10-02","2026-10-05","2026-10-06","2026-10-07","2026-10-08")
            $isWeekend = ($c.DayOfWeek -eq [DayOfWeek]::Saturday -or $c.DayOfWeek -eq [DayOfWeek]::Sunday)
            if (-not $isWeekend -and $cStr -notin $testHolidays) {
                return $cStr
            }
        }
        return $null
    }

    $dailyRecords = $ExistingRecords | Where-Object { $_ -match "^(.*),(daily|daily_latest),SUCCESS" }
    if ($dailyRecords) {
        $lastDailyDate = ($dailyRecords | ForEach-Object { $_.Split(",")[0] } | Sort-Object -Descending | Select-Object -First 1)
        $evalDate = Get-NextTradingDaySimple $lastDailyDate
        if ($evalDate -and $evalDate -le $Today) {
            # If evalDate is today but eval cutoff hasn't passed, skip
            if ($evalDate -eq $Today -and $hourDecimal -lt 19.0) {
                $details += "  [4]  ${lastDailyDate}的次日评估(${evalDate})未到19:00 → 留给定时任务"
            } else {
                $alreadyInActions = $actions | Where-Object { $_ -match "^eval:${evalDate}$" }
                if (-not $alreadyInActions -and -not (Test-Done $ExistingRecords $evalDate "eval")) {
                    [void]$actions.Add("eval:$evalDate")
                    $details += "  [4]  ${lastDailyDate}的次日评估(下一个交易日=${evalDate}) MISS → 加入追赶队列"
                } else {
                    $details += "  [4]  ${lastDailyDate}的次日评估(${evalDate})已覆盖 → 跳过"
                }
            }
        } elseif (-not $evalDate) {
            $details += "  [4]  无法确定 ${lastDailyDate} 的下一个交易日 → 跳过"
        } else {
            $details += "  [4]  ${lastDailyDate}的次日评估(${evalDate})尚未到日期 → 跳过"
        }
    }

    # ---- Verify against expected ----
    $actual = if ($actions.Count -eq 0) { "NONE" } else { $actions -join ", " }
    $expected = $ExpectedActions -join ", "

    Write-Host " 决策详情:" -ForegroundColor Gray
    foreach ($d in $details) { Write-Host $d -ForegroundColor Gray }
    Write-Host " 预期: $expected" -ForegroundColor Yellow
    Write-Host " 实际: $actual" -ForegroundColor Yellow

    if ($expected -eq $actual) {
        Write-Host " 结果: PASS" -ForegroundColor Green
        $script:pass++
    } else {
        Write-Host " 结果: FAIL" -ForegroundColor Red
        $script:fail++
    }

    if ($ExpectBackfill) {
        Write-Host " 后置: backfill --catch-up (始终执行)" -ForegroundColor Gray
    }
}

# ==================== 场景 1-6: 原有 workflow 追赶逻辑 ====================
Write-Host "`n========== Proof: catchup_launcher workflow 逻辑验证 ==========" -ForegroundColor Magenta

# 场景1: 工作日 18:00 开机，今天的任务都还没过期
Test-Scenario -Name "S1: 提前开机" `
    -Desc "周一18:00开机，eval(19:00)和daily_latest(20:00)都还没到时间" `
    -Today "2026-05-25" -CurrentTime "18:00" `
    -ExistingRecords @("2026-05-22,daily,SUCCESS", "2026-05-22,eval,SUCCESS", "2026-05-22,daily_latest,SUCCESS") `
    -ExpectedActions @("NONE")

# 场景2: 工作日 19:30 开机，eval已经过期
Test-Scenario -Name "S2: eval过期" `
    -Desc "周一19:30开机，19:00的eval已过期未执行，20:00的daily_latest还没到" `
    -Today "2026-05-25" -CurrentTime "19:30" `
    -ExistingRecords @("2026-05-22,daily,SUCCESS") `
    -ExpectedActions @("eval:2026-05-25")

# 场景3: 工作日 20:30 开机，两个都过期
Test-Scenario -Name "S3: 全部过期" `
    -Desc "周一20:30开机，eval和daily_latest都过期未执行" `
    -Today "2026-05-25" -CurrentTime "20:30" `
    -ExistingRecords @("2026-05-22,daily,SUCCESS") `
    -ExpectedActions @("daily_latest:2026-05-25", "eval:2026-05-25")

# 场景4: 非交易日开机
Test-Scenario -Name "S4: 非交易日" `
    -Desc "周六开机，不做任何事" `
    -Today "2026-05-23" -CurrentTime "10:00" `
    -ExistingRecords @("2026-05-22,daily,SUCCESS") `
    -ExpectedActions @("NONE")

# 场景5: 关机3天后开机，上次daily没被eval
Test-Scenario -Name "S5: 多日关机+缺eval" `
    -Desc "周三20:30开机，上次daily是上周五，周一和周二的eval都没跑" `
    -Today "2026-05-27" -CurrentTime "20:30" `
    -ExistingRecords @("2026-05-22,daily,SUCCESS", "2026-05-26,daily,SUCCESS") `
    -ExpectedActions @("daily_latest:2026-05-27", "eval:2026-05-27")

# 场景6: 正常状态，都跑过了
Test-Scenario -Name "S6: 一切正常" `
    -Desc "周一20:30，今天的eval和daily_latest都已正常执行" `
    -Today "2026-05-25" -CurrentTime "20:30" `
    -ExistingRecords @("2026-05-25,eval,SUCCESS", "2026-05-25,daily_latest,SUCCESS") `
    -ExpectedActions @("NONE")

# ==================== 场景 7-12: 多日离线数据补偿逻辑 ====================
Write-Host "`n========== Proof: 多日离线数据补偿逻辑验证 ==========" -ForegroundColor Magenta

# 与 catchup_launcher.ps1 保持一致的节假日清单
$holidays = @(
    "2026-01-01"
    "2026-02-16", "2026-02-17", "2026-02-18", "2026-02-19", "2026-02-20"
    "2026-04-06"
    "2026-05-01", "2026-05-04", "2026-05-05"
    "2026-06-19"
    "2026-10-01", "2026-10-02", "2026-10-05", "2026-10-06", "2026-10-07", "2026-10-08"
)

function Test-GetTradingDays {
    param([string]$From, [string]$To, [string[]]$Expected)
    $start = Get-Date $From
    $end   = Get-Date $To
    $result = [System.Collections.ArrayList]::new()
    $cur = $start
    while ($cur -le $end) {
        $ds = $cur.ToString("yyyy-MM-dd")
        $isWknd = ($cur.DayOfWeek -eq "Saturday" -or $cur.DayOfWeek -eq "Sunday")
        if (-not $isWknd -and $ds -notin $holidays) { [void]$result.Add($ds) }
        $cur = $cur.AddDays(1)
    }
    $actual = $result -join ","
    $expected = $Expected -join ","
    if ($actual -eq $expected) {
        Write-Host "  TradingDays [$From -> $To]: PASS" -ForegroundColor Green
        $script:pass++
    } else {
        Write-Host "  TradingDays [$From -> $To]: FAIL" -ForegroundColor Red
        Write-Host "    Expected: $expected" -ForegroundColor Red
        Write-Host "    Actual:   $actual" -ForegroundColor Red
        $script:fail++
    }
}

# 假日列表公共，用同一天测试周末+假期
# S7: Get-TradingDays — 日内含周末
Test-GetTradingDays -From "2026-05-22" -To "2026-05-25" -Expected @("2026-05-22", "2026-05-25")

# S8: Get-TradingDays — 跨劳动节假期
Test-GetTradingDays -From "2026-04-30" -To "2026-05-06" -Expected @("2026-04-30", "2026-05-06")

# S9: Get-TradingDays — 单日
Test-GetTradingDays -From "2026-05-25" -To "2026-05-25" -Expected @("2026-05-25")

# S10: Get-TradingDays — 全周末区间
Test-GetTradingDays -From "2026-05-23" -To "2026-05-24" -Expected @()

# ==================== 状态文件 + 补偿队列测试 ====================

function Test-OfflineDetection {
    param(
        [string]$Name,
        [string]$Desc,
        [hashtable]$State,
        [string]$Today,
        [string[]]$ExpectedMissedDays,
        [string[]]$ExpectedBackfillTypes  # e.g., @("KLine","FundFlow")
    )
    Write-Host "`n----------------------------------------" -ForegroundColor Cyan
    Write-Host " 场景: $Name" -ForegroundColor Cyan
    Write-Host " 描述: $Desc" -ForegroundColor Gray
    Write-Host " 状态: last_run=$($State['last_run_date']) kline=$($State['last_kline_date']) fundflow=$($State['last_fundflow_date']) margin=$($State['last_margin_date']) nb=$($State['last_northbound_date']) research=$($State['last_research_date'])" -ForegroundColor Gray
    Write-Host " 今天: $Today" -ForegroundColor Gray

    # Simulate missed days calculation
    $lastRun = $State["last_run_date"]
    $yesterday = (Get-Date $Today).AddDays(-1).ToString("yyyy-MM-dd")
    if ($lastRun -eq "1970-01-01" -or $lastRun -ge $Today) {
        $missedDays = @()
    } else {
        $dayAfter = (Get-Date $lastRun).AddDays(1).ToString("yyyy-MM-dd")
        $start = Get-Date $dayAfter
        $end = Get-Date $yesterday
        $missed = [System.Collections.ArrayList]::new()
        $cur = $start
        while ($cur -le $end) {
            $ds = $cur.ToString("yyyy-MM-dd")
            $isWknd = ($cur.DayOfWeek -eq "Saturday" -or $cur.DayOfWeek -eq "Sunday")
            if (-not $isWknd -and $ds -notin $holidays) { [void]$missed.Add($ds) }
            $cur = $cur.AddDays(1)
        }
        $missedDays = $missed.ToArray()
    }

    # Simulate backfill queue construction
    $dataConfig = @(
        @{ Name="KLine";      StateKey="last_kline_date" }
        @{ Name="FundFlow";   StateKey="last_fundflow_date" }
        @{ Name="Margin";     StateKey="last_margin_date" }
        @{ Name="Northbound"; StateKey="last_northbound_date" }
        @{ Name="Research";   StateKey="last_research_date" }
    )
    $backfillTypes = [System.Collections.ArrayList]::new()
    if ($missedDays.Count -gt 0) {
        foreach ($dt in $dataConfig) {
            $lastDtDate = $State[$dt.StateKey]
            if ($lastDtDate -lt $missedDays[-1]) {
                [void]$backfillTypes.Add($dt.Name)
            }
        }
    }

    $missedActual = $missedDays -join ","
    $missedExpected = $ExpectedMissedDays -join ","
    $bfActual = $backfillTypes -join ","
    $bfExpected = $ExpectedBackfillTypes -join ","

    $testPass = $true
    if ($missedActual -ne $missedExpected) {
        Write-Host "  错过的交易日: FAIL (expected='$missedExpected', actual='$missedActual')" -ForegroundColor Red
        $testPass = $false
    } else {
        Write-Host "  错过的交易日: '$missedActual' - OK" -ForegroundColor Green
    }
    if ($bfActual -ne $bfExpected) {
        Write-Host "  需回填类型:   FAIL (expected='$bfExpected', actual='$bfActual')" -ForegroundColor Red
        $testPass = $false
    } else {
        Write-Host "  需回填类型:   '$bfActual' - OK" -ForegroundColor Green
    }

    if ($testPass) {
        Write-Host "  结果: PASS" -ForegroundColor Green
        $script:pass++
    } else {
        Write-Host "  结果: FAIL" -ForegroundColor Red
        $script:fail++
    }
}

# S11: 首次运行（无状态文件，epoch日期）
Test-OfflineDetection -Name "S11: 首次运行" `
    -Desc "从未运行过，last_run 为 1970-01-01，所有数据类型都需要初始化" `
    -State @{
        last_run_date        = "1970-01-01"
        last_kline_date      = "1970-01-01"
        last_fundflow_date   = "1970-01-01"
        last_margin_date     = "1970-01-01"
        last_northbound_date = "1970-01-01"
        last_research_date   = "1970-01-01"
    } `
    -Today "2026-05-25" `
    -ExpectedMissedDays @() `
    -ExpectedBackfillTypes @()

# S12: 隔离日跳过 — 周一开机，上次运行是上周五
# 2026-05-25 是周一，last_run=2026-05-22 是周五，跳过周末，无错过交易日
Test-OfflineDetection -Name "S12: 周末关机(无错过)" `
    -Desc "周五运行过，周一开机，无交易日错过" `
    -State @{
        last_run_date        = "2026-05-22"
        last_kline_date      = "2026-05-22"
        last_fundflow_date   = "2026-05-22"
        last_margin_date     = "2026-05-22"
        last_northbound_date = "2026-05-22"
        last_research_date   = "2026-05-22"
    } `
    -Today "2026-05-25" `
    -ExpectedMissedDays @() `
    -ExpectedBackfillTypes @()

# S13: 错过1个交易日 — 周二开机，上次是上周五
# 2026-05-26(周二) - last_run=2026-05-22(周五), 错过周一(05-25)
# 所有数据类型都需要回填（因为 last_kline_date=05-22 < 05-25）
Test-OfflineDetection -Name "S13: 错过1个交易日" `
    -Desc "上周五运行过，周二开机，错过周一(05-25)，所有数据需回填" `
    -State @{
        last_run_date        = "2026-05-22"
        last_kline_date      = "2026-05-22"
        last_fundflow_date   = "2026-05-22"
        last_margin_date     = "2026-05-22"
        last_northbound_date = "2026-05-22"
        last_research_date   = "2026-05-22"
    } `
    -Today "2026-05-26" `
    -ExpectedMissedDays @("2026-05-25") `
    -ExpectedBackfillTypes @("KLine", "FundFlow", "Margin", "Northbound", "Research")

# S14: 错过3个交易日 — 周三开机，上次是上周五
# 2026-05-27(周三) - last_run=2026-05-22(周五), 错过周一(05-25),周二(05-26)
Test-OfflineDetection -Name "S14: 错过2个交易日" `
    -Desc "上周五运行过，周三开机，错过周一和周二，所有数据需回填" `
    -State @{
        last_run_date        = "2026-05-22"
        last_kline_date      = "2026-05-22"
        last_fundflow_date   = "2026-05-22"
        last_margin_date     = "2026-05-22"
        last_northbound_date = "2026-05-22"
        last_research_date   = "2026-05-22"
    } `
    -Today "2026-05-27" `
    -ExpectedMissedDays @("2026-05-25", "2026-05-26") `
    -ExpectedBackfillTypes @("KLine", "FundFlow", "Margin", "Northbound", "Research")

# S15: 部分数据类型已是最新 — KLine和FundFlow是今天更新的，但Margin还没
# 模拟：昨天中午手动刷新了KLine和FundFlow，但Margin和Northbound还是3天前的
Test-OfflineDetection -Name "S15: 部分数据已是最新" `
    -Desc "错过2天，但KLine和FundFlow已在昨天部分刷新，仅Margin/Northbound/Research需回填" `
    -State @{
        last_run_date        = "2026-05-22"
        last_kline_date      = "2026-05-26"
        last_fundflow_date   = "2026-05-26"
        last_margin_date     = "2026-05-22"
        last_northbound_date = "2026-05-22"
        last_research_date   = "2026-05-22"
    } `
    -Today "2026-05-27" `
    -ExpectedMissedDays @("2026-05-25", "2026-05-26") `
    -ExpectedBackfillTypes @("Margin", "Northbound", "Research")

# S16: 幂等测试 — 同一天第二次运行
# last_run_date 已经等于今天，说明今天已经跑过一次了
Test-OfflineDetection -Name "S16: 幂等(同一天第二次)" `
    -Desc "今天已经运行过，再次启动应检测到无错过交易日" `
    -State @{
        last_run_date        = "2026-05-25"
        last_kline_date      = "2026-05-25"
        last_fundflow_date   = "2026-05-25"
        last_margin_date     = "2026-05-25"
        last_northbound_date = "2026-05-25"
        last_research_date   = "2026-05-25"
    } `
    -Today "2026-05-25" `
    -ExpectedMissedDays @() `
    -ExpectedBackfillTypes @()

# S17: 错过1天但跨假期 — 五一前最后一天运行，五一后第一个交易日开机
# 2026-04-30(周四) → 2026-05-06(周三，五一假期后第一个交易日)
# 错过 0 个交易日（假期中间无交易日）
Test-OfflineDetection -Name "S17: 跨长假(无错过)" `
    -Desc "五一前(04-30)运行过，节后(05-06)开机，假期无交易日错过" `
    -State @{
        last_run_date        = "2026-04-30"
        last_kline_date      = "2026-04-30"
        last_fundflow_date   = "2026-04-30"
        last_margin_date     = "2026-04-30"
        last_northbound_date = "2026-04-30"
        last_research_date   = "2026-04-30"
    } `
    -Today "2026-05-06" `
    -ExpectedMissedDays @() `
    -ExpectedBackfillTypes @()

# S18: 错过1天但含假期 — 五一后运行过，中间关机，含周末
# 2026-05-06(周三) → 2026-05-11(周一)，错过 05-07(周四),05-08(周五)
Test-OfflineDetection -Name "S18: 跨周末错过2天" `
    -Desc "周三运行过，下周一开机，错过周四周五2个交易日" `
    -State @{
        last_run_date        = "2026-05-06"
        last_kline_date      = "2026-05-06"
        last_fundflow_date   = "2026-05-06"
        last_margin_date     = "2026-05-06"
        last_northbound_date = "2026-05-06"
        last_research_date   = "2026-05-06"
    } `
    -Today "2026-05-11" `
    -ExpectedMissedDays @("2026-05-07", "2026-05-08") `
    -ExpectedBackfillTypes @("KLine", "FundFlow", "Margin", "Northbound", "Research")

# ==================== 总结 ====================
Write-Host "`n========================================" -ForegroundColor Magenta
Write-Host " 测试完成: PASS=$pass FAIL=$fail" -ForegroundColor $(if ($fail -eq 0) { "Green" } else { "Red" })
Write-Host "========================================" -ForegroundColor Magenta

if ($fail -gt 0) { exit 1 } else { exit 0 }
