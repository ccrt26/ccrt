# 依赖: dot-source "$PSScriptRoot/core.ps1"

function Get-StockFinancial {
    param(
        [Parameter(Mandatory=$true)][string]$Code,
        [int]$Quarters = 4  # 返回最近N个季度
    )

    # --- 缓存优先（财务数据季度更新，Tier 3）---
    $cached = Load-DataCache -Key "Financial_$Code" -TTLHours 168
    if ($cached) {
        $script:SourceUsed["Financial"] = "缓存"
        return $cached
    }

    $secucode = if ($Code.StartsWith("6")) { "${Code}.SH" } else { "${Code}.SZ" }
    $encoded = [System.Web.HttpUtility]::UrlEncode($secucode)
    $url = "http://datacenter.eastmoney.com/api/data/v1/get?reportName=RPT_LICO_FN_CPD&columns=ALL&filter=(SECUCODE=%22${encoded}%22)&pageSize=${Quarters}&sortColumns=NOTICE_DATE&sortTypes=-1"

    try {
        $r = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 8 -Headers @{"User-Agent"="Mozilla/5.0"}
        $json = $r.Content | ConvertFrom-Json
        if ($json.result -and $json.result.data) {
            # P0-1: 字段合理性校验 — 关键字段为0则尝试THS降级
            $latest = $json.result.data[0]
            $hasDataIssue = $false
            if ($latest.PSObject.Properties.Name -contains 'OPERATE_COST') {
                $operateCost = [double]$latest.OPERATE_COST
                $operateIncome = [double]$latest.TOTAL_OPERATE_INCOME
                if ($operateCost -eq 0 -and $operateIncome -gt 0) { $hasDataIssue = $true }
            }
            if ($latest.PSObject.Properties.Name -contains 'DEBT_ASSET_RATIO') {
                if ([double]$latest.DEBT_ASSET_RATIO -eq 0) { $hasDataIssue = $true }
            }
            if (-not $hasDataIssue) {
                $script:SourceUsed["Financial"] = "东方财富"
                Save-DataCache -Key "Financial_$Code" -Data $json.result.data
                return $json.result.data
            } else {
                Write-Warning "[财务] 东方财富关键字段异常(OPERATE_COST=0或DEBT_ASSET_RATIO=0)，尝试THS降级"
            }
        }
    } catch {
        Write-Warning "Get-StockFinancial failed for $Code : $_"
        # 尝试同花顺 THS 备份
        Write-Warning "[财务] 尝试同花顺 THS 备份..."
        $thsResult = Invoke-ThsFallback -Action "financial" -Params "--code $Code --quarters $Quarters"
        if ($thsResult) {
            $script:SourceUsed["Financial"] = "同花顺"
            Save-DataCache -Key "Financial_$Code" -Data $thsResult
            return $thsResult
        }
    }
    $script:SourceUsed["Financial"] = "失败"
    # 过期缓存兜底（API双源均失败时的最后手段）
    $staleCache = Load-DataCache -Key "Financial_$Code" -TTLHours 720
    if ($staleCache) { Write-Warning "[财务] API双源失败，使用过期缓存兜底"; return $staleCache }
    return $null
}

