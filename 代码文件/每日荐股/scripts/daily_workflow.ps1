<#
.SYNOPSIS
  TieLv Daily Workflow Master Script
.DESCRIPTION
  Automated scheduling for TieLv Quantitative System.
  Mode daily       (Day N 20:00) -> Daily stock analysis with current whitepaper (manual first-run)
  Mode eval        (Day N+1 19:00) -> Post-evaluation -> report -> optimize whitepaper -> version update
  Mode daily_latest (Day N+1 20:00) -> Daily analysis with latest whitepaper (scheduled)
.PARAMETER Mode
  daily / eval / daily_latest
.PARAMETER Date
  Target date (yyyy-MM-dd). Default today. For testing.
.PARAMETER SkipMarketCheck
  Skip market open check (testing).
.PARAMETER LogOnly
  Log only, skip actual analysis (testing).
.EXAMPLE
  .\daily_workflow.ps1 -Mode daily
  .\daily_workflow.ps1 -Mode eval -Date "2026-05-22"
  .\daily_workflow.ps1 -Mode daily_latest -SkipMarketCheck
#>

param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("daily", "eval", "daily_latest")]
    [string]$Mode,
    [string]$Date = (Get-Date -Format "yyyy-MM-dd"),
    [switch]$SkipMarketCheck,
    [switch]$LogOnly
)

$rootDir = "C:\Users\34269\Documents\Claude\股票分析"
$dailyCodeDir = Join-Path $rootDir "代码文件\每日荐股"
$dailyDocDir = Join-Path $rootDir "每日荐股"
$scriptsDir = Join-Path $dailyCodeDir "scripts"
$evalDir = Join-Path $dailyDocDir "事后评估"
$logicDir = Join-Path $dailyCodeDir "分析逻辑"
$reportDir = Join-Path $dailyDocDir "股票报告"
$holidayFile = Join-Path $dailyDocDir "运营记录\holidays_2026.csv"
$marketCheckScript = Join-Path $dailyCodeDir "scripts\is_market_open.ps1"
$recordFile = Join-Path $dailyDocDir "运营记录\workflow_records.csv"
$archiveScript = Join-Path $dailyCodeDir "scripts\archive_data.ps1"

$logFile = Join-Path $scriptsDir ("workflow_" + (Get-Date -Format "yyyyMM") + ".log")

function Write-Log {
    param([string]$Msg, [string]$Level = "INFO")
    $time = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $line = "[" + $time + "][" + $Level + "] " + $Msg
    Add-Content -Path $logFile -Value $line -Encoding UTF8
    Write-Output $line
}

function Write-Record {
    param(
        [string]$Date,
        [string]$Mode,
        [string]$Status,
        [string]$ReportName = "",
        [string]$VersionBefore = "",
        [string]$VersionAfter = "",
        [string]$Notes = ""
    )
    $header = "Date,Mode,Status,ReportName,VersionBefore,VersionAfter,Notes"
    $line = "$Date,$Mode,$Status,$ReportName,$VersionBefore,$VersionAfter,$Notes"
    $exists = Test-Path $recordFile
    if (-not $exists) {
        Add-Content -Path $recordFile -Value $header -Encoding UTF8
    }
    Add-Content -Path $recordFile -Value $line -Encoding UTF8
}

# -- Market open check --
if (-not $SkipMarketCheck) {
    Write-Log -Msg ("Checking market open for " + $Date + "...")
    $result = & $marketCheckScript -Date $Date -HolidayFile $holidayFile
    if ($LASTEXITCODE -ne 0) {
        Write-Log -Msg ($Date + " is not a trading day, skip") -Level "SKIP"
        Write-Record -Date $Date -Mode $Mode -Status "SKIPPED" -Notes "Not a trading day"
        exit 0
    }
    Write-Log -Msg ($Date + " is a trading day, proceeding")
} else {
    Write-Log -Msg "Market check skipped (-SkipMarketCheck)"
}

