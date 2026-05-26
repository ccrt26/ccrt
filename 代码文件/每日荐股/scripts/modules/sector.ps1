# 依赖: dot-source "$PSScriptRoot/core.ps1"

function Get-SectorData {
    param([int]$Top = 10)
. "$PSScriptRoot/../../../lib/init_encoding.ps1"
    $url = "http://push2.eastmoney.com/api/qt/clist/get?cb=&pn=1&pz=${Top}&po=1&np=1&ut=bd1d9ddb04089700cf9c27f6f7426281&fltt=2&invt=2&fid=f3&fs=m:90+t:2&fields=f2,f3,f4,f12,f14"
    try {
        $r = Invoke-ThrottledApiCall { Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 8 -Headers @{"User-Agent"="Mozilla/5.0"} }
        $json = $r.Content | ConvertFrom-Json
        if ($json.data -and $json.data.diff) {
            $result = $json.data.diff | ForEach-Object {
                [PSCustomObject]@{
                    SectorCode  = $_.f12
                    SectorName  = $_.f14
                    Index       = [double]$_.f2
                    ChangePct   = [double]$_.f3
                    Turnover    = [double]$_.f4
                }
            }
            $script:SourceUsed["Sector"] = "东方财富"
            Save-DataCache -Key "Sector_$Top" -Data $result
            return $result
        }
    } catch {
        Write-Warning "Get-SectorData failed: $_"
        # 尝试同花顺 THS 备份
        Write-Warning "[板块] 尝试同花顺 THS 备份..."
        $thsResult = Invoke-ThsFallback -Action "sector_ranking" -Params "--top $Top"
        if ($thsResult) {
            $script:SourceUsed["Sector"] = "同花顺"
            # 字段对齐：SectorName, ChangePct, Turnover 已兼容
            Save-DataCache -Key "Sector_$Top" -Data $thsResult
            return $thsResult
        }
    }
    $script:SourceUsed["Sector"] = "失败"
    $cached = Load-DataCache -Key "Sector_$Top" -TTLHours 6
    if ($cached) { Write-Warning "[板块] API失败，使用缓存"; return $cached }
    return $null
}

# ============================================================
# [7b] 东方财富板块成分股 — 获取指定板块内的所有股票
# API: push2.eastmoney.com/api/qt/clist/get?fs=b:BKXXXX
# ============================================================
function Get-SectorConstituents {
    param(
        [Parameter(Mandatory=$true)][string]$SectorCode,
        [int]$MaxCount = 50,
        [string]$SortField = "f3"  # f3=涨跌幅排序
    )

    # --- 缓存优先（成分股调整低频，Tier 3）---
    $cached = Load-DataCache -Key "SectorConstituents_$SectorCode" -TTLHours 168
    if ($cached -and @($cached).Count -ge $MaxCount) {
        $script:SourceUsed["SectorConstituents"] = "缓存"
        return $cached
    }

    $url = "http://push2.eastmoney.com/api/qt/clist/get?cb=&pn=1&pz=${MaxCount}&po=1&np=1&ut=bd1d9ddb04089700cf9c27f6f7426281&fltt=2&invt=2&fid=${SortField}&fs=b:${SectorCode}&fields=f12,f14,f2,f3,f4,f15,f16,f17,f18"
    try {
        $r = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 8 -Headers @{"User-Agent"="Mozilla/5.0"}
        $json = $r.Content | ConvertFrom-Json
        if ($json.data -and $json.data.diff) {
            $result = $json.data.diff | ForEach-Object {
                [PSCustomObject]@{
                    Code        = $_.f12
                    Name        = $_.f14
                    Price       = [double]$_.f2
                    ChangePct   = [double]$_.f3
                    Turnover    = [double]$_.f4
                    High        = [double]$_.f15
                    Low         = [double]$_.f16
                    Open        = [double]$_.f17
                    PrevClose   = [double]$_.f18
                }
            }
            $script:SourceUsed["SectorConstituents"] = "东方财富"
            Save-DataCache -Key "SectorConstituents_$SectorCode" -Data $result
            return $result
        }
    } catch {
        Write-Warning "Get-SectorConstituents failed for $SectorCode : $_"
    }
    $script:SourceUsed["SectorConstituents"] = "失败"
    # 过期缓存兜底（API双源均失败时的最后手段）
    $staleCache = Load-DataCache -Key "SectorConstituents_$SectorCode" -TTLHours 720
    if ($staleCache) { Write-Warning "[板块成分股] API双源失败，使用过期缓存兜底"; return $staleCache }
    return $null
}

# ============================================================
# [9] 个股资金流向
# ============================================================
