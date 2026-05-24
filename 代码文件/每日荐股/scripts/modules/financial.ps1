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
# [5] 技术指标计算
# ============================================================