. "$PSScriptRoot/../../lib/init_encoding.ps1"
# 依赖: dot-source "$PSScriptRoot/audit_core.ps1"
# $rootDir, helper functions, and script: variables are inherited from audit_core.ps1

# ============================================================
# Section A: 数据完整性 (每日)
# ============================================================
Write-Host "── Section A: 数据完整性 ──" -ForegroundColor Cyan

# A-1: 跨文件交易一致性
$txnFile = Join-Path $rootDir "模拟交易\持仓记录\transactions.csv"
$posFile = Join-Path $rootDir "模拟交易\持仓记录\positions.json"
if ((Test-Path $txnFile) -and (Test-Path $posFile)) {
    try {
        $txn = Import-Csv $txnFile -Encoding UTF8
        $posObj = Get-Content $posFile -Raw -Encoding UTF8 | ConvertFrom-Json
        $posList = @($posObj.Positions.PSObject.Properties | ForEach-Object { $_.Value })
        $txnCodes = @($txn | Select-Object -ExpandProperty Code -Unique | Sort-Object)
        $posCodes = @($posList | Where-Object { $_.Shares -gt 0 } | Select-Object -ExpandProperty Code | Sort-Object)
        $diff = Compare-Object $txnCodes $posCodes
        if ($diff.Count -eq 0) {
            Add-Check 'A' '1' '跨文件交易一致性' 'PASS' "交易记录与持仓$($txnCodes.Count)只股票一致"
        } else {
            Add-Check 'A' '1' '跨文件交易一致性' 'FAIL' "不一致: $(($diff | ForEach-Object { $_.InputObject }) -join ', ')"
        }
    } catch {
        Add-Check 'A' '1' '跨文件交易一致性' 'WARN' "无法解析: $_"
    }
} else {
    Add-Check 'A' '1' '跨文件交易一致性' 'WARN' "文件不存在"
}

# A-3: 数据新鲜度
$keyDataFiles = @("$dataDir\data_final.json", "$dataDir\data_scored.json", "$dataDir\dynamic_pool.json")
$staleCount = 0
foreach ($f in $keyDataFiles) {
    if (-not (Test-FileFreshness $f 48)) { $staleCount++ }
}
if ($staleCount -eq 0) { Add-Check 'A' '3' '数据新鲜度' 'PASS' "关键数据文件均在48h内更新" }
elseif ($staleCount -le 1) { Add-Check 'A' '3' '数据新鲜度' 'WARN' "$staleCount 个文件过期" }
else { Add-Check 'A' '3' '数据新鲜度' 'FAIL' "$staleCount 个文件过期超过48h" }

# A-5: 交易记录幂等性
if (Test-Path $txnFile) {
    $lines = Get-Content $txnFile -Encoding UTF8
    $dataLines = $lines | Select-Object -Skip 1 | Where-Object { $_.Trim() -ne '' }
    $dupes = $dataLines | Group-Object { $_ } | Where-Object { $_.Count -gt 1 }
    if ($dupes.Count -eq 0) { Add-Check 'A' '5' '交易记录幂等性' 'PASS' "无重复行" }
    else { Add-Check 'A' '5' '交易记录幂等性' 'FAIL' "$($dupes.Count) 组重复行" }
} else {
    Add-Check 'A' '5' '交易记录幂等性' 'WARN' "transactions.csv 不存在"
}

# A-7: API降级频率 (扫描workflow日志)
$workflowLog = Join-Path $scriptsDir ("workflow_" + (Get-Date -Format "yyyyMM") + ".log")
if (Test-Path $workflowLog) {
    $logContent = Get-Content $workflowLog -Encoding UTF8 -Tail 500
    $totalOps = ($logContent | Select-String -Pattern "\[").Count
    $degradedB = ($logContent | Select-String -Pattern "\[B\]").Count
    $degradedC = ($logContent | Select-String -Pattern "\[C\]").Count
    if ($totalOps -gt 0) {
        $degradeRate = [math]::Round(($degradedB + $degradedC) / [Math]::Max($totalOps, 1) * 100, 1)
        if ($degradeRate -lt 5) { Add-Check 'A' '7' 'API降级频率' 'PASS' "降级率 ${degradeRate}%" }
        elseif ($degradeRate -lt 15) { Add-Check 'A' '7' 'API降级频率' 'WARN' "降级率 ${degradeRate}%" }
        else { Add-Check 'A' '7' 'API降级频率' 'FAIL' "降级率 ${degradeRate}%" }
    } else { Add-Check 'A' '7' 'API降级频率' 'WARN' "无操作记录" }
} else {
    Add-Check 'A' '7' 'API降级频率' 'WARN' "日志文件不存在"
}

