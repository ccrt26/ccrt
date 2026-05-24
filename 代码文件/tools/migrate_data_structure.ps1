# 铁律量化 — 历史数据目录重组迁移脚本
# 基于 Arch 06-数据持久化架构设计.md
# 用法：.\migrate_data_structure.ps1 [-WhatIf] [-Force]
param([switch]$WhatIf, [switch]$Force)

$ErrorActionPreference = "Stop"
$rootDir = "C:\Users\34269\Documents\Claude\股票分析"
$newBase = Join-Path $rootDir "历史数据"
$backupLog = Join-Path $rootDir "代码文件\tools\migration_log.txt"

function Write-Step { param($Msg); Write-Host $Msg -ForegroundColor Cyan; Add-Content $backupLog "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] $Msg" }

if ($WhatIf) { Write-Host "=== WHATIF MODE — 不执行实际操作 ===" -ForegroundColor Yellow }

# ============================================================
# Step 1: 创建新目录结构
# ============================================================
Write-Step "Step 1: 创建新目录结构"

$newDirs = @(
    "$newBase\00_核心交易",
    "$newBase\01_交易快照",
    "$newBase\02_评估数据",
    "$newBase\03_分析报告\重点股票",
    "$newBase\03_分析报告\每日荐股",
    "$newBase\03_分析报告\后评估",
    "$newBase\04_原始数据",
    "$newBase\05_参考数据",
    "$newBase\06_月度归档",
    "$newBase\cache\kline",
    "$newBase\cache\research",
    "$newBase\cache\fundflow",
    "$newBase\cache\financial",
    "$newBase\cache\quote",
    "$newBase\cache\sector",
    "$newBase\_backup"
)

foreach ($d in $newDirs) {
    if (-not $WhatIf) {
        if (-not (Test-Path $d)) { New-Item -ItemType Directory -Path $d -Force | Out-Null }
    }
    Write-Host "  [目录] $d"
}

# ============================================================
# Step 2: 迁移 S级资产 (00_核心交易)
# ============================================================
Write-Step "Step 2: 迁移 S级资产 → 00_核心交易"

$sLevelMoves = @(
    @{Src="$rootDir\模拟交易\持仓记录\transactions.csv"; Dst="$newBase\00_核心交易\transactions.csv"},
    @{Src="$rootDir\模拟交易\持仓记录\positions.json";  Dst="$newBase\00_核心交易\positions.json"},
    @{Src="$rootDir\模拟交易\绩效报告\perf_summary.json"; Dst="$newBase\00_核心交易\perf_summary.json"}
)

foreach ($m in $sLevelMoves) {
    if (Test-Path $m.Src) {
        if (-not $WhatIf) { Copy-Item $m.Src $m.Dst -Force }
        Write-Host "  [S级] 复制: $($m.Src) → $($m.Dst)" -ForegroundColor Green
    } else {
        Write-Host "  [跳过] 源不存在: $($m.Src)" -ForegroundColor Yellow
    }
}

# ============================================================
# Step 3: 迁移 A级资产 (01_交易快照, 02_评估数据, 03_分析报告, 06_月度归档)
# ============================================================
Write-Step "Step 3: 迁移 A级资产"

# 3.1 每日快照 → 01_交易快照
$snapshotDir = "$rootDir\模拟交易\每日快照"
if (Test-Path $snapshotDir) {
    Get-ChildItem $snapshotDir -Filter "snapshot_*.json" | ForEach-Object {
        if (-not $WhatIf) { Copy-Item $_.FullName "$newBase\01_交易快照\$($_.Name)" -Force }
        Write-Host "  [A-快照] 复制: $($_.Name)"
    }
}

# 3.2 评估数据 → 02_评估数据
$evalSrcDir = "$rootDir\重点股票\次日评估"
if (Test-Path $evalSrcDir) {
    Get-ChildItem $evalSrcDir -Filter "评估数据_*.json" | ForEach-Object {
        if (-not $WhatIf) { Copy-Item $_.FullName "$newBase\02_评估数据\$($_.Name)" -Force }
        Write-Host "  [A-评估] 复制: $($_.Name)"
    }
}

# 3.3 历史重点股票评估数据 → 合并到 02_评估数据
$histKeyStock = "$newBase\重点股票"
if (Test-Path $histKeyStock) {
    Get-ChildItem $histKeyStock -Filter "*.json" | ForEach-Object {
        $dstName = $_.Name -replace '^\d{8}_', ''
        if (-not $WhatIf) { Copy-Item $_.FullName "$newBase\02_评估数据\$dstName" -Force }
        Write-Host "  [A-评估-历史] 复制: $($_.Name) → $dstName"
    }
}

