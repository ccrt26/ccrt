# 依赖: dot-source "$PSScriptRoot/core.ps1"
# 最后更新: 2026-05-25 — 接入Invoke-DataSource统一降级引擎

function Get-StockFinancial {
    param(
        [Parameter(Mandatory=$true)][string]$Code,
        [int]$Quarters = 4  # 返回最近N个季度
    )
. "$PSScriptRoot/../../../lib/init_encoding.ps1"

    return Invoke-DataSource -Category "Financial" `
        -CacheKey "Financial_$Code" `
        -PrimaryName "东方财富[3]" `
        -BackupName "备源链(THS→必盈)" `
        -PrimaryCall {
            $secucode = if ($Code.StartsWith("6")) { "${Code}.SH" } else { "${Code}.SZ" }
            $encoded = [System.Web.HttpUtility]::UrlEncode($secucode)
            $url = "http://datacenter.eastmoney.com/api/data/v1/get?reportName=RPT_LICO_FN_CPD&columns=ALL&filter=(SECUCODE=%22${encoded}%22)&pageSize=${Quarters}&sortColumns=NOTICE_DATE&sortTypes=-1"

            $r = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 8 -Headers @{"User-Agent"="Mozilla/5.0"}
            $json = $r.Content | ConvertFrom-Json
            if ($json.result -and $json.result.data) {
                return $json.result.data
            }
            return $null
        } `
        -ValidateBlock {
            param($data)
            if (-not $data -or $data.Count -eq 0) { return $false }
            $latest = $data[0]
            $props = $latest.PSObject.Properties.Name
            if ($props -contains 'OPERATE_COST') {
                $oc = [double]$latest.OPERATE_COST
                $oi = [double]$latest.TOTAL_OPERATE_INCOME
                if ($oc -eq 0 -and $oi -gt 0) {
                    Write-Warning "[财务] 东方财富字段异常(OPERATE_COST=0)，触发备源降级"
                    return $false
                }
            }
            if ($props -contains 'DEBT_ASSET_RATIO') {
                if ([double]$latest.DEBT_ASSET_RATIO -eq 0) {
                    Write-Warning "[财务] 东方财富字段异常(DEBT_ASSET_RATIO=0)，触发备源降级"
                    return $false
                }
            }
            return $true
        } `
        -BackupCall {
            # 第一备源：同花顺 THS
            Write-Warning "[财务] 尝试同花顺 THS 备源..."
            $thsResult = Invoke-ThsFallback -Action "financial" -Params "--code $Code --quarters $Quarters"
            if ($thsResult) {
                $script:SourceUsed["Financial"] = "同花顺[THS]"
                return $thsResult
            }

            # 第二备源：必盈API[13] 利润表→映射
            Write-Warning "[财务] 尝试必盈API[13]备源..."
            $biyingFin = Get-BiyingFinancial -Code $Code -Quarters $Quarters
            if ($biyingFin -and $biyingFin.Count -gt 0) {
                $mapped = $biyingFin | ForEach-Object {
                    [PSCustomObject]@{
                        BASIC_EPS            = $_.BasicEPS
                        DILUTED_EPS          = $_.DilutedEPS
                        TOTAL_OPERATE_INCOME = $_.Revenue
                        OPERATE_COST         = $_.OperCost
                        NET_PROFIT           = $_.NetProfit
                        PARENT_NET_PROFIT    = $_.ParentProfit
                        NOTICE_DATE          = $_.PublishDate
                        REPORT_DATE          = $_.ReportDate
                        DEBT_ASSET_RATIO     = $null
                        CURRENT_RATIO        = $null
                        QUICK_RATIO          = $null
                        TOTAL_CURRENT_ASSETS = $null
                        TOTAL_CURRENT_LIABILITIES = $null
                        INVENTORY            = $null
                        SHORT_BORROWINGS     = $null
                        LONG_TERM_BORROWINGS = $null
                        TOTAL_ASSETS         = $null
                        ACCOUNTS_RECEIVABLE  = $null
                        TOTAL_LIABILITIES    = $null
                        ROE                  = $null
                    }
                }
                $script:SourceUsed["Financial"] = "必盈[13]"
                return $mapped
            }
            return $null
        }
}