# A-8: 独有源数据标注 (抽查最新HTML报告)
$reportDir = Join-Path $rootDir "每日荐股\股票报告"
$latestHtml = Get-ChildItem $reportDir -Filter "daily_report_*.html" -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if ($latestHtml) {
    $html = Get-Content $latestHtml.FullName -Raw -Encoding UTF8
    $hasDisclaimer = $html -match "仅供参考|免责声明"
    if ($hasDisclaimer) { Add-Check 'A' '8' '报告免责声明' 'PASS' "$($latestHtml.Name) 含免责声明" }
    else { Add-Check 'A' '8' '报告免责声明' 'FAIL' "$($latestHtml.Name) 缺少免责声明" }
} else {
    Add-Check 'A' '8' '报告免责声明' 'WARN' "无HTML报告可检查"
}

# ============================================================
# Section B: 缓存健康 (每周)
# ============================================================
if (-not $Quick) {
Write-Host "── Section B: 缓存健康 ──" -ForegroundColor Cyan

$cacheDir = Join-Path $rootDir "代码文件\每日荐股\data_cache"
if (Test-Path $cacheDir) {
    # B-1: 缓存文件清单
    $cacheFiles = Get-ChildItem $cacheDir -File -ErrorAction SilentlyContinue
    $byType = $cacheFiles | Group-Object { ($_.Name -split '_')[0] }
    $typeSummary = ($byType | ForEach-Object { "$($_.Name):$($_.Count)" }) -join ', '
    $totalCache = $cacheFiles.Count
    Add-Check 'B' '1' '缓存文件清单' 'PASS' "$totalCache 文件, $typeSummary"

    # B-2: 缓存年龄分布（周末/非交易日放宽阈值）
    $now = Get-Date
    $dow = [int]$now.DayOfWeek  # 0=Sun, 6=Sat
    $isWeekend = ($dow -eq 0 -or $dow -eq 6)
    if ($isWeekend) {
        # 周末：最近交易日可能在周五，放宽至72h
        $freshH = 72; $warmH = 96
    } else {
        $freshH = 24; $warmH = 48
    }
    $fresh = ($cacheFiles | Where-Object { ($now - $_.LastWriteTime).TotalHours -lt $freshH }).Count
    $warm = ($cacheFiles | Where-Object { $h = ($now - $_.LastWriteTime).TotalHours; $h -ge $freshH -and $h -lt $warmH }).Count
    $cold = ($cacheFiles | Where-Object { ($now - $_.LastWriteTime).TotalHours -ge $warmH }).Count
    $freshRate = [math]::Round($fresh / [Math]::Max($totalCache, 1) * 100, 1)
    if ($freshRate -gt 70) { Add-Check 'B' '2' '缓存新鲜度' 'PASS' "新鲜率 ${freshRate}% (fresh:$fresh warm:$warm cold:$cold)" }
    elseif ($freshRate -gt 50) { Add-Check 'B' '2' '缓存新鲜度' 'WARN' "新鲜率 ${freshRate}% (${freshH}h窗口)" }
    else { Add-Check 'B' '2' '缓存新鲜度' 'WARN' "新鲜率 ${freshRate}% — $(if($isWeekend){'周末，数据未更新属正常'})" }

    # B-3: 空缓存子目录
    $subdirs = Get-ChildItem $cacheDir -Directory -ErrorAction SilentlyContinue
    $empties = ($subdirs | Where-Object { (Get-ChildItem $_.FullName -File -ErrorAction SilentlyContinue).Count -eq 0 }).Count
    if ($empties -eq 0) { Add-Check 'B' '3' '空缓存目录' 'PASS' "无空目录" }
    elseif ($empties -le 2) { Add-Check 'B' '3' '空缓存目录' 'WARN' "$empties 个空目录" }
    else { Add-Check 'B' '3' '空缓存目录' 'FAIL' "$empties 个空目录" }

    # B-4: 缓存大小异常
    $tinyFiles = ($cacheFiles | Where-Object { $_.Length -lt 100 }).Count
    $hugeFiles = ($cacheFiles | Where-Object { $_.Length -gt 10MB }).Count
    if ($tinyFiles -eq 0 -and $hugeFiles -eq 0) { Add-Check 'B' '4' '缓存文件大小' 'PASS' "无异常大小文件" }
    elseif ($tinyFiles -le 5) { Add-Check 'B' '4' '缓存文件大小' 'WARN' "$tinyFiles 个<100B, $hugeFiles 个>10MB" }
    else { Add-Check 'B' '4' '缓存文件大小' 'FAIL' "$tinyFiles 个异常小文件" }
} else {
    Add-Check 'B' '1' '缓存目录' 'FAIL' "data_cache 目录不存在"
}

# ============================================================
# Section C: 编码健康 (每周)
# ============================================================
Write-Host "── Section C: 编码健康 ──" -ForegroundColor Cyan

# C-4: .Count 模式检测 (最高优先级)
$ps1Files = Get-ChildItem $rootDir -Recurse -Filter "*.ps1" -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -notmatch "\.git" }
$countViolations = @()
foreach ($f in $ps1Files) {
    $content = Get-Content $f.FullName -Raw -ErrorAction SilentlyContinue
    if ($content -match '\$(\w+)\.Count\b' -and $content -notmatch '@\(\$(\w+)\)\.Count') {
        $matches = [regex]::Matches($content, '(?<!\@\()\$(\w+)\.Count')
        foreach ($m in $matches) {
            $line = (1 + ($content.Substring(0, $m.Index).ToCharArray() | Where-Object { $_ -eq "`n" }).Count)
            $countViolations += "$($f.Name):$line `$$($m.Groups[1].Value).Count"
        }
    }
}
$countViolations = $countViolations | Select-Object -Unique
if ($countViolations.Count -eq 0) { Add-Check 'C' '4' '.Count 模式 (防误判)' 'PASS' "全部使用 @() 包裹" }
elseif ($countViolations.Count -le 50) { Add-Check 'C' '4' '.Count 模式 (防误判)' 'WARN' "$($countViolations.Count) 处裸 .Count（数组变量上安全，关注函数返回值上的使用）" }
else { Add-Check 'C' '4' '.Count 模式 (防误判)' 'WARN' "$($countViolations.Count) 处裸 .Count — 超过50，建议逐步用 @() 包裹高风险调用" }

