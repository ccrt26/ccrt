# 实时验证：优化版操作建议 vs 实时行情
$rootDir = "C:\Users\34269\Documents\Claude\股票分析"
Import-Module (Join-Path $rootDir "每日荐股\scripts\stock_data_fetcher.psm1") -Force -WarningAction SilentlyContinue 2>$null

$stocks = @(
    @{ Code = "603019"; Name = "中科曙光" },
    @{ Code = "601689"; Name = "拓普集团" },
    @{ Code = "600114"; Name = "东睦股份" },
    @{ Code = "301075"; Name = "多瑞医药" },
    @{ Code = "000967"; Name = "盈峰环境" },
    @{ Code = "600036"; Name = "招商银行" }
)

# 优化版分析结果（从PDF/HTML报告提取的关键数据）
$optResults = @{
    "603019" = @{ Tech=45;Fund=39;Sent=20;Sect=55;Cap=53;Mac=100;Comp=48;Short="中性";Conf="低(<50%)";S1=92.43;R1=95.39;SL=79.49;MaxPos=10 }
    "601689" = @{ Tech=73;Fund=39;Sent=23;Sect=55;Cap=33;Mac=100;Comp=54;Short="偏多";Conf="中(50-70%)";S1=64.12;R1=72.86;SL=57.39;MaxPos=10 }
    "600114" = @{ Tech=65;Fund=39;Sent=23;Sect=55;Cap=58;Mac=100;Comp=55;Short="偏多";Conf="高(>70%)";S1=33.7;R1=38.49;SL=27.41;MaxPos=10 }
    "301075" = @{ Tech=83;Fund=67;Sent=20;Sect=55;Cap=33;Mac=100;Comp=64;Short="看多";Conf="高(>70%)";S1=82.49;R1=86.51;SL=61.43;MaxPos=10 }
    "000967" = @{ Tech=31;Fund=59;Sent=20;Sect=55;Cap=60;Mac=100;Comp=50;Short="中性";Conf="低(<50%)";S1=12.3;R1=13.95;SL=7.67;MaxPos=10 }
    "600036" = @{ Tech=23;Fund=47;Sent=55;Sect=55;Cap=58;Mac=100;Comp=46;Short="中性";Conf="低(<50%)";S1=36.27;R1=38.34;SL=34.12;MaxPos=10 }
}

Write-Host "`n========== 优化版 vs 实时行情验证 =========="
Write-Host "验证时间: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
Write-Host "`n"