# -- mode: eval (白皮书 v1.5) --
if ($Mode -eq "eval") {
    Write-Log -Msg "===== Starting Post-Evaluation (白皮书 v1.5) ====="
    # 白皮书 §1.3: N+1日19:00评估T日荐股
    $evalDate = (Get-Date $Date).AddDays(-1).ToString("yyyy-MM-dd")
    $reportDateStr = $evalDate -replace '-',''
    # 白皮书 §1.4: 评估报告_YYYYMMDD (YYYYMMDD=T日)
    $reportName = "评估报告_$reportDateStr"
    if ($LogOnly) {
        Write-Log -Msg "[LogOnly] Skipping actual evaluation"
    } else {
        # ---- §2 实际评估：调用 run_daily_eval.ps1（白皮书 v1.5） ----
        $evalScript = Join-Path $scriptsDir "run_daily_eval.ps1"
        Write-Log -Msg ("Running evaluation: " + $evalScript)
        # 传入 -ReportDate 参数确保报告命名使用T日日期
        & $evalScript -ReportDate $reportDateStr
        if ($LASTEXITCODE -ne 0) {
            Write-Log -Msg "Evaluation script failed (exit: $LASTEXITCODE)" -Level "ERROR"
        } else {
            Write-Log -Msg "Evaluation completed successfully"
        }

        # ---- 归档评估数据 ----
        Write-Log -Msg "Archiving evaluation data..."
        & $archiveScript -Date $Date

        # ---- 重点股票评估 ----
        Write-Log -Msg "Running keystock evaluation..."
        $keystockEvalScript = Join-Path $rootDir "代码文件\重点股票\次日评估\run_keystock_evaluation.ps1"
        & $keystockEvalScript
        if ($LASTEXITCODE -ne 0) {
            Write-Log -Msg "Keystock evaluation failed (exit: $LASTEXITCODE)" -Level "ERROR"
        } else {
            Write-Log -Msg "Keystock evaluation completed"
        }

        # ---- §5.2 自动优化触发（白皮书§7.1） ----
        Write-Log -Msg "[§5.2] Checking auto-optimization triggers..."
        # TODO: 读取评估产出（records.csv）判断是否需要自动优化
        # 触发条件：
        # - 胜率<60% → 审查评分逻辑
        # - 盈亏比<1.5 → 调整止损参数
        # - 评分区分度<15% → 维度审查
        # - 某维度误判率>20%连续3日 → 维度重构
        # 当前为占位，待records.csv积累≥5日数据后启用
        Write-Log -Msg "[§5.2] Auto-optimization check complete (placeholder - needs ≥5 days data)"

        # ---- §5.2 版本升级检测 ----
        Write-Log -Msg "[§5.2] Checking version update requirements..."
        # TODO: 根据评估结果判断是否需要版本升级
        # 当前为占位
        Write-Log -Msg "[§5.2] Version check complete (placeholder)"

        # ---- 更新CHANGELOG ----
        $changelogFile = Join-Path $rootDir "每日荐股\事后评估\次日后评估白皮书_CHANGELOG.md"
        if (Test-Path $changelogFile) {
            $changelogEntry = "`n### $Date 评估执行`n- 执行模式：$Mode`n- 评估报告：$reportName`n- 评估结果：详见报告"
            Add-Content -Path $changelogFile -Value $changelogEntry -Encoding UTF8
            Write-Log -Msg "CHANGELOG updated: $changelogFile"
        }
    }
    Write-Log -Msg "Evaluation completed (白皮书 v1.5)"
    Write-Record -Date $Date -Mode $Mode -Status "SUCCESS" -ReportName $reportName -Notes "Evaluation v1.5 done"
    Write-Log -Msg "===== Post-Evaluation Complete ====="
}