# 3.4 分析报告 PDF → 03_分析报告
# 重点股票分析报告
$keyReportDir = "$rootDir\重点股票\股票报告"
if (Test-Path $keyReportDir) {
    Get-ChildItem $keyReportDir -Filter "*.pdf" | ForEach-Object {
        if (-not $WhatIf) { Copy-Item $_.FullName "$newBase\03_分析报告\重点股票\$($_.Name)" -Force }
        Write-Host "  [A-报告] 复制: $($_.Name)"
    }
}

# 每日荐股报告
$dailyReportDir = "$rootDir\每日荐股\股票报告"
if (Test-Path $dailyReportDir) {
    Get-ChildItem $dailyReportDir -Filter "*.pdf" | ForEach-Object {
        if (-not $WhatIf) { Copy-Item $_.FullName "$newBase\03_分析报告\每日荐股\$($_.Name)" -Force }
        Write-Host "  [A-报告] 复制: $($_.Name)"
    }
}

# 历史 reports/
$histReports = "$newBase\reports"
if (Test-Path $histReports) {
    Get-ChildItem $histReports -Filter "*.pdf" | ForEach-Object {
        if (-not $WhatIf) { Copy-Item $_.FullName "$newBase\03_分析报告\每日荐股\$($_.Name)" -Force }
        Write-Host "  [A-报告-历史] 复制: $($_.Name)"
    }
}

# 后评估报告
$histEval = "$newBase\eval"
if (Test-Path $histEval) {
    Get-ChildItem $histEval -Filter "*.pdf" -ErrorAction SilentlyContinue | ForEach-Object {
        if (-not $WhatIf) { Copy-Item $_.FullName "$newBase\03_分析报告\后评估\$($_.Name)" -Force }
        Write-Host "  [A-后评估] 复制: $($_.Name)"
    }
    Get-ChildItem $histEval -Filter "*.html" -ErrorAction SilentlyContinue | ForEach-Object {
        if (-not $WhatIf) { Copy-Item $_.FullName "$newBase\03_分析报告\后评估\$($_.Name)" -Force }
        Write-Host "  [A-后评估] 复制: $($_.Name)"
    }
}

# 3.5 月度归档 → 06_月度归档
$histMonthly = "$newBase\monthly"
if (Test-Path $histMonthly) {
    Get-ChildItem $histMonthly | ForEach-Object {
        if (-not $WhatIf) { Copy-Item $_.FullName "$newBase\06_月度归档\$($_.Name)" -Force }
        Write-Host "  [A-月度] 复制: $($_.Name)"
    }
}

# ============================================================
# Step 4: 迁移 B级资产 (04_原始数据, 05_参考数据)
# ============================================================
Write-Step "Step 4: 迁移 B级资产"

# raw_data → 04_原始数据
$histRaw = "$newBase\raw_data"
if (Test-Path $histRaw) {
    Get-ChildItem $histRaw -Filter "*.json" | ForEach-Object {
        if (-not $WhatIf) { Copy-Item $_.FullName "$newBase\04_原始数据\raw_$($_.Name | Split-Path -Leaf)" -Force }
        Write-Host "  [B-原始] 复制: $($_.Name)"
    }
}

# scored → 04_原始数据
$histScored = "$newBase\scored"
if (Test-Path $histScored) {
    Get-ChildItem $histScored -Filter "*.json" | ForEach-Object {
        if (-not $WhatIf) { Copy-Item $_.FullName "$newBase\04_原始数据\scored_$($_.Name | Split-Path -Leaf)" -Force }
        Write-Host "  [B-评分] 复制: $($_.Name)"
    }
}

# final → 04_原始数据
$histFinal = "$newBase\final"
if (Test-Path $histFinal) {
    Get-ChildItem $histFinal -Filter "*.json" | ForEach-Object {
        if (-not $WhatIf) { Copy-Item $_.FullName "$newBase\04_原始数据\final_$($_.Name | Split-Path -Leaf)" -Force }
        Write-Host "  [B-最终] 复制: $($_.Name)"
    }
}

