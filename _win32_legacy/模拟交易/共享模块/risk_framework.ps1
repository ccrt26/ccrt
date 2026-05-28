# ============================================================
# risk_framework.ps1 — 组合级别风控共享模块
# 四级预警体系: 黄旗 → 红旗 → 黑旗 → 连败
# 两个模拟交易赛道共用
# ============================================================

# ---- 单日回撤检测 ----
# 返回: @{ Level="none"|"yellow"|"red"; DailyDD=double; Action="" }
function Get-DailyDrawdownRisk {
    param(
        [double]$CurrentValue,
        [double]$PrevValue,
        [double]$YellowThreshold = 3.0,
        [double]$RedThreshold = 5.0
    )
    if ($PrevValue -le 0) {
        return @{ Level = "none"; DailyDD = 0; Action = "" }
    }
    $dailyDD = [Math]::Round(($CurrentValue / $PrevValue - 1) * 100, 2)
    if ($dailyDD -le -$RedThreshold) {
        return @{ Level = "red"; DailyDD = $dailyDD; Action = "当日减仓50%+停开仓3日" }
    }
    if ($dailyDD -le -$YellowThreshold) {
        return @{ Level = "yellow"; DailyDD = $dailyDD; Action = "次日不开新仓" }
    }
    return @{ Level = "none"; DailyDD = $dailyDD; Action = "" }
}

# ---- 累计回撤检测 ----
function Get-CumulativeDrawdownRisk {
    param(
        [double]$CurrentValue,
        [double]$InitialCapital,
        [double]$BlackThreshold = 10.0,
        [double]$PeakValue = 0
    )
    if ($InitialCapital -le 0) {
        return @{ Level = "none"; TotalDD = 0; Action = "" }
    }
    $totalDD = [Math]::Round(($CurrentValue / $InitialCapital - 1) * 100, 2)
    if ($totalDD -le -$BlackThreshold) {
        return @{ Level = "black"; TotalDD = $totalDD; Action = "暂停系统，全面审查" }
    }
    # 从峰值回撤
    $peakDD = 0
    if ($PeakValue -gt 0) {
        $peakDD = [Math]::Round(($CurrentValue / $PeakValue - 1) * 100, 2)
    }
    return @{ Level = "none"; TotalDD = $totalDD; PeakDD = $peakDD; Action = "" }
}

# ---- 连续亏损检测 ----
function Get-ConsecutiveLossRisk {
    param(
        [int]$ConsecutiveLosses,
        [int]$MaxAllowed = 6
    )
    if ($ConsecutiveLosses -ge $MaxAllowed) {
        return @{ Level = "yellow"; Consecutive = $ConsecutiveLosses; Action = "停开仓，审视信号有效性" }
    }
    return @{ Level = "none"; Consecutive = $ConsecutiveLosses; Action = "" }
}

# ---- 组合风险综合评估 ----
# 汇总所有风险信号，返回统一的风险决策
function Get-PortfolioRiskDecision {
    param(
        [double]$CurrentValue,
        [double]$PrevValue,
        [double]$InitialCapital,
        [double]$PeakValue,
        [int]$ConsecutiveLosses,
        [hashtable]$Config
    )
    $decisions = @()

    # 单日回撤
    $dailyRisk = Get-DailyDrawdownRisk -CurrentValue $CurrentValue -PrevValue $PrevValue `
        -YellowThreshold $Config.YellowFlagDD -RedThreshold $Config.RedFlagDD
    if ($dailyRisk.Level -ne "none") {
        $decisions += @{ Source = "单日回撤"; Level = $dailyRisk.Level; Detail = "日回撤 $($dailyRisk.DailyDD)%"; Action = $dailyRisk.Action }
    }

    # 累计回撤
    $cumRisk = Get-CumulativeDrawdownRisk -CurrentValue $CurrentValue -InitialCapital $InitialCapital `
        -BlackThreshold $Config.BlackFlagDD -PeakValue $PeakValue
    if ($cumRisk.Level -ne "none") {
        $decisions += @{ Source = "累计回撤"; Level = $cumRisk.Level; Detail = "累计亏损 $($cumRisk.TotalDD)%"; Action = $cumRisk.Action }
    }

    # 连续亏损
    $lossRisk = Get-ConsecutiveLossRisk -ConsecutiveLosses $ConsecutiveLosses -MaxAllowed $Config.MaxConsecutiveLosses
    if ($lossRisk.Level -ne "none") {
        $decisions += @{ Source = "连续亏损"; Level = $lossRisk.Level; Detail = "连败 $($lossRisk.Consecutive) 笔"; Action = $lossRisk.Action }
    }

    # 综合判断：取最高风险级别
    $maxLevel = "none"
    $skipOpen = $false
    $forceReduce = $false
    $forceSuspend = $false

    foreach ($d in $decisions) {
        if ($d.Level -eq "black") {
            $maxLevel = "black"
            $forceSuspend = $true
            break
        }
        if ($d.Level -eq "red") { $maxLevel = "red"; $forceReduce = $true; $skipOpen = $true }
        if ($d.Level -eq "yellow" -and $maxLevel -eq "none") { $maxLevel = "yellow"; $skipOpen = $true }
    }

    return @{
        MaxLevel       = $maxLevel
        SkipOpen        = $skipOpen
        ForceReduce     = $forceReduce
        ForceSuspend    = $forceSuspend
        Decisions       = $decisions
        DailyDD         = $dailyRisk.DailyDD
    }
}