# C-1: UTF-8 有效性 (抽样检查)
$sampleFiles = @($ps1Files | Select-Object -First 10)
$utf8Errors = 0
foreach ($f in $sampleFiles) {
    if (-not (Test-UTF8Validity $f.FullName)) { $utf8Errors++ }
}
if ($utf8Errors -eq 0) { Add-Check 'C' '1' 'UTF-8 编码有效性' 'PASS' "抽样10个PS1全部有效" }
else { Add-Check 'C' '1' 'UTF-8 编码有效性' 'FAIL' "$utf8Errors 个文件编码异常" }

# C-6: JSON 格式有效性
$jsonFiles = @(
    "$dataDir\data_final.json", "$dataDir\data_scored.json",
    "$dataDir\dynamic_pool.json", "$dataDir\sector_data.json"
)
$jsonErrors = 0
foreach ($jf in $jsonFiles) {
    if (Test-Path $jf) {
        try { $null = Get-Content $jf -Raw -Encoding UTF8 | ConvertFrom-Json }
        catch { $jsonErrors++; Add-Check 'C' '6' 'JSON格式' 'WARN' "$(Split-Path $jf -Leaf) 解析异常" }
    }
}
if ($jsonErrors -eq 0) { Add-Check 'C' '6' 'JSON格式有效性' 'PASS' "全部可解析" }
else { Add-Check 'C' '6' 'JSON格式有效性' 'FAIL' "$jsonErrors 个JSON解析失败" }

# ============================================================
# Section D: Schema完整性 (每日)
# ============================================================
Write-Host "── Section D: Schema完整性 ──" -ForegroundColor Cyan