# sector → 05_参考数据
$histSector = "$newBase\sector"
if (Test-Path $histSector) {
    Get-ChildItem $histSector -Filter "*.json" | ForEach-Object {
        if (-not $WhatIf) { Copy-Item $_.FullName "$newBase\05_参考数据\$($_.Name)" -Force }
        Write-Host "  [B-板块] 复制: $($_.Name)"
    }
}

# daily_pool → 05_参考数据
$histPool = "$newBase\daily_pool"
if (Test-Path $histPool) {
    Get-ChildItem $histPool -Filter "*.json" | ForEach-Object {
        if (-not $WhatIf) { Copy-Item $_.FullName "$newBase\05_参考数据\$($_.Name)" -Force }
        Write-Host "  [B-候选池] 复制: $($_.Name)"
    }
}

# ============================================================
# Step 5: 清理空目录
# ============================================================
Write-Step "Step 5: 清理空目录"

$emptyDirs = @(
    "$newBase\评估",
    "$newBase\预判"
)
foreach ($d in $emptyDirs) {
    if ((Test-Path $d) -and (-not $WhatIf)) {
        $isEmpty = (Get-ChildItem $d -Force -ErrorAction SilentlyContinue).Count -eq 0
        if ($isEmpty) {
            Remove-Item $d -Force
            Write-Host "  [删除] 空目录: $d"
        }
    }
}

# ============================================================
# Step 6: 清理临时回溯 (脚本→代码文件/tools, 其余归类)
# ============================================================
Write-Step "Step 6: 处理临时回溯目录"

$tempDir = "$newBase\临时回溯"
if (Test-Path $tempDir) {
    # 脚本文件移动到代码文件/tools
    $scriptExts = @("*.ps1", "*.py")
    foreach ($ext in $scriptExts) {
        Get-ChildItem $tempDir -Filter $ext | ForEach-Object {
            $dstScript = "$rootDir\代码文件\tools\$($_.Name)"
            if (-not $WhatIf -and -not (Test-Path $dstScript)) {
                Move-Item $_.FullName $dstScript -Force
                Write-Host "  [脚本迁移] $($_.Name) → 代码文件/tools/"
            } elseif (Test-Path $dstScript) {
                Write-Host "  [跳过] 已存在: $($_.Name)" -ForegroundColor Yellow
            }
        }
    }

    # 剩余文件标注为可清理
    $remaining = Get-ChildItem $tempDir
    if ($remaining.Count -gt 0) {
        Write-Host "  [待清理] 临时回溯目录还有 $($remaining.Count) 个文件，请确认后手动删除" -ForegroundColor Yellow
        $remaining | ForEach-Object { Write-Host "    $($_.Name)" }
    }
}

# ============================================================
# Step 7: 创建 S级资产镜像备份
# ============================================================
Write-Step "Step 7: 创建 S级资产镜像备份"

$sAssets = @("transactions.csv", "positions.json", "perf_summary.json")
foreach ($f in $sAssets) {
    $src = "$newBase\00_核心交易\$f"
    $dst = "$newBase\_backup\$f"
    if (Test-Path $src) {
        if (-not $WhatIf) {
            Copy-Item $src $dst -Force
            $srcHash = (Get-FileHash $src -Algorithm SHA256).Hash
            $dstHash = (Get-FileHash $dst -Algorithm SHA256).Hash
            if ($srcHash -ne $dstHash) {
                Write-Host "  [错误] 备份校验失败: $f" -ForegroundColor Red
            } else {
                Write-Host "  [备份] $f ✓ (SHA256校验通过)" -ForegroundColor Green
            }
        } else {
            Write-Host "  [备份-WI] $f"
        }
    } else {
        Write-Host "  [跳过] 源文件不存在: $f" -ForegroundColor Yellow
    }
}

# ============================================================
# Step 8: 更新脚本路径引用
# ============================================================
Write-Step "Step 8: 更新脚本路径引用（需手动运行或重新生成）"
Write-Host "  以下脚本需要更新路径引用:"
Write-Host "  - sim_trading.ps1: 持仓/快照/绩效 路径 → 00_核心交易/"
Write-Host "  - run_keystock_analysis.ps1: 评估数据输出路径 → 02_评估数据/"
Write-Host "  - daily_workflow.ps1: 报告/数据归档路径"
Write-Host "  - archive_data.ps1: 归档目标路径"
Write-Host "  [注意] 旧路径仍保留作为过渡期双写目标"

Write-Step "迁移完成!"
Write-Host "查看详细日志: $backupLog"