# ============================================================
# [3b] 财务明细提取（毛利率 + 商誉 + 扣非EPS）
# 从东方财富RPT_DMSK_FN_INCOME端点获取利润表详细字段
# 依赖: 东方财富[3] 利润表端点
# v2026-05-27: 修复毛利率/商誉/扣非EPS全线缺失问题(设计: design_financial_data_fix_20260527)
# ============================================================
function Get-FinancialDetail {
    param(
        [Parameter(Mandatory=$true)][string]$Code,
        [int]$Quarters = 1
    )

    $cached = Import-DataCache -Key "FinancialDetail_${Code}" -TTLHours 168
    if ($cached) {
        $script:SourceUsed["FinancialDetail"] = "缓存[C]"
        return $cached
    }

    try {
        $secucode = if ($Code.StartsWith("6")) { "${Code}.SH" } else { "${Code}.SZ" }
        $encoded = [System.Web.HttpUtility]::UrlEncode($secucode)
        # 利润表详细端点 — 含GROSS_PROFIT_MARGIN / GOODWILL / DEDUCTED_EPS
        $url = "http://datacenter.eastmoney.com/api/data/v1/get?reportName=RPT_DMSK_FN_INCOME&columns=ALL&filter=(SECUCODE=%22${encoded}%22)&pageSize=${Quarters}&sortColumns=NOTICE_DATE&sortTypes=-1"

        $r = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 8 -Headers @{"User-Agent"="Mozilla/5.0"}
        $json = $r.Content | ConvertFrom-Json
        if ($json.result -and $json.result.data -and $json.result.data.Count -gt 0) {
            $latest = $json.result.data[0]
            $props = $latest.PSObject.Properties.Name

            $result = [PSCustomObject]@{
                GROSS_PROFIT_MARGIN = if ($props -contains 'GROSS_PROFIT_MARGIN') { [double]$latest.GROSS_PROFIT_MARGIN } else { $null }
                GOODWILL           = if ($props -contains 'GOODWILL') { [double]$latest.GOODWILL } else { $null }
                DEDUCTED_EPS       = if ($props -contains 'DEDUCTED_EPS') { [double]$latest.DEDUCTED_EPS } else { $null }
                OPERATE_COST       = if ($props -contains 'OPERATE_COST') { [double]$latest.OPERATE_COST } else { $null }
                TOTAL_OPERATE_INCOME = if ($props -contains 'TOTAL_OPERATE_INCOME') { [double]$latest.TOTAL_OPERATE_INCOME } else { $null }
                NOTICE_DATE        = $latest.NOTICE_DATE
                SOURCE             = "东方财富[3a]"
            }
            $script:SourceUsed["FinancialDetail"] = "东方财富[3a]"
            Export-DataCache -Key "FinancialDetail_${Code}" -Data $result
            return $result
        }
    } catch {
        Write-Warning "[财务明细] ${Code}: 东方财富利润表端点失败 → $_"
    }

    # Fallback: 尝试从Get-StockFinancial全字段中提取（原逻辑已覆盖毛利率3字段fallback）
    $script:SourceUsed["FinancialDetail"] = "失败→调用方降级"
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

    $cached = Import-DataCache -Key "FinancialRatios_${Code}" -TTLHours 168
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
    Export-DataCache -Key "FinancialRatios_${Code}" -Data $result
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

    $cached = Import-DataCache -Key "ScenarioEPS_${Code}" -TTLHours 168
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
    Export-DataCache -Key "ScenarioEPS_${Code}" -Data $result
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

    $cached = Import-DataCache -Key "ComparableValuation_${Code}" -TTLHours 24
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
        Export-DataCache -Key "ComparableValuation_${Code}" -Data $peers
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