# D-1: v3.0字段存在性
$evalFiles = Get-ChildItem (Join-Path $rootDir "重点股票\次日评估") -Filter "评估数据_*.json" -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1
if ($evalFiles) {
    try {
        $evalData = Get-Content $evalFiles.FullName -Raw -Encoding UTF8 | ConvertFrom-Json
        $v30fields = @("ADX_Value", "ADX_Trend", "OBV_Trend", "Wyckoff_Phase")
        # 评估数据JSON结构: {Date, Stocks: [{Signals: {...}}]} — 需进入.Stocks数组
        $stocks = if ($evalData.Stocks) { @($evalData.Stocks) }
                  elseif ($evalData -is [array]) { $evalData }
                  else { @() }
        $missingFields = @()
        $fieldsExist = $false  # 字段是否作为属性存在(管道生成了v3.0字段)
        foreach ($stock in $stocks) {
            if (-not $stock.Signals) { continue }
            foreach ($f in $v30fields) {
                $prop = $stock.Signals.PSObject.Properties[$f]
                if ($null -ne $prop) {
                    $fieldsExist = $true
                    # ADX_Value可为0(趋势不明时)，用$null检查而非falsy检查
                    if ($null -eq $prop.Value -or $prop.Value -eq '') {
                        $missingFields += "$($stock.Code)_$f"
                    }
                }
            }
        }
        if ($fieldsExist -and $missingFields.Count -eq 0) {
            Add-Check 'D' '1' 'v3.0字段完整性' 'PASS' "ADX/OBV/Wyckoff 全部存在"
        } elseif ($fieldsExist) {
            Add-Check 'D' '1' 'v3.0字段完整性' 'WARN' "部分字段未填充: $($missingFields -join ', ')"
        } else {
            Add-Check 'D' '1' 'v3.0字段完整性' 'WARN' "v3.0字段未生成(可能使用旧版分析管道，非数据问题)"
        }
    } catch {
        Add-Check 'D' '1' 'v3.0字段完整性' 'WARN' "无法解析评估数据"
    }
} else {
    Add-Check 'D' '1' 'v3.0字段完整性' 'WARN' "无评估数据文件"
}

# D-3: PE(TTM)计算路径 (搜索评分脚本)
$scoringScript = Join-Path $rootDir "代码文件\每日荐股\分析逻辑\scoring_engine_v2.py"
if (Test-Path $scoringScript) {
    $pyContent = Get-Content $scoringScript -Raw -Encoding UTF8
    $usesTTM = $pyContent -match "TTM_EPS|ttm_eps|pe_ttm"
    $usesStaticPE = $pyContent -match "static_pe|静态PE|pe_static"
    if ($usesTTM) { Add-Check 'D' '3' 'PE(TTM)计算路径' 'PASS' "使用TTM_EPS计算PE(TTM)" }
    elseif ($usesStaticPE) { Add-Check 'D' '3' 'PE(TTM)计算路径' 'FAIL' "检测到静态PE引用" }
    else { Add-Check 'D' '3' 'PE(TTM)计算路径' 'WARN' "未检测到PE计算" }
}

# D-4: Schema版本一致性 (P2-4)
$keyDataFiles = @(
    @{Path="代码文件\数据\data_scored.json"; Name="data_scored"},
    @{Path="代码文件\数据\data_final.json"; Name="data_final"},
    @{Path="代码文件\数据\dynamic_pool.json"; Name="dynamic_pool"}
)
$schemaVersions = @{}
foreach ($df in $keyDataFiles) {
    $dfFull = Join-Path $rootDir $df.Path
    if (Test-Path $dfFull) {
        try {
            $content = Get-Content $dfFull -Raw -Encoding UTF8 | ConvertFrom-Json
            $ver = if ($content._schema_version) { $content._schema_version } else { "缺失" }
            $schemaVersions[$df.Name] = $ver
        } catch { $schemaVersions[$df.Name] = "解析失败" }
    }
}
$missingSchema = ($schemaVersions.GetEnumerator() | Where-Object { $_.Value -eq "缺失" }).Count
$mismatchSchema = ($schemaVersions.GetEnumerator() | Where-Object { $_.Value -ne "缺失" -and $_.Value -ne "1.0" }).Count
if ($missingSchema -eq 0 -and $mismatchSchema -eq 0) {
    Add-Check 'D' '4' 'Schema版本一致性' 'PASS' "所有核心数据文件 _schema_version=1.0"
} elseif ($missingSchema -gt 0) {
    Add-Check 'D' '4' 'Schema版本一致性' 'WARN' "$missingSchema 个文件缺少 _schema_version 字段"
} else {
    Add-Check 'D' '4' 'Schema版本一致性' 'FAIL' "Schema版本不一致: $($schemaVersions.GetEnumerator() | ForEach-Object { \"$($_.Key)=$($_.Value)\" }) -join '; '"
}

# ============================================================
# Section E: 文件系统卫生 (每周)
# ============================================================
Write-Host "── Section E: 文件系统卫生 ──" -ForegroundColor Cyan

# E-1: 脚本重复检测 (SHA256)
$allPS1 = Get-ChildItem $rootDir -Recurse -Filter "*.ps1" -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -notmatch "\.git|node_modules" }
$hashGroups = $allPS1 | Group-Object { (Get-FileHash $_.FullName -Algorithm SHA256).Hash }
$dupes = $hashGroups | Where-Object { $_.Count -gt 1 }
if ($dupes.Count -eq 0) { Add-Check 'E' '1' '脚本重复检测' 'PASS' "无重复脚本" }
else {
    $dupNames = ($dupes | ForEach-Object { ($_.Group | Select-Object -First 2 | ForEach-Object { $_.Name }) -join '=' }) -join '; '
    Add-Check 'E' '1' '脚本重复检测' 'FAIL' "$($dupes.Count) 组重复: $dupNames"
}