# ============================================================
# [3a] 财务比率提取（偿债能力 + 运营效率）
# 从Get-StockFinancial已有全字段响应中提取
# 依赖: Get-StockFinancial
# ============================================================
function Get-FinancialRatios {
    param(
        [Parameter(Mandatory=$true)][string]$Code,
        [int]$Quarters = 1
    )

    $cached = Load-DataCache -Key "FinancialRatios_${Code}" -TTLHours 168
    if ($cached) {
        $script:SourceUsed["FinancialRatios"] = "缓存[C]"
        return $cached
    }

    $finData = Get-StockFinancial -Code $Code -Quarters $Quarters
    if (-not $finData -or $finData.Count -eq 0) { return $null }
    $latest = $finData[0]
    $props = $latest.PSObject.Properties.Name

    # -- 偿债能力 --
    $debtAssetRatio = if ($props -contains 'DEBT_ASSET_RATIO') { [double]$latest.DEBT_ASSET_RATIO } else { $null }

    $currentRatio = $null; $currentRatioSrc = "不可得"
    if ($props -contains 'CURRENT_RATIO') {
        $currentRatio = [double]$latest.CURRENT_RATIO; $currentRatioSrc = "API直取"
    } elseif ($props -contains 'TOTAL_CURRENT_ASSETS' -and $props -contains 'TOTAL_CURRENT_LIABILITIES') {
        $ca = [double]$latest.TOTAL_CURRENT_ASSETS; $cl = [double]$latest.TOTAL_CURRENT_LIABILITIES
        if ($cl -gt 0) { $currentRatio = [math]::Round($ca / $cl, 2); $currentRatioSrc = "自算" }
    }

    $quickRatio = $null; $quickRatioSrc = "不可得"
    if ($props -contains 'QUICK_RATIO') {
        $quickRatio = [double]$latest.QUICK_RATIO; $quickRatioSrc = "API直取"
    } elseif ($props -contains 'TOTAL_CURRENT_ASSETS' -and $props -contains 'INVENTORY' -and $props -contains 'TOTAL_CURRENT_LIABILITIES') {
        $ca = [double]$latest.TOTAL_CURRENT_ASSETS; $inv = [double]$latest.INVENTORY
        $cl = [double]$latest.TOTAL_CURRENT_LIABILITIES
        if ($cl -gt 0) { $quickRatio = [math]::Round(($ca - $inv) / $cl, 2); $quickRatioSrc = "自算" }
    }

    $interestDebtRatio = $null
    if ($props -contains 'SHORT_BORROWINGS' -and $props -contains 'LONG_TERM_BORROWINGS' -and $props -contains 'TOTAL_ASSETS') {
        $shortBorrow = [double]$latest.SHORT_BORROWINGS
        $longBorrow = [double]$latest.LONG_TERM_BORROWINGS
        $totalAssets = [double]$latest.TOTAL_ASSETS
        if ($totalAssets -gt 0) { $interestDebtRatio = [math]::Round(($shortBorrow + $longBorrow) / $totalAssets * 100, 2) }
    }

    # -- 运营效率 --
    $arTurnover = $null; $arTurnoverSrc = "不可得"
    if ($props -contains 'TOTAL_OPERATE_INCOME' -and $props -contains 'ACCOUNTS_RECEIVABLE') {
        $revenue = [double]$latest.TOTAL_OPERATE_INCOME
        $ar = [double]$latest.ACCOUNTS_RECEIVABLE
        if ($ar -gt 0) { $arTurnover = [math]::Round($revenue / $ar, 2); $arTurnoverSrc = "自算" }
    }

    $invTurnover = $null; $invTurnoverSrc = "不可得"
    if ($props -contains 'OPERATE_COST' -and $props -contains 'INVENTORY') {
        $cost = [double]$latest.OPERATE_COST
        $inv = [double]$latest.INVENTORY
        if ($inv -gt 0) { $invTurnover = [math]::Round($cost / $inv, 2); $invTurnoverSrc = "自算" }
    }

    # 有息负债率备用：用负债合计估算
    if ($null -eq $interestDebtRatio -and $props -contains 'TOTAL_LIABILITIES' -and $props -contains 'TOTAL_ASSETS') {
        $tl = [double]$latest.TOTAL_LIABILITIES; $ta = [double]$latest.TOTAL_ASSETS
        if ($ta -gt 0) { $interestDebtRatio = [math]::Round($tl / $ta * 100, 2) }
    }

    $result = [PSCustomObject]@{
        DebtAssetRatio         = $debtAssetRatio
        CurrentRatio           = $currentRatio
        CurrentRatioSource     = $currentRatioSrc
        QuickRatio             = $quickRatio
        QuickRatioSource       = $quickRatioSrc
        InterestBearingDebtRatio = $interestDebtRatio
        ARTurnover             = $arTurnover
        ARTurnoverSource       = $arTurnoverSrc
        InventoryTurnover      = $invTurnover
        InventoryTurnoverSource = $invTurnoverSrc
        Source                 = $script:SourceUsed["Financial"]
        DataDate               = $latest.NOTICE_DATE
    }
    $script:SourceUsed["FinancialRatios"] = $script:SourceUsed["Financial"]
    Save-DataCache -Key "FinancialRatios_${Code}" -Data $result
    return $result
}