foreach ($s in $stocks) {
    $code = $s.Code; $name = $s.Name
    $o = $optResults[$code]
    Write-Host "──────────────────────────────────────────────"
    Write-Host "【$name ($code)】"

    # 获取实时行情
    $q = Get-StockQuote -Code $code
    if (-not $q) { Write-Host "  行情获取失败"; continue }
    $price = $q.Price

    Write-Host "  实时价格: $price | 涨跌幅: $($q.ChangePct)% | 换手: $($q.TurnoverRate)%"

    # 最近3根K线
    $kl = Get-StockKLine -Code $code -Scale 240 -Count 5
    if ($kl -and $kl.Count -ge 2) {
        $openToday = $kl[-1].Open
        $highToday = $kl[-1].High
        $lowToday = $kl[-1].Low
        $closeToday = $kl[-1].Close
        $volToday = $kl[-1].Volume

        # 昨收 = 前一根的收盘
        $prevClose = $kl[-2].Close
        $chgPct = [Math]::Round(($closeToday - $prevClose) / $prevClose * 100, 2)

        Write-Host "  今日K线: 开$openToday 高$highToday 低$lowToday 收$closeToday"
        Write-Host "  今日涨跌: $chgPct% | 昨收: $prevClose"

        # --- 对照优化版建议验证 ---
        Write-Host ""
        Write-Host "  [优化版建议]"
        Write-Host "  综合评分: $($o.Comp)分 | 短期方向: $($o.Short) | 置信度: $($o.Conf)"
        Write-Host "  支撑S1: $($o.S1) | 阻力R1: $($o.R1) | 止损: $($o.SL) | 仓位上限: $($o.MaxPos)%"

        # 验证1: 价格在支撑/阻力中的位置
        $distToS1 = [Math]::Round(($price - $o.S1) / $o.S1 * 100, 1)
        $distToR1 = [Math]::Round(($o.R1 - $price) / $price * 100, 1)
        Write-Host "  [位置验证] 距S1: $distToS1% | 距R1: $distToR1%"

        if ($price -le $o.S1 * 1.02 -and $price -ge $o.S1 * 0.98) {
            Write-Host "  ⚡ 当前价格在S1($($o.S1))附近,符合买入条件"
        } elseif ($price -le $o.S1) {
            Write-Host "  ⚡ 已跌破S1($($o.S1)),需观察是否企稳"
        } elseif ($price -ge $o.R1 * 0.98 -and $price -le $o.R1 * 1.02) {
            Write-Host "  ⚡ 当前价格在R1($($o.R1))附近,注意遇阻"
        }

        # 验证2: 今日涨跌方向 vs 优化版短期方向
        if ($o.Short -eq "看多" -or $o.Short -eq "偏多") {
            if ($chgPct -gt 0) {
                Write-Host "  ✅ 方向验证: 优化版看多($($o.Short)) → 今日上涨($chgPct%), 方向正确"
            } elseif ($chgPct -lt -1) {
                Write-Host "  ❌ 方向验证: 优化版看多($($o.Short)) → 今日下跌($chgPct%), 方向不符(需观察T+1)"
            } else {
                Write-Host "  🔶 方向验证: 优化版看多($($o.Short)) → 今日微跌($chgPct%), 待观察"
            }
        } elseif ($o.Short -eq "中性") {
            if ($chgPct -gt 1) {
                Write-Host "  🔶 方向验证: 优化版中性 → 今日上涨($chgPct%), 偏强超出预期"
            } elseif ($chgPct -lt -1) {
                Write-Host "  🔶 方向验证: 优化版中性 → 今日下跌($chgPct%), 偏弱在预期内"
            } else {
                Write-Host "  ✅ 方向验证: 优化版中性 → 今日窄幅震荡($chgPct%), 符合预期"
            }
        }

        # 验证3: 趋势健康度参考（基于今日K线简单判断）
        if ($chgPct -gt 2) { $todayHealth = "强势上涨" }
        elseif ($chgPct -gt 0) { $todayHealth = "温和上涨" }
        elseif ($chgPct -gt -1) { $todayHealth = "窄幅震荡" }
        elseif ($chgPct -gt -2) { $todayHealth = "温和下跌" }
        else { $todayHealth = "明显下跌" }

        Write-Host "  [今日状态] $todayHealth ($chgPct%)"

        # 验证4: 量价配合
        if ($kl.Count -ge 3) {
            $avgVol = [Math]::Round(($kl[-2].Volume + $kl[-3].Volume) / 2, 0)
            if ($avgVol -gt 0) {
                $volRatio = [Math]::Round($volToday / $avgVol, 1)
                if ($volRatio -gt 1.5 -and $chgPct -gt 0) {
                    Write-Host "  [量价] 放量上涨(量比$volRatio), 走势健康"
                } elseif ($volRatio -gt 1.5 -and $chgPct -lt 0) {
                    Write-Host "  [量价] 放量下跌(量比$volRatio), 注意风险"
                } elseif ($volRatio -lt 0.7 -and $chgPct -gt 0) {
                    Write-Host "  [量价] 缩量上涨(量比$volRatio), 动力不足"
                } elseif ($volRatio -lt 0.7 -and $chgPct -lt 0) {
                    Write-Host "  [量价] 缩量下跌(量比$volRatio), 抛压减弱"
                } else {
                    Write-Host "  [量价] 量能正常(量比$volRatio)"
                }
            }
        }
    } else {
        Write-Host "  K线数据不足"
    }
    Write-Host ""
}

Write-Host "=========================================="
Write-Host "验证完成: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