# E-3: 空目录（排除基础设施和脚本占位目录）
$allDirs = Get-ChildItem $rootDir -Recurse -Directory -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -notmatch "\.git" }
$emptyDirs = $allDirs | Where-Object {
    $p = $_.FullName
    (Get-ChildItem $p -Force -ErrorAction SilentlyContinue).Count -eq 0 -and
    $p -notmatch '\\\.claude\\' -and
    $p -notmatch '\\模拟交易\\每日交易记录\\' -and
    $p -notmatch '\\模拟交易\\策略迭代\\' -and
    $p -notmatch '\\模拟交易\\生成\\' -and
    $p -notmatch '\\重点股票\\次日评估\\' -and
    $p -notmatch '\\重点股票\\股票报告' -and
    $p -notmatch '\\历史数据\\cache' -and
    $p -notmatch '\\历史数据\\03_审计报告\\'
}
if ($emptyDirs.Count -eq 0) { Add-Check 'E' '3' '空目录检测' 'PASS' "无空目录" }
elseif ($emptyDirs.Count -le 2) { Add-Check 'E' '3' '空目录检测' 'WARN' "$($emptyDirs.Count) 个空目录: $($emptyDirs.Name -join ', ')" }
else { Add-Check 'E' '3' '空目录检测' 'WARN' "$($emptyDirs.Count) 个空目录（含占位/基础设施目录）" }

# E-6: S级资产备份完整性
$sAssets = @("transactions.csv", "positions.json", "perf_summary.json")
$backupOk = $true
foreach ($a in $sAssets) {
    $src = Join-Path $auditDir "00_核心交易\$a"
    $dst = Join-Path $auditDir "_backup\$a"
    if ((Test-Path $src) -and (Test-Path $dst)) {
        $srcHash = (Get-FileHash $src -Algorithm SHA256).Hash
        $dstHash = (Get-FileHash $dst -Algorithm SHA256).Hash
        if ($srcHash -ne $dstHash) { $backupOk = $false }
    }
}
if ($backupOk) { Add-Check 'E' '6' 'S级资产备份' 'PASS' "SHA256校验通过" }
else { Add-Check 'E' '6' 'S级资产备份' 'FAIL' "备份与源文件不一致" }

# E-8: 日志文件大小
$logFiles = Get-ChildItem $scriptsDir -Filter "workflow_*.log" -ErrorAction SilentlyContinue
$totalLogSize = ($logFiles | Measure-Object Length -Sum).Sum
if ($totalLogSize -lt 5MB) { Add-Check 'E' '8' '日志文件大小' 'PASS' "$([math]::Round($totalLogSize/1KB,1))KB" }
elseif ($totalLogSize -lt 10MB) { Add-Check 'E' '8' '日志文件大小' 'WARN' "$([math]::Round($totalLogSize/1KB,1))KB" }
else { Add-Check 'E' '8' '日志文件大小' 'FAIL' "$([math]::Round($totalLogSize/1MB,1))MB" }

# E-11: Git 状态
$gitStatus = & git -C $rootDir status --porcelain 2>&1 | Out-String
$untracked = ($gitStatus -split "`n" | Where-Object { $_ -match '^\?\?' }).Count
$modified = ($gitStatus -split "`n" | Where-Object { $_ -match '^ M|^M ' }).Count
if ($untracked -eq 0 -and $modified -eq 0) { Add-Check 'E' '11' 'Git工作区状态' 'PASS' "干净" }
elseif ($modified -gt 0) { Add-Check 'E' '11' 'Git工作区状态' 'WARN' "$modified 已修改, $untracked 未追踪" }
else { Add-Check 'E' '11' 'Git工作区状态' 'WARN' "$untracked 个未追踪文件" }
} # end -not $Quick

# ============================================================
# Section F: 流水线健康 (每日)
# ============================================================
Write-Host "── Section F: 流水线健康 ──" -ForegroundColor Cyan