# -- mode: daily / daily_latest --
if ($Mode -eq "daily" -or $Mode -eq "daily_latest") {
    $versionLabel = "latest"
    if ($Mode -eq "daily") { $versionLabel = "current" }
    Write-Log -Msg ("===== Starting Daily Stock Analysis (" + $versionLabel + " version) =====")
    $reportLabel = "daily_report_" + ($Date -replace '-','')
    $reportPath = Join-Path $reportDir ($reportLabel + ".html")
    $genScript = Join-Path $scriptsDir "..\分析逻辑\gen_daily_html.ps1"
    if ($LogOnly) {
        Write-Log -Msg "[LogOnly] Skipping analysis"
    } else {
        # ---- Phase 1: Build dynamic pool ----
        Write-Log -Msg "[1/6] Building dynamic pool..."
        $poolScript = Join-Path $scriptsDir "build_dynamic_pool.ps1"
        & $poolScript
        if ($LASTEXITCODE -ne 0) {
            Write-Log -Msg "Dynamic pool build failed (exit: $LASTEXITCODE)" -Level "ERROR"
        } else {
            Write-Log -Msg "Dynamic pool built successfully"
        }

        # ---- Phase 2: Batch data collection ----
        Write-Log -Msg "[2/6] Collecting batch data..."
        $collectScript = Join-Path $scriptsDir "batch_data_collector.ps1"
        & $collectScript
        if ($LASTEXITCODE -ne 0) {
            Write-Log -Msg "Data collection failed (exit: $LASTEXITCODE)" -Level "ERROR"
        } else {
            Write-Log -Msg "Data collection completed"
        }

        # ---- Phase 3: Scoring engine v2 (veto + score) ----
        Write-Log -Msg "[3/6] Running scoring engine..."
        $scoringScript = Join-Path $logicDir "scoring_engine_v2.py"
        python $scoringScript 2>&1 | ForEach-Object { Write-Log -Msg $_ }
        if ($LASTEXITCODE -ne 0) {
            Write-Log -Msg "Scoring engine failed (exit: $LASTEXITCODE)" -Level "ERROR"
        } else {
            Write-Log -Msg "Scoring completed"
        }

        # ---- Phase 4: Generate report ----
        Write-Log -Msg "[4/6] Generating report..."
        Write-Log -Msg ("Generating report via: " + $genScript)
        & $genScript -Date $Date -SkipPdf:$($Mode -eq "daily_latest" -or $reportAsHtml)
        if ($LASTEXITCODE -ne 0) {
            Write-Log -Msg "Report generation failed (exit code: $LASTEXITCODE)" -Level "ERROR"
        } else {
            Write-Log -Msg "Report generated successfully"
        }
        # ---- Phase 5: Key stock analysis ----
        Write-Log -Msg "[5/6] Running keystock analysis..."
        $keystockScript = Join-Path $rootDir "代码文件\重点股票\run_keystock_analysis.ps1"
        & $keystockScript -Date $Date
        if ($LASTEXITCODE -ne 0) {
            Write-Log -Msg "Keystock analysis failed (exit: $LASTEXITCODE)" -Level "ERROR"
        } else {
            Write-Log -Msg "Keystock analysis completed"
        }

        # ---- Phase 6: Archive data ----
        Write-Log -Msg "[6/6] Archiving daily data..."
        & $archiveScript -Date $Date
        if ($LASTEXITCODE -ne 0) {
            Write-Log -Msg "Archive step failed (exit: $LASTEXITCODE)" -Level "ERROR"
        } else {
            Write-Log -Msg "Data archived successfully"
        }

        # ---- Phase 7: 模拟交易引擎 ----
        Write-Host "`n[Phase 7] 启动模拟交易引擎..." -ForegroundColor Cyan
        $simTradingScript = Join-Path $rootDir "模拟交易/交易引擎/sim_trading.ps1"
        $evalDateStr = $Date -replace '-',''
        $evalFile = Join-Path $rootDir "重点股票/次日评估/评估数据_${evalDateStr}.json"
        if (Test-Path $evalFile) {
            & $simTradingScript -Date $evalDateStr -DataFile $evalFile -DryRun  # 安全模式：如需实盘去除 -DryRun
            if ($LASTEXITCODE -eq 0) {
                Write-Host "[Phase 7] 模拟交易引擎完成" -ForegroundColor Green
            } else {
                Write-Warning "[Phase 7] 模拟交易引擎返回非零退出码"
            }
        } else {
            Write-Warning "[Phase 7] 评估数据不存在: $evalFile，跳过模拟交易"
        }
    }
    Write-Record -Date $Date -Mode $Mode -Status "SUCCESS" -Notes ("Analysis done, output: " + $reportDir)
    Write-Log -Msg "===== Daily Stock Analysis Complete ====="
}

Write-Log -Msg "Execution Summary:"
Write-Log -Msg ("  Mode:   " + $Mode)
Write-Log -Msg ("  Date:   " + $Date)
Write-Log -Msg ("  Log:    " + $logFile)
Write-Log -Msg ("  Record: " + $recordFile)