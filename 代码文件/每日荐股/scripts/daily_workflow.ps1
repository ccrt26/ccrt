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
. "$PSScriptRoot/../../lib/init_encoding.ps1"

$rootDir = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
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
    Write-Log -Msg "===== Starting Post-Evaluation (白皮书 v1.7, 分析逻辑 v3.1) ====="
    # 白皮书 §1.3: N+1日19:00评估最近交易日荐股
    # Find the most recent trading day (handles weekends/holidays)
    $evalDate = $Date
    do {
        $evalDate = (Get-Date $evalDate).AddDays(-1).ToString("yyyy-MM-dd")
        & $marketCheckScript -Date $evalDate -HolidayFile $holidayFile 2>&1 | Out-Null
        $isTrading = ($LASTEXITCODE -eq 0)
        if ((Get-Date $evalDate) -lt (Get-Date).AddDays(-30)) {
            Write-Log -Msg "Cannot find recent trading day within 30 days" -Level "ERROR"
            throw "No recent trading day found"
        }
    } while (-not $isTrading)
    Write-Log -Msg ("Eval target date: " + $evalDate + " (most recent trading day)")
    $reportDateStr = $evalDate -replace '-',''
    # 白皮书 §1.4: 评估报告_YYYYMMDD (YYYYMMDD=T日)
    $reportName = "每日荐股后评估报告_$reportDateStr"
    if ($LogOnly) {
        Write-Log -Msg "[LogOnly] Skipping actual evaluation"
    } else {
        # ---- Pre-eval: Backfill historical returns ----
        Write-Log -Msg "[Pre-eval] Backfilling historical returns..."
        $backfillScript = Join-Path $scriptsDir "backfill_returns.py"
        if (Test-Path $backfillScript) {
            $backfillResult = & python $backfillScript 2>&1
            Write-Log -Msg "[Pre-eval] Backfill complete: $backfillResult"
        } else {
            Write-Log -Msg "[Pre-eval] Backfill script not found, skipping" -Level "WARN"
        }

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
        Write-Log -Msg "情墨iving evaluation data..."
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

        # ---- §6.8 桥接联动检测（后评估→分析逻辑白皮书） ----
        Write-Log -Msg "[§6.8] Bridge detection integrated in run_keystock_evaluation.ps1 (v1.7)"
        # 桥接检测在 run_keystock_evaluation.ps1 内部自动执行
        # B1-B8 触发条件由白皮书 §6.8.2 定义，输出到 逻辑积累\联动日志\分析逻辑联动建议.json
        # 待数据积累 ≥ 20 条后，桥接建议可进入自动采纳流程（需腰子确认）

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
        # ---- Phase 0: Health Check (pre-flight) ----
        Write-Log -Msg "[0/7] Backfill pre-warming..."
        $backfillScript = Join-Path $scriptsDir "backfill_returns.py"
        if (Test-Path $backfillScript) {
            $null = & python $backfillScript 2>&1
            Write-Log -Msg "[0/7] Backfill pre-warming complete"
        }
        Write-Log -Msg "[0/7] Running pre-flight health check..."
        $healthScript = Join-Path $rootDir "代码文件\tools\health_check.ps1"
        $dataFullPath = Join-Path $rootDir "代码文件\数据\data_full.json"
        if (Test-Path $healthScript) {
            $healthResult = & $healthScript -Mode daily_sim -DataFile $dataFullPath -RootDir $rootDir 2>&1
            try {
                $healthJson = $healthResult | Select-Object -Last 1 | ConvertFrom-Json
                if ($healthJson.Flag -eq "blocked" -or $healthJson.AlertLevel -eq "L3") {
                    Write-Log -Msg "[HEALTH] L3 BLOCKED — 数据健康检测不通过, 停止全部下游流水线" -Level "ERROR"
                    Write-Log -Msg "[HEALTH] $($healthJson.Messages -join '; ')"
                    Write-Record -Date $Date -Mode $Mode -Status "BLOCKED" -Notes "Health check L3: $($healthJson.Flag)"
                    exit 1
                }
                Write-Log -Msg "[HEALTH] Pre-flight PASSED (Level: $($healthJson.AlertLevel), Flag: $($healthJson.Flag))"
            } catch {
                Write-Log -Msg "[HEALTH] Health check parse error, proceeding with caution: $_" -Level "WARN"
            }
        } else {
            Write-Log -Msg "[HEALTH] Health check script not found, skipping" -Level "WARN"
        }

        # ---- Phase 1: Build dynamic pool ----
        Write-Log -Msg "[1/7] Building dynamic pool..."
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

        # ---- Quality Gate QC-1: Post-Collection Data Check (max 3 retries) ----
        $maxRetries = 3
        $retryCount = 0
        $qc1Passed = $false
        do {
            $retryCount++
            Write-Log -Msg "[QC-1] Running data quality check after collection (attempt $retryCount/$maxRetries)..."
            $qcScript = Join-Path $rootDir "代码文件\tools\check_data_quality.ps1"
            $dataFullPath = Join-Path $rootDir "代码文件\数据\data_full.json"
            $qcResult1 = & $qcScript -Mode daily_sim -DataFile $dataFullPath -RootDir $rootDir 2>&1
            try {
                $qcJson1 = $qcResult1 | ConvertFrom-Json
                if (-not $qcJson1.Passed -or $qcJson1.Flag -eq "cached") {
                    Write-Log -Msg "[QC-1] DATA QUALITY FAILED (Flag: $($qcJson1.Flag), Passed: $($qcJson1.Passed))" -Level "ERROR"
                    Write-Log -Msg "[QC-1] Degraded: $($qcJson1.DegradedFields -join ', '); Cached: $($qcJson1.CachedFields -join ', ')"
                    if ($retryCount -ge $maxRetries) {
                        Write-Log -Msg "[QC-1] FAILED after $maxRetries retries, ABORTING" -Level "ERROR"
                        Write-Record -Date $Date -Mode $Mode -Status "FAILED" -Notes "QC-1: data quality gate failed after $maxRetries retries (Flag: $($qcJson1.Flag))"
                        # Generate health alert HTML
                        $alertHtml = Join-Path $rootDir "临时报告\health_alert_$($Date -replace '-','').html"
                        & $healthScript -Mode daily_sim -DataFile $dataFullPath -OutputHtml $alertHtml -RootDir $rootDir 2>&1 | Out-Null
                        exit 1
                    }
                    Write-Log -Msg "[QC-1] Retrying in 30s..." -Level "WARN"
                    Start-Sleep -Seconds 30
                    # Re-collect data before retry
                    Write-Log -Msg "[QC-1] Re-collecting data before retry..."
                    & $collectScript 2>&1 | Out-Null
                } else {
                    $qc1Passed = $true
                    Write-Log -Msg "[QC-1] Data quality check PASSED (Flag: $($qcJson1.Flag))"
                }
            } catch {
                Write-Log -Msg "[QC-1] Quality check script error: $_" -Level "ERROR"
                if ($retryCount -ge $maxRetries) {
                    Write-Record -Date $Date -Mode $Mode -Status "FAILED" -Notes "QC-1: quality check script crashed after $maxRetries retries"
                    exit 1
                }
                Write-Log -Msg "[QC-1] Retrying in 30s..." -Level "WARN"
                Start-Sleep -Seconds 30
            }
        } while (-not $qc1Passed -and $retryCount -lt $maxRetries)
        Write-Log -Msg "[3/7] Running scoring engine v2.9..."
        $scoringScript = Join-Path $logicDir "scoring_engine_v2.py"
        python $scoringScript --date $Date 2>&1 | ForEach-Object { Write-Log -Msg $_ }
        if ($LASTEXITCODE -ne 0) {
            Write-Log -Msg "Scoring engine failed (exit: $LASTEXITCODE)" -Level "ERROR"
        } else {
            Write-Log -Msg "Scoring completed"
        }

        # ---- Phase 3.5: Backfill returns (v2.9 路线二 阶段A) ----
        Write-Log -Msg "[3.5/7] Backfilling historical returns..."
        $backfillScript = Join-Path $scriptsDir "backfill_returns.py"
        $backfillResult = & python $backfillScript 2>&1
        Write-Log -Msg ("Backfill: " + ($backfillResult -join "; "))
        Write-Host "[Phase 3.5] 收益回填完成" -ForegroundColor Cyan

        # ---- Quality Gate QC-2: Post-Scoring Data Check ----
        Write-Log -Msg "[QC-2] Running data quality check after scoring..."
        $scoredPath = Join-Path $rootDir "代码文件\数据\data_scored.json"
        $qcResult2 = & $qcScript -Mode daily_sim -DataFile $scoredPath -RootDir $rootDir 2>&1
        try {
            $qcJson2 = $qcResult2 | ConvertFrom-Json
            if (-not $qcJson2.Passed) {
                Write-Log -Msg "[QC-2] SCORED DATA QUALITY FAILED (Flag: $($qcJson2.Flag))" -Level "ERROR"
                Write-Log -Msg "[QC-2] Degraded: $($qcJson2.DegradedFields -join ', '); Cached: $($qcJson2.CachedFields -join ', ')"
                Write-Record -Date $Date -Mode $Mode -Status "FAILED" -Notes "QC-2: scored data quality gate failed"
                exit 1
            }
            Write-Log -Msg "[QC-2] Scored data quality check PASSED (Flag: $($qcJson2.Flag))"
        } catch {
            Write-Log -Msg "[QC-2] Quality check script error: $_" -Level "ERROR"
            Write-Record -Date $Date -Mode $Mode -Status "FAILED" -Notes "QC-2: quality check script crashed"
            exit 1
        }

        # ---- Phase 4: Generate report ----
        Write-Log -Msg "[4/7] Generating report..."
        Write-Log -Msg ("Generating report via: " + $genScript)
        & $genScript -Date $Date -SkipPdf:$($Mode -eq "daily_latest" -or $reportAsHtml)
        if ($LASTEXITCODE -ne 0) {
            Write-Log -Msg "Report generation failed (exit code: $LASTEXITCODE)" -Level "ERROR"
        } else {
            Write-Log -Msg "Report generated successfully"
        }
        # ---- Phase 5: Key stock analysis ----
        Write-Log -Msg "[5/7] Running keystock analysis..."
        $keystockScript = Join-Path $rootDir "代码文件\重点股票\run_keystock_analysis.ps1"
        & $keystockScript -Date $Date
        if ($LASTEXITCODE -ne 0) {
            Write-Log -Msg "Keystock analysis failed (exit: $LASTEXITCODE)" -Level "ERROR"
        } else {
            Write-Log -Msg "Keystock analysis completed"
        }

        # ---- Phase 6: Archive data ----
        Write-Log -Msg "[6/7] 情墨iving daily data..."
        & $archiveScript -Date $Date
        if ($LASTEXITCODE -ne 0) {
            Write-Log -Msg "Archive step failed (exit: $LASTEXITCODE)" -Level "ERROR"
        } else {
            Write-Log -Msg "Data archived successfully"
        }

        # ---- Phase 7: 模拟交易引擎 ----
        Write-Host "`n[Phase 7/7] 启动模拟交易引擎..." -ForegroundColor Cyan
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

        # ---- Phase 7.5: 每日荐股模拟交易引擎 ----
        Write-Host "`n[Phase 7.5/7] 启动每日荐股模拟交易引擎..." -ForegroundColor Cyan
        $simDailyScript = Join-Path $rootDir "模拟交易/每日荐股赛道/交易引擎/sim_trading_daily.ps1"
        $scoredFile = Join-Path $rootDir "代码文件/数据/data_scored.json"
        if (Test-Path $scoredFile) {
            $evalDateStr = $Date -replace '-',''
            & $simDailyScript -Date $evalDateStr -DataFile $scoredFile -DryRun
            if ($LASTEXITCODE -eq 0) {
                Write-Host "[Phase 7.5] 每日荐股模拟交易引擎完成" -ForegroundColor Green
            } else {
                Write-Warning "[Phase 7.5] 每日荐股模拟交易引擎返回非零退出码"
            }
        } else {
            Write-Warning "[Phase 7.5] data_scored.json 不存在: $scoredFile，跳过每日荐股模拟交易"
        }

        # ---- Phase 7.6: 综合审计 (旧影 审计官) ----
        Write-Host "`n[Phase 7.6/7] 综合审计..." -ForegroundColor Cyan
        $auditScript = Join-Path $rootDir "代码文件\监督机制\run_full_audit.ps1"
        if (Test-Path $auditScript) {
            & $auditScript -Quick -Date $Date 2>&1 | ForEach-Object { Write-Log -Msg $_ }
            if ($LASTEXITCODE -ne 0) {
                Write-Log -Msg "审计发现需关注问题 (exit: $LASTEXITCODE)" -Level "WARN"
            } else {
                Write-Log -Msg "审计通过"
            }
        } else {
            Write-Log -Msg "审计脚本不存在，跳过" -Level "WARN"
        }
    Write-Record -Date $Date -Mode $Mode -Status "SUCCESS" -Notes ("Analysis done, output: " + $reportDir)
    Write-Log -Msg "===== Daily Stock Analysis Complete ====="
    }
}

# Auto-commit: daily_pick outputs (covers reports, scored data, pool data)
$gitAuto = Join-Path $rootDir "代码文件\tools\git_autocommit.ps1"
if (Test-Path $gitAuto) {
    $reportParent = Split-Path $reportDir -Parent
    $null = & $gitAuto -Module "daily_pick" -Paths @($reportParent, "历史数据\") -Message "每日荐股全流程产出"
}

# Auto-commit: engineering sweep (catch-all for any remaining uncommitted changes)
$gitSweep = Join-Path $rootDir "代码文件\tools\git_sweep.ps1"
if (Test-Path $gitSweep) {
    $null = & $gitSweep
}

Write-Log -Msg "Execution Summary:"
Write-Log -Msg ("  Mode:   " + $Mode)
Write-Log -Msg ("  Date:   " + $Date)
Write-Log -Msg ("  Log:    " + $logFile)
Write-Log -Msg ("  Record: " + $recordFile)