# F-1: 今日流水线执行确认
if (Test-Path $workflowLog) {
    $todayEntries = Select-String -Path $workflowLog -Pattern $Date -SimpleMatch -ErrorAction SilentlyContinue
    if ($todayEntries.Count -gt 0) {
        $phases = ($todayEntries | Select-String -Pattern "\[(\d+)/" | ForEach-Object { if ($_.Matches) { $_.Matches.Groups[1].Value } } | Sort-Object -Unique) -join ','
        Add-Check 'F' '1' '今日流水线执行' 'PASS' "$($todayEntries.Count)条日志, Phase: $phases"
    } else {
        Add-Check 'F' '1' '今日流水线执行' 'WARN' "今日无执行记录（可能非交易日）"
    }
} else {
    Add-Check 'F' '1' '今日流水线执行' 'WARN' "日志文件不存在"
}

# F-4: 错误日志扫描
if (Test-Path $workflowLog) {
    $errors = Select-String -Path $workflowLog -Pattern "ERROR|FATAL|FAIL" -SimpleMatch -ErrorAction SilentlyContinue
    $recentErrors = $errors | Where-Object { $_.Line -match $Date }
    if ($recentErrors.Count -eq 0) { Add-Check 'F' '4' '错误日志扫描' 'PASS' "今日无ERROR" }
    elseif ($recentErrors.Count -le 3) { Add-Check 'F' '4' '错误日志扫描' 'WARN' "$($recentErrors.Count) 个ERROR" }
    else { Add-Check 'F' '4' '错误日志扫描' 'FAIL' "$($recentErrors.Count) 个ERROR" }
}

# ============================================================
# Section G: 集成已有检查 (每日+每周)
# ============================================================
Write-Host "── Section G: 集成已有检查 ──" -ForegroundColor Cyan

# G-1: check_redlines.ps1
$redlineScript = Join-Path $redlinesDir "check_redlines.ps1"
$r = Invoke-ExistingScript $redlineScript $(if($Quick){@('-Quick')}else{@()})
if (-not $r) {
    Add-Check 'G' '1' '红线合规检查' 'WARN' "check_redlines 不可用"
} else {
    $redOutput = $r.Output
    # 解析输出中的 FAIL 计数。check_redlines 有 WARN 时也会非零退出，
    # 所以不能仅看 exit code。输出中 "FAIL N" 才是真实 FAIL 数。
    $failMatch = [regex]::Match($redOutput, 'FAIL\s*(\d+)', 'IgnoreCase')
    $redFailCount = if ($failMatch.Success) { [int]$failMatch.Groups[1].Value } else { -1 }
    if ($redFailCount -eq 0) {
        Add-Check 'G' '1' '红线合规检查' 'PASS' "check_redlines 通过 (0 FAIL)"
    } elseif ($redFailCount -gt 0) {
        Add-Check 'G' '1' '红线合规检查' 'FAIL' "check_redlines 未通过 ($redFailCount FAIL)"
    } else {
        # 无法解析 FAIL 计数，回退到 exit code (0=PASS, 非0=WARN)
        if ($r.ExitCode -eq 0) { Add-Check 'G' '1' '红线合规检查' 'PASS' "check_redlines 通过" }
        else { Add-Check 'G' '1' '红线合规检查' 'WARN' "check_redlines 有WARN项(exit=$($r.ExitCode))，无FAIL" }
    }
}

# G-2: version_supervisor.ps1
$vsScript = Join-Path $supervisorDir "version_supervisor.ps1"
$vs = Invoke-ExistingScript $vsScript
if (-not $vs) {
    Add-Check 'G' '2' '版本一致性检查' 'WARN' "version_supervisor 不可用"
} else {
    $vsOutput = $vs.Output
    # 解析输出中的错误计数: "错误: N"
    $vsErrMatch = [regex]::Match($vsOutput, '错误[：:]\s*(\d+)', 'IgnoreCase')
    $vsWarnMatch = [regex]::Match($vsOutput, '提醒[：:]\s*(\d+)', 'IgnoreCase')
    $vsErrCount = if ($vsErrMatch.Success) { [int]$vsErrMatch.Groups[1].Value } else { -1 }
    $vsWarnCount = if ($vsWarnMatch.Success) { [int]$vsWarnMatch.Groups[1].Value } else { 0 }
    if ($vsErrCount -eq 0) {
        if ($vsWarnCount -eq 0) {
            Add-Check 'G' '2' '版本一致性检查' 'PASS' "version_supervisor 通过"
        } else {
            Add-Check 'G' '2' '版本一致性检查' 'WARN' "version_supervisor: $vsWarnCount 提醒, 0 错误"
        }
    } elseif ($vsErrCount -gt 0) {
        Add-Check 'G' '2' '版本一致性检查' 'FAIL' "version_supervisor: $vsErrCount 错误"
    } else {
        # 无法解析计数，回退到 exit code
        if ($vs.ExitCode -eq 0) { Add-Check 'G' '2' '版本一致性检查' 'PASS' "version_supervisor 通过" }
        else { Add-Check 'G' '2' '版本一致性检查' 'WARN' "version_supervisor 有提醒项(exit=$($vs.ExitCode))" }
    }
}

# G-3: check_report_style.ps1
$styleScript = Join-Path $redlinesDir "check_report_style.ps1"
$st = Invoke-ExistingScript $styleScript
if ($st -and $st.ExitCode -eq 0) { Add-Check 'G' '3' '报告样式检查' 'PASS' "check_report_style 通过" }
elseif ($st -and $st.ExitCode -ne 0) { Add-Check 'G' '3' '报告样式检查' 'FAIL' "check_report_style 未通过" }
else { Add-Check 'G' '3' '报告样式检查' 'WARN' "check_report_style 不可用" }

# ============================================================
# Section H: 紧急豁免追踪 (§5.6) (每日)
# ============================================================
Write-Host "── Section H: 紧急豁免追踪 ──" -ForegroundColor Cyan

$improvLog = Join-Path $rootDir "改进日志.md"
if (Test-Path $improvLog) {
    $improvContent = Get-Content $improvLog -Raw -Encoding UTF8
    # 匹配豁免记录: 场景 + 豁免规则 + 审批人 + 补齐期限
    $exemptPattern = '(?s)豁免[：:]\s*(.+?)(?=\n(?:#|$|\n\s*\n))'
    $exemptMatches = [regex]::Matches($improvContent, $exemptPattern)
    if ($exemptMatches.Count -gt 0) {
        $ruleCounter = @{}
        foreach ($m in $exemptMatches) {
            $block = $m.Groups[1].Value
            # 提取豁免的规则编号（如 §3.2, §5.5）
            $ruleRefs = [regex]::Matches($block, '§\d+\.\d+(?:\.\d+)?') | ForEach-Object { $_.Value }
            foreach ($ref in $ruleRefs) {
                if (-not $ruleCounter.ContainsKey($ref)) { $ruleCounter[$ref] = 0 }
                $ruleCounter[$ref]++
            }
        }
        $overLimit = $ruleCounter.GetEnumerator() | Where-Object { $_.Value -ge 3 }
        if ($overLimit) {
            $overList = ($overLimit | ForEach-Object { "$($_.Key):$($_.Value)次" }) -join ', '
            Add-Check 'H' '1' '紧急豁免次数' 'FAIL' "连续豁免>=3次须启动规则修订: $overList"
        } else {
            Add-Check 'H' '1' '紧急豁免次数' 'PASS' "总豁免$($exemptMatches.Count)条，无规则超3次"
        }
        # H-2: 补齐期限检查
        $now = Get-Date
        $overdueCount = 0
        foreach ($m in $exemptMatches) {
            if ($m.Groups[1].Value -match '补齐.*?(\d{4}-\d{2}-\d{2})') {
                $deadline = [datetime]::Parse($matches[1])
                if ($now -gt $deadline) { $overdueCount++ }
            }
        }
        if ($overdueCount -gt 0) {
            Add-Check 'H' '2' '豁免补齐期限' 'FAIL' "$overdueCount 条豁免超过补齐期限"
        } else {
            Add-Check 'H' '2' '豁免补齐期限' 'PASS' "无过期未补齐的豁免"
        }
    } else {
        Add-Check 'H' '1' '紧急豁免记录' 'PASS' "无紧急豁免记录"
        Add-Check 'H' '2' '豁免补齐期限' 'PASS' "不适用"
    }
} else {
    Add-Check 'H' '1' '紧急豁免记录' 'WARN' "改进日志.md 不存在"
    Add-Check 'H' '2' '豁免补齐期限' 'WARN' "无法检查"
}

# G-4: verify_report_output (报告路径合规)
$vrScript = Join-Path $supervisorDir "verify_report_output.ps1"
$vr = Invoke-ExistingScript $vrScript
if (-not $vr) {
    Add-Check 'G' '4' '报告路径合规' 'WARN' "verify_report_output 不可用"
} else {
    $vrFailMatch = [regex]::Match($vr.Output, '失败:\s*(\d+)')
    $vrFailCount = if ($vrFailMatch.Success) { [int]$vrFailMatch.Groups[1].Value } else { -1 }
    if ($vrFailCount -eq 0) {
        Add-Check 'G' '4' '报告路径合规' 'PASS' "verify_report_output 通过"
    } elseif ($vrFailCount -gt 0) {
        Add-Check 'G' '4' '报告路径合规' 'FAIL' "verify_report_output 未通过 ($vrFailCount 项)"
    } else {
        if ($vr.ExitCode -eq 0) { Add-Check 'G' '4' '报告路径合规' 'PASS' "verify_report_output 通过" }
        else { Add-Check 'G' '4' '报告路径合规' 'WARN' "verify_report_output 有警告(exit=$($vr.ExitCode))" }
    }
}