# ============================================================
# 三情景EPS预测模型 (L1)
# 基线=TTM_EPS × 季节调整 × 增速锚 × 情景乘数
# 不替代AI判断——仅提供计算参考
# ============================================================
function Get-ScenarioEPS {
    param(
        [Parameter(Mandatory=$true)][string]$Code,
        [double]$OptimisticMultiplier = 1.15,
        [double]$PessimisticMultiplier = 0.85
    )

    $cached = Load-DataCache -Key "ScenarioEPS_${Code}" -TTLHours 168
    if ($cached) {
        $script:SourceUsed["ScenarioEPS"] = "缓存[C]"
        return $cached
    }

    # 获取最近4季度 + 历史年度财务数据
    $finQ = Get-StockFinancial -Code $Code -Quarters 8
    if (-not $finQ -or $finQ.Count -lt 4) { return $null }

    # TTM EPS: 最近4个季度BASIC_EPS之和
    $ttmEps = 0; $epsValues = @()
    for ($i = 0; $i -lt [math]::Min(4, $finQ.Count); $i++) {
        $e = [double]$finQ[$i].BASIC_EPS
        $ttmEps += $e; $epsValues += $e
    }
    if ($ttmEps -le 0) { return $null }

    # TTM营收增速：最近4Q营收 vs 前4Q营收 (YoY对比)
    $ttmRevenue = 0; $priorTtmRevenue = 0
    for ($i = 0; $i -lt 4 -and $i -lt $finQ.Count; $i++) {
        $ttmRevenue += [double]$finQ[$i].TOTAL_OPERATE_INCOME
    }
    for ($i = 4; $i -lt 8 -and $i -lt $finQ.Count; $i++) {
        $priorTtmRevenue += [double]$finQ[$i].TOTAL_OPERATE_INCOME
    }
    $growthMedian = if ($priorTtmRevenue -gt 0 -and $ttmRevenue -gt 0) {
        [math]::Max(-0.5, [math]::Min(2.0, ($ttmRevenue - $priorTtmRevenue) / $priorTtmRevenue))
    } else { 0.05 }
    $revenueGrowthRates = @($growthMedian)  # 保持输出兼容

    # 情景计算
    $optEps = [math]::Round($ttmEps * (1 + $growthMedian) * $OptimisticMultiplier, 3)
    $neuEps = [math]::Round($ttmEps * (1 + $growthMedian * 0.7) * 1.0, 3)
    $pesEps = [math]::Round($ttmEps * (1 + [math]::Max(0, $growthMedian) * 0.3) * $PessimisticMultiplier, 3)

    # 当前价
    $quote = Get-StockQuote -Code $Code
    $price = if ($quote -and $quote.Price) { [double]$quote.Price } else { 0 }

    $result = [PSCustomObject]@{
        TTM_EPS                = [math]::Round($ttmEps, 3)
        TTM_EPS_Quarters       = ($epsValues | ForEach-Object { [math]::Round($_, 3) }) -join ', '
        RevenueGrowth3Y_Median = [math]::Round($growthMedian * 100, 1)
        RevenueGrowth3Y_Values = ($revenueGrowthRates | ForEach-Object { [math]::Round($_ * 100, 1) }) -join ', '
        Optimistic_EPS         = $optEps
        Optimistic_PE          = if ($price -gt 0) { [math]::Round($price / $optEps, 1) } else { $null }
        Neutral_EPS            = $neuEps
        Neutral_PE             = if ($price -gt 0) { [math]::Round($price / $neuEps, 1) } else { $null }
        Pessimistic_EPS        = $pesEps
        Pessimistic_PE         = if ($price -gt 0) { [math]::Round($price / $pesEps, 1) } else { $null }
        CurrentPrice           = $price
        ScenarioNote           = "仅供参考，不替代AI判断。乘数: 乐观x${OptimisticMultiplier} / 悲观x${PessimisticMultiplier}"
    }
    $script:SourceUsed["ScenarioEPS"] = $script:SourceUsed["Financial"]
    Save-DataCache -Key "ScenarioEPS_${Code}" -Data $result
    return $result
}

