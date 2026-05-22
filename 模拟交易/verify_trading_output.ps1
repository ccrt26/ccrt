# 铁律量化 - 模拟交易输出完整性验证脚本
# 用法: powershell -File verify_trading_output.ps1 -Date 20260523

param(
    [string]$Date = (Get-Date).ToString("yyyyMMdd"),
    [int]$MinTransactions = 1
)

$rootDir = "C:\Users\34269\Documents\Claude\股票分析"
$tradingDir = Join-Path $rootDir "模拟交易"

Write-Host "=== 模拟交易输出完整性验证 ===" -ForegroundColor Cyan
Write-Host "日期: $Date`n"

$allPassed = $true

# 1. 验证 交易目录结构
$requiredDirs = @(
    "持仓记录", "日志", "绩效报告", "每日快照"
)
foreach ($dir in $requiredDirs) {
    $fullPath = Join-Path $tradingDir $dir
    if (Test-Path $fullPath) {
        Write-Host "  [PASS] 目录存在: $dir" -ForegroundColor Green
    } else {
        Write-Host "  [INFO] 目录不存在(首次运行?): $dir" -ForegroundColor Yellow
    }
}

# 2. 验证 transactions.csv
$csvFile = Join-Path $tradingDir "持仓记录/transactions.csv"
if (Test-Path $csvFile) {
    try {
        $rows = Import-Csv $csvFile -Encoding UTF8
        $rowCount = ($rows | Measure-Object).Count
        if ($rowCount -ge $MinTransactions) {
            Write-Host "  [PASS] transactions.csv: $rowCount 条记录" -ForegroundColor Green
        } else {
            Write-Host "  [WARN] transactions.csv: 仅 $rowCount 条记录 (阈值=$MinTransactions)" -ForegroundColor Yellow
        }
        $requiredCols = @("date", "code", "action", "price", "shares")
        $actualCols = ($rows[0].PSObject.Properties).Name
        $missingCols = $requiredCols | Where-Object { $_ -notin $actualCols }
        if ($missingCols.Count -eq 0) {
            Write-Host "  [PASS] transactions.csv 列完整" -ForegroundColor Green
        } else {
            Write-Host "  [FAIL] transactions.csv 缺少列: $($missingCols -join ",")" -ForegroundColor Red
            $allPassed = $false
        }
    } catch {
        Write-Host "  [FAIL] transactions.csv 无法解析: $_" -ForegroundColor Red
        $allPassed = $false
    }
} else {
    Write-Host "  [INFO] transactions.csv 不存在(尚未交易)" -ForegroundColor Yellow
}

# 3. 验证 positions.json
$posFile = Join-Path $tradingDir "持仓记录/positions.json"
if (Test-Path $posFile) {
    try {
        $pos = Get-Content $posFile -Raw -Encoding UTF8 | ConvertFrom-Json
        Write-Host "  [PASS] positions.json 可解析" -ForegroundColor Green
        if ($pos.Cash -ge 0) {
            Write-Host "  [PASS] positions.json Cash=$($pos.Cash)" -ForegroundColor Green
        } else {
            Write-Host "  [FAIL] positions.json Cash 异常: $($pos.Cash)" -ForegroundColor Red
            $allPassed = $false
        }
        $posCount = ($pos.Positions.PSObject.Properties | Where-Object { $_.Value.Shares -gt 0 } | Measure-Object).Count
        Write-Host "  [INFO] 当前持仓: $posCount 只" -ForegroundColor Gray
        if ($pos.TotalValue -and $pos.Cash -and $pos.Positions) {
            $calcTotal = [double]$pos.Cash
            foreach ($p in $pos.Positions.PSObject.Properties) {
                $calcTotal += [double]$p.Value.Shares * [double]$p.Value.CurrentPrice
            }
            $diff = [Math]::Abs($calcTotal - [double]$pos.TotalValue)
            if ($diff -lt 0.02) {
                Write-Host "  [PASS] positions.json 一致性: Cash+市值=$([Math]::Round($calcTotal,2)) = TotalValue=$([Math]::Round($pos.TotalValue,2))" -ForegroundColor Green
            } else {
                Write-Host "  [FAIL] positions.json 一致性: Cash+市值=$([Math]::Round($calcTotal,2)) != TotalValue=$([Math]::Round($pos.TotalValue,2)) (偏差$diff)" -ForegroundColor Red
                $allPassed = $false
            }
        }
    } catch {
        Write-Host "  [FAIL] positions.json 无法解析: $_" -ForegroundColor Red
        $allPassed = $false
    }
} else {
    Write-Host "  [INFO] positions.json 不存在" -ForegroundColor Yellow
}