# ---- 冷却期管理 ----
# 持久化风险冷却期状态
function Get-RiskCooldownState {
    param(
        [hashtable]$RiskCooldowns,
        [string]$Date
    )
    if (-not $RiskCooldowns -or -not $RiskCooldowns.ContainsKey("RedFlagDate")) {
        return @{ InCooldown = $false; DaysRemaining = 0 }
    }
    $redDate = $RiskCooldowns.RedFlagDate
    if (-not $redDate) { return @{ InCooldown = $false; DaysRemaining = 0 } }
    $d1 = [datetime]::ParseExact($Date, "yyyyMMdd", $null)
    $d2 = [datetime]::ParseExact($redDate, "yyyyMMdd", $null)
    $days = 0
    $current = $d2.AddDays(1)
    while ($current -le $d1) {
        if ($current.DayOfWeek -ge [DayOfWeek]::Monday -and $current.DayOfWeek -le [DayOfWeek]::Friday) {
            $days++
        }
        $current = $current.AddDays(1)
    }
    $cooldownDays = 3
    $remaining = $cooldownDays - $days
    if ($remaining -le 0) {
        return @{ InCooldown = $false; DaysRemaining = 0 }
    }
    return @{ InCooldown = $true; DaysRemaining = $remaining }
}

# ---- 大盘系统性熔断 (山猫 v2026-05-24) ----
# 返回: @{ Level="none"|"warn"|"meltdown"; Action=""; SkipOpen=$false; ForceReduce=$false }
function Get-MarketCircuitBreaker {
    param(
        [double]$CSI300ChangePct,
        [double]$MarketTurnover,    # 全市场成交额(亿)
        [int]$LowTurnoverDays = 0   # 连续低成交天数
    )
    $result = @{ Level = "none"; Action = ""; SkipOpen = $false; ForceReduce = $false }

    if ($CSI300ChangePct -le -5.0) {
        $result.Level = "meltdown"
        $result.Action = "大盘暴跌>5%: 强制减仓50%+停开仓3日"
        $result.SkipOpen = $true
        $result.ForceReduce = $true
    }
    elseif ($CSI300ChangePct -le -3.0) {
        $result.Level = "warn"
        $result.Action = "大盘跌>3%: 当日不开新仓"
        $result.SkipOpen = $true
    }
    elseif ($MarketTurnover -lt 5000 -and $LowTurnoverDays -ge 2) {
        $result.Level = "warn"
        $result.Action = "流动性枯竭(成交<5000亿连续2日): 开仓金额减半"
        $result.SkipOpen = $false
    }
    return $result
}

# ---- 板块相位持仓检查 (山猫 v2026-05-24) ----
# 返回: @{ Warnings=@(); ForceReduce=@() }
function Get-SectorPhaseAlerts {
    param(
        [hashtable]$Positions,       # 当前持仓 { code -> @{EntrySectorPhase, ...} }
        [hashtable]$CurrentPhases,   # 当前板块相位 { sector_name -> "主升"|"潜伏期"|"高潮期"|"衰退期" }
        [hashtable]$ConfidenceMap    # 当前主线置信度 { sector_name -> 0-100 }
    )
    $warnings = @()
    $forceReduce = @()

    foreach ($code in $Positions.Keys) {
        $pos = $Positions[$code]
        $sector = if ($pos.EntryIndustry) { $pos.EntryIndustry } else { $pos.EntrySector }
        if (-not $sector) { continue }
        $entryPhase = $pos.EntrySectorPhase
        $currentPhase = $CurrentPhases[$sector]
        $currentConf = $ConfidenceMap[$sector]

        if (-not $currentPhase) { continue }

        # 板块退入衰退期
        if ($currentPhase -eq "衰退期" -and $entryPhase -ne "衰退期") {
            $warnings += @{ Code = $code; Reason = "板块恶化: ${sector} ${entryPhase}→衰退期"; Level = "yellow" }
        }

        # 主线置信度跌破40 → 强制减仓 (L1直接触发,无需对比entry置信度)
        if ($currentConf -and $currentConf -lt 40) {
            $forceReduce += @{ Code = $code; Reason = "主线置信度崩塌: ${sector} 当前置信度=${currentConf}<40"; Level = "red" }
        }
    }

    return @{ Warnings = $warnings; ForceReduce = $forceReduce }
}

# ---- 行业集中度检查 (流金 v2026-05-24) ----
function Get-IndustryConcentration {
    param(
        [hashtable]$Positions,
        [int]$MaxPerIndustry = 2
    )
    $industryCount = @{}
    foreach ($code in $Positions.Keys) {
        $pos = $Positions[$code]
        if ($pos.Shares -le 0) { continue }
        $ind = $pos.EntryIndustry
        if (-not $ind) { $ind = "未知" }
        if (-not $industryCount.ContainsKey($ind)) { $industryCount[$ind] = @() }
        $industryCount[$ind] += $code
    }

    $violations = @{}
    foreach ($ind in $industryCount.Keys) {
        if ($industryCount[$ind].Count -gt $MaxPerIndustry) {
            $violations[$ind] = $industryCount[$ind]
        }
    }
    return @{ Counts = $industryCount; Violations = $violations }
}

# ---- 恢复检测 ----
function Test-RecoveryCondition {
    param(
        [double]$DailyDD,
        [double]$Threshold = 1.0
    )
    return [Math]::Abs($DailyDD) -lt $Threshold
}