# ============================================================
# 可比公司估值查询 (L0)
# 获取同申万二级行业可比公司的PE/PB/ROE/营收增速
# ============================================================
function Get-ComparableValuation {
    param(
        [Parameter(Mandatory=$true)][string]$Code,
        [int]$TopN = 5
    )

    $cached = Load-DataCache -Key "ComparableValuation_${Code}" -TTLHours 24
    if ($cached) {
        $script:SourceUsed["ComparableValuation"] = "缓存[C]"
        return $cached
    }

    # 先获取目标股票的行业
    $quote = Get-StockQuote -Code $Code
    if (-not $quote) { return $null }
    $industry = $quote.Industry

    # 查询同行业股票（东方财富行业成分股）
    $encoded = [System.Web.HttpUtility]::UrlEncode($industry)
    $url = "http://datacenter.eastmoney.com/api/data/v1/get?reportName=RPT_STOCKINDUSTRY_COMPONENT&columns=SECUCODE,SECURITY_NAME_ABBR&filter=(INDUSTRY_NAME=%22${encoded}%22)&pageSize=30&sortColumns=MARKET_CAP&sortTypes=-1"

    try {
        $r = Invoke-ThrottledApiCall { Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 8 -Headers @{"User-Agent"="Mozilla/5.0"} }
        $json = $r.Content | ConvertFrom-Json
        if (-not $json.result -or -not $json.result.data) { return $null }

        $peers = @()
        $count = 0
        foreach ($item in $json.result.data) {
            $peerCode = if ($item.SECUCODE -match '(\d{6})') { $matches[1] } else { $null }
            if (-not $peerCode -or $peerCode -eq $Code) { continue }
            if ($count -ge $TopN) { break }

            $peerFin = Get-StockFinancial -Code $peerCode -Quarters 2
            $peerQuote = Get-StockQuote -Code $peerCode
            if (-not $peerFin -or -not $peerQuote) { continue }

            $peerEps = [double]$peerFin[0].BASIC_EPS
            $peerPrice = [double]$peerQuote.Price
            $peerPE = if ($peerEps -gt 0) { [math]::Round($peerPrice / $peerEps, 1) } else { $null }
            $peerPB = if ($peerQuote.PSObject.Properties.Name -contains 'PB') { [double]$peerQuote.PB } else { $null }
            $peerROE = if ($peerFin[0].PSObject.Properties.Name -contains 'ROE') { [double]$peerFin[0].ROE } else { $null }
            $peerMktCap = if ($peerQuote.PSObject.Properties.Name -contains 'MktCap') { [double]$peerQuote.MktCap } else { $null }

            $peers += [PSCustomObject]@{
                Code       = $peerCode
                Name       = $item.SECURITY_NAME_ABBR
                PE_TTM     = $peerPE
                PB         = $peerPB
                ROE        = $peerROE
                MktCap     = $peerMktCap
            }
            $count++
        }
        $script:SourceUsed["ComparableValuation"] = "东方财富"
        Save-DataCache -Key "ComparableValuation_${Code}" -Data $peers
        return $peers
    } catch {
        Write-Warning "Get-ComparableValuation failed for $Code : $_"
    }
    $script:SourceUsed["ComparableValuation"] = "失败"
    return $null
}

# ============================================================
# [5] 技术指标计算
# ============================================================