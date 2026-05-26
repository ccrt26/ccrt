# 必盈API免费版封装模块 [13]
# 依赖: dot-source "$PSScriptRoot/core.ps1"
# 限流: 免费版200次/天, 自动计数+80%告警+100%熔断
# Licence: 从环境变量 $env:BIYING_LICENCE 读取
# 实测可用: 实时行情/K线/利润表/资产负债表/现金流量表/技术指标

$script:BiyingBaseUrl = "https://api.biyingapi.com"
$script:BiyingDailyLimit = 200
$script:BiyingWarnThreshold = 160
$script:BiyingCallCount = 0
$script:BiyingDateStamp = (Get-Date).Date

function Reset-BiyingCounter {
    $today = (Get-Date).Date
    if ($script:BiyingDateStamp -ne $today) {
        $script:BiyingCallCount = 0
        $script:BiyingDateStamp = $today
    }
}

function Invoke-BiyingApi {
    param(
        [Parameter(Mandatory=$true)][string]$Path,
        [int]$TimeoutSec = 8
    )
. "$PSScriptRoot/../../../lib/init_encoding.ps1"
    Reset-BiyingCounter

    if ($script:BiyingCallCount -ge $script:BiyingDailyLimit) {
        Write-Warning "[必盈API] 日限额${script:BiyingDailyLimit}次已用完，自动降级"
        return $null
    }

    $licence = $env:BIYING_LICENCE
    if (-not $licence) {
        Write-Warning "[必盈API] BIYING_LICENCE 环境变量未设置"
        return $null
    }

    $url = "$script:BiyingBaseUrl/$Path/$licence"
    try {
        $result = Invoke-ThrottledApiCall {
            Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec $TimeoutSec -Headers @{
                "User-Agent" = "Mozilla/5.0"
            }
        }
        $script:BiyingCallCount++

        if ($script:BiyingCallCount -ge $script:BiyingWarnThreshold) {
            Write-Warning "[必盈API] 已达${script:BiyingCallCount}/${script:BiyingDailyLimit}次 (80%告警)"
        }

        if ($result.Content) {
            $json = $result.Content | ConvertFrom-Json
            return $json
        }
        return $null
    } catch {
        Write-Warning "[必盈API] 调用失败 ($Path): $_"
        return $null
    }
}

# ============================================================
# 实时行情（备源 [1-备] 新浪的替代/增强）
# API: /hsstock/real/time/{code}/{licence}  注意: 纯数字代码，不带.SZ/.SH
# ============================================================
function Get-BiyingQuote {
    param([Parameter(Mandatory=$true)][string]$Code)

    $data = Invoke-BiyingApi -Path "hsstock/real/time/$Code"
    if (-not $data -or $data.error) { return $null }

    $result = [PSCustomObject]@{
        Code         = $Code
        Name         = $data.name
        Price        = [double]$data.p
        Open         = [double]$data.o
        High         = [double]$data.h
        Low          = [double]$data.l
        PreClose     = [double]$data.yc
        ChangePct    = [double]$data.zf
        PE           = [double]$data.pe
        PB           = [double]$data.pb_ratio
        TurnRate     = [double]$data.tr
        Volume       = [double]$data.v
        Amount       = [double]$data.cje
        TotalMktCap  = [double]$data.pv
        FloatMktCap  = [double]$data.tv
        UpdateTime   = $data.t
    }
    $script:SourceUsed["Quote"] = "必盈[13]"
    Save-DataCache -Key "Quote_$Code" -Data $result
    return $result
}

# ============================================================
# 历史K线（备源 [2-备] 腾讯的替代/增强）
# API: /hsstock/history/{code}.SZ/{周期}/{除权}/{licence}?st=yyyymmdd&et=yyyymmdd
# 除权: n(不复权)/f(前复权)/b(后复权)/fr(等比前)/br(等比后)
# ============================================================
function Get-BiyingKLine {
    param(
        [Parameter(Mandatory=$true)][string]$Code,
        [string]$Scale = "d",
        [int]$Count = 60,
        [string]$Adjust = "f"
    )
    $market = if ($Code.StartsWith("6")) { "SH" } else { "SZ" }
    $fullCode = "${Code}.${market}"
    $endDate = (Get-Date).ToString("yyyyMMdd")
    $startDate = (Get-Date).AddDays(-$Count * 2).ToString("yyyyMMdd")

    $data = Invoke-BiyingApi -Path "hsstock/history/${fullCode}/${Scale}/${Adjust}?st=${startDate}&et=${endDate}&lt=${Count}"
    if (-not $data) { return $null }
    if ($data -isnot [array]) { return $null }

    $result = $data | ForEach-Object {
        [PSCustomObject]@{
            Date      = [datetime]::Parse($_.t).ToString("yyyy-MM-dd")
            Open      = [double]$_.o
            High      = [double]$_.h
            Low       = [double]$_.l
            Close     = [double]$_.c
            Volume    = [double]$_.v
            Amount    = [double]$_.a
            PreClose  = [double]$_.pc
        }
    }
    $script:SourceUsed["KLine"] = "必盈[13]"
    Save-DataCache -Key "KLine_${Code}_${Scale}_${Count}" -Data $result
    return $result
}

# ============================================================
# 财务三大报表（备源 [3] 东方财富的增强）
# 利润表: /hsstock/financial/income/{code}.SZ/{licence}
# 资产负债表: /hsstock/financial/balance/{code}.SZ/{licence}
# 现金流量表: /hsstock/financial/cashflow/{code}.SZ/{licence}
# 返回多季度数据，最新季度在第一个
# ============================================================
function Get-BiyingFinancial {
    param(
        [Parameter(Mandatory=$true)][string]$Code,
        [int]$Quarters = 4
    )
    $market = if ($Code.StartsWith("6")) { "SH" } else { "SZ" }
    $fullCode = "${Code}.${market}"

    # 利润表（含 EPS/净利润/营收）
    $income = Invoke-BiyingApi -Path "hsstock/financial/income/${fullCode}"
    if (-not $income -or $income -isnot [array]) { return $null }

    $result = @()
    $count = [math]::Min($Quarters, $income.Count)
    for ($i = 0; $i -lt $count; $i++) {
        $item = $income[$i]
        $result += [PSCustomObject]@{
            ReportDate   = $item.jzrq
            PublishDate  = $item.plrq
            Revenue      = [double]$item.yysr
            OperCost     = [double]$item.yyzcb
            NetProfit    = [double]$item.jlr
            ParentProfit = [double]$item.gsmgsyzzdjlr
            BasicEPS     = [double]$item.jbmgsy
            DilutedEPS   = if ($item.kfmgsy -and $item.kfmgsy -ne "-") { [double]$item.kfmgsy } else { [double]$item.jbmgsy }
        }
    }
    $script:SourceUsed["Financial"] = "必盈[13]"
    Save-DataCache -Key "Financial_${Code}_${Quarters}" -Data $result
    return $result
}