# 4. 验证 当日快照
$snapFile = Join-Path $tradingDir "每日快照/snapshot_${Date}.json"
if (Test-Path $snapFile) {
    try {
        $snap = Get-Content $snapFile -Raw -Encoding UTF8 | ConvertFrom-Json
        Write-Host "  [PASS] 每日快照 $Date 可解析" -ForegroundColor Green
        if ($snap.TotalValue -and $snap.Cash -and $snap.StockDetails) {
            $calcTotal = [double]$snap.Cash
            $holdingsValue = 0
            foreach ($p in $snap.StockDetails) {
                $holdingsValue += [double]$p.Shares * [double]$p.CurrentPrice
            }
            $calcTotal += $holdingsValue
            $diff = [Math]::Abs($calcTotal - [double]$snap.TotalValue)
            if ($diff -lt 0.02) {
                Write-Host "  [PASS] 快照一致性: Cash+持仓=$([Math]::Round($calcTotal,2)) = TotalValue=$([Math]::Round($snap.TotalValue,2))" -ForegroundColor Green
            } else {
                Write-Host "  [FAIL] 快照一致性: Cash+持仓=$([Math]::Round($calcTotal,2)) != TotalValue=$([Math]::Round($snap.TotalValue,2)) (偏差$diff)" -ForegroundColor Red
                $allPassed = $false
            }
        }
        if ($snap.Date -eq $Date) {
            Write-Host "  [PASS] 快照日期一致: $($snap.Date)" -ForegroundColor Green
        } else {
            Write-Host "  [WARN] 快照日期 $($snap.Date) 与参数 $Date 不一致" -ForegroundColor Yellow
        }
    } catch {
        Write-Host "  [FAIL] 每日快照 $Date 无法解析: $_" -ForegroundColor Red
        $allPassed = $false
    }
} else {
    Write-Host "  [INFO] 每日快照 $Date 不存在" -ForegroundColor Yellow
}

# 5. 验证 perf_summary.json
$perfFile = Join-Path $tradingDir "绩效报告/perf_summary.json"
if (Test-Path $perfFile) {
    try {
        $perf = Get-Content $perfFile -Raw -Encoding UTF8 | ConvertFrom-Json
        Write-Host "  [PASS] perf_summary.json 可解析" -ForegroundColor Green
        if ($perf.InitialCapital -gt 0) {
            Write-Host "  [PASS] 初始资金: $($perf.InitialCapital)" -ForegroundColor Green
        }
        if ($perf.CurrentValue -gt 0) {
            Write-Host "  [PASS] 当前总值: $([Math]::Round($perf.CurrentValue,2))" -ForegroundColor Green
        }
        if ($null -ne $perf.TotalReturnPct) {
            Write-Host "  [PASS] 总收益率: $($perf.TotalReturnPct)%" -ForegroundColor Green
        }
    } catch {
        Write-Host "  [FAIL] perf_summary.json 无法解析: $_" -ForegroundColor Red
        $allPassed = $false
    }
} else {
    Write-Host "  [INFO] perf_summary.json 不存在(数据不足)" -ForegroundColor Yellow
}

# 6. 验证 当日日志
$logFile = Join-Path $tradingDir "日志/sim_${Date}.log"
if (Test-Path $logFile) {
    $logSize = (Get-Item $logFile).Length
    if ($logSize -gt 100) {
        Write-Host "  [PASS] 日志 $Date ($([Math]::Round($logSize/1KB,1)) KB)" -ForegroundColor Green
    } else {
        Write-Host "  [WARN] 日志 $Date 过小 ($logSize bytes)" -ForegroundColor Yellow
    }
} else {
    Write-Host "  [INFO] 日志 sim_${Date}.log 不存在" -ForegroundColor Yellow
}

# 7. 验证 跨文件一致性: snapshot vs positions
if ((Test-Path $snapFile) -and (Test-Path $posFile)) {
    try {
        $snap = Get-Content $snapFile -Raw -Encoding UTF8 | ConvertFrom-Json
        $pos = Get-Content $posFile -Raw -Encoding UTF8 | ConvertFrom-Json
        $snapTotal = [double]$snap.TotalValue
        $posTotal = [double]$pos.TotalValue
        $diff = [Math]::Abs($snapTotal - $posTotal)
        if ($diff -lt 0.02) {
            Write-Host "  [PASS] 跨文件一致: snapshot=$snapTotal = positions=$posTotal" -ForegroundColor Green
        } else {
            Write-Host "  [FAIL] 跨文件不一致: snapshot=$snapTotal != positions=$posTotal (偏差$diff)" -ForegroundColor Red
            $allPassed = $false
        }
    } catch {
        Write-Host "  [WARN] 跨文件一致性校验跳过: $_" -ForegroundColor Yellow
    }
}

# 汇总
Write-Host ""
if ($allPassed) {
    Write-Host "结果: 全部通过" -ForegroundColor Green
    exit 0
} else {
    Write-Host "结果: 存在失败项目" -ForegroundColor Red
    exit 1
}