# ============================================================
# Section I: OOS合规检查 (§5.5) (每周)
# ============================================================
if (-not $Quick) {
Write-Host "── Section I: OOS样本外验证合规 ──" -ForegroundColor Cyan

# CHANGELOG files to scan (whitepapers + 模拟交易)
$oosChangelogs = @(
    @{ Name='每日荐股分析逻辑白皮书';     Path="$rootDir\每日荐股\分析逻辑\每日荐股分析逻辑白皮书_CHANGELOG.md" },
    @{ Name='次日后评估白皮书';             Path="$rootDir\每日荐股\事后评估\次日后评估白皮书_CHANGELOG.md" },
    @{ Name='重点股票跟踪分析逻辑白皮书';   Path="$rootDir\重点股票\分析逻辑\重点股票跟踪分析逻辑白皮书_CHANGELOG.md" },
    @{ Name='重点股票次日后评估白皮书';     Path="$rootDir\重点股票\次日评估\重点股票次日后评估白皮书_CHANGELOG.md" },
    @{ Name='分析的规则红线';               Path="$rootDir\规则红线\分析的规则红线--Claude_CHANGELOG.md" },
    @{ Name='模拟交易白皮书';               Path="$rootDir\模拟交易\模拟交易白皮书_CHANGELOG.md" }
)

# §5.5.1: OOS必须关键词 → CHANGELOG条目必须有"OOS通过"标记
$OOS_REQUIRED = @(
    '评分权重', '权重调整', '否决阈值', '阈值变更',
    '新增.*因子', '删除.*因子', '因子.*新增', '因子.*删除',
    '开仓规则', '出场规则', '仓位规则', '交易规则.*变更',
    '选股逻辑', '一票否决.*调整'
)
# §5.5.4: 豁免标记
$OOS_EXEMPT = '(OOS豁免|OOS\s*免检|紧急风控|Bug\s*修复|修复.*Bug|除零|计算逻辑错误|仅新增备源|数据源新增)'

$oosFail = 0; $oosWarn = 0; $oosChecked = 0

foreach ($cl in $oosChangelogs) {
    if (-not (Test-Path $cl.Path)) { continue }
    $clContent = Get-Content $cl.Path -Raw -Encoding UTF8
    $entries = $clContent -split '(?=## v\d+\.\d+)' | Where-Object { $_.Trim() -ne '' }

    foreach ($entry in $entries) {
        if ($entry -match '^\s*##\s*\[Unreleased\]') { continue }
        if ($entry -notmatch '##\s*v(\d+\.\d+(?:\.\d+)?)') { continue }
        $entryVersion = "v$($matches[1])"

        $needsOOS = $false; $matchedKw = ""
        foreach ($kw in $OOS_REQUIRED) {
            if ($entry -match $kw) { $needsOOS = $true; $matchedKw = $kw; break }
        }
        if (-not $needsOOS) { continue }

        $oosChecked++
        $hasOOS = $entry -match 'OOS通过|OOS\s*验证通过|OOS\s*PASS|样本外验证通过'
        $hasExempt = $entry -match $OOS_EXEMPT

        if ($hasOOS) {
            # PASS — 静默
        } elseif ($hasExempt) {
            $oosWarn++
            Add-Check 'I' "$($oosChecked)" "$($cl.Name) $entryVersion" 'WARN' "匹配'$matchedKw'但标记豁免，需确认审批"
        } else {
            $oosFail++
            Add-Check 'I' "$($oosChecked)" "$($cl.Name) $entryVersion" 'FAIL' "匹配'$matchedKw'但无OOS通过标记！须补充OOS验证或豁免"
        }
    }
}

if ($oosChecked -eq 0) {
    Add-Check 'I' '0' 'OOS合规扫描' 'PASS' "扫描6个CHANGELOG，无需OOS验证的变更条目"
} elseif ($oosFail -eq 0 -and $oosWarn -eq 0) {
    Add-Check 'I' '0' 'OOS合规扫描' 'PASS' "$oosChecked 条需OOS变更，全部通过"
}
} # end -not $Quick
