<#
.SYNOPSIS
  铁律量化 · 每日数据归档脚本
.DESCRIPTION
  每天流水线跑完后执行，将当日关键数据文件归档到历史数据/ 目录。
  同时管理归档保留策略（保留90天），避免磁盘无限增长。
.PARAMETER Date
  归档日期标签，默认今天。格式 yyyy-MM-dd。
.PARAMETER SourceDir
  数据文件所在根目录。默认 $rootDir。
.PARAMETER RetentionDays
  归档保留天数，默认90天。
#>

param(
    [string]$Date = (Get-Date -Format "yyyy-MM-dd"),
    [string]$SourceDir = (Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))),
    [int]$RetentionDays = 90
)
. "$PSScriptRoot/../../lib/init_encoding.ps1"

$archiveRoot = Join-Path $SourceDir "历史数据"
$dateLabel = $Date -replace '-', ''
$dailyDir = Join-Path $SourceDir "每日荐股"
$scriptsDir = Join-Path $SourceDir "代码文件\每日荐股\scripts"
$logFile = Join-Path $scriptsDir "workflow_$(Get-Date -Format yyyyMM).log"

function Write-Log {
    param([string]$Msg, [string]$Level = "INFO")
    $time = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $line = "[$time][ARCHIVE][$Level] $Msg"
    Add-Content -Path $logFile -Value $line -Encoding UTF8
    Write-Output $line
}

function Archive-File {
    param([string]$FilePath, [string]${ArchiveSubDir})
    if (-not (Test-Path $FilePath)) {
        Write-Log -Msg "文件不存在，跳过: $FilePath" -Level "WARN"
        return $false
    }
    $targetDir = Join-Path $archiveRoot ${ArchiveSubDir}
    if (-not (Test-Path $targetDir)) { New-Item -ItemType Directory -Path $targetDir -Force | Out-Null }

    $ext = [System.IO.Path]::GetExtension($FilePath)
    $baseName = [System.IO.Path]::GetFileNameWithoutExtension($FilePath)
    $archiveName = "${dateLabel}_${baseName}${ext}"
    $targetPath = Join-Path $targetDir $archiveName

    Copy-Item -Path $FilePath -Destination $targetPath -Force
    Write-Log -Msg "归档: $($FilePath) → $targetPath"
    return $true
}

function Clean-OldArchives {
    param([string]${ArchiveSubDir})
    $targetDir = Join-Path $archiveRoot ${ArchiveSubDir}
    if (-not (Test-Path $targetDir)) { return }
    $cutoff = (Get-Date).AddDays(-$RetentionDays)
    ${deleted} = 0
    Get-ChildItem $targetDir -File | Where-Object { $_.LastWriteTime -lt $cutoff } | ForEach-Object {
        Remove-Item $_.FullName -Force
        ${deleted}++
    }
    if (${deleted} -gt 0) {
        Write-Log -Msg "清理 ${ArchiveSubDir}: 删除 ${deleted} 个过期文件（>$RetentionDays 天）"
    }
}

# 需要保留最新的文件数量（而非按时间清理）
$keepLatestCount = 60

function Trim-ToLatest {
    param([string]${ArchiveSubDir}, [int]${KeepCount} = $keepLatestCount)
    $targetDir = Join-Path $archiveRoot ${ArchiveSubDir}
    if (-not (Test-Path $targetDir)) { return }
    $files = Get-ChildItem $targetDir -File | Sort-Object LastWriteTime -Descending
    if ($files.Count -gt ${KeepCount}) {
        $toDelete = $files | Select-Object -Skip ${KeepCount}
        $toDelete | ForEach-Object { Remove-Item $_.FullName -Force }
        Write-Log -Msg "裁剪 ${ArchiveSubDir}: 保留最新 ${KeepCount} 个，删除 $($toDelete.Count) 个"
    }
}

# P2-3: 缓存滚动清理 — 删除过期/超额缓存文件
function Invoke-RollingCleanup {
    param(
        [string]$CacheDir = "",
        [int]$MaxCacheFiles = 500,
        [int]$MaxCacheAgeHours = 168
    )
    if (-not $CacheDir -or -not (Test-Path $CacheDir)) {
        if ($CacheDir) { Write-Log -Msg "缓存目录不存在，跳过清理: $CacheDir" -Level "INFO" }
        return
    }
    # 删除超过TTL的文件
    $cutoff = (Get-Date).AddHours(-$MaxCacheAgeHours)
    $oldFiles = Get-ChildItem $CacheDir -File -Recurse -ErrorAction SilentlyContinue | Where-Object { $_.LastWriteTime -lt $cutoff }
    if ($oldFiles) {
        $oldFiles | Remove-Item -Force -ErrorAction SilentlyContinue
        Write-Log -Msg "缓存清理: 删除 $($oldFiles.Count) 个过期文件 (>${MaxCacheAgeHours}h)"
    }
    # 若仍超量，删最旧的
    $remaining = Get-ChildItem $CacheDir -File -Recurse -ErrorAction SilentlyContinue
    if ($remaining.Count -gt $MaxCacheFiles) {
        $toDelete = $remaining | Sort-Object LastWriteTime | Select-Object -First ($remaining.Count - $MaxCacheFiles)
        $toDelete | Remove-Item -Force -ErrorAction SilentlyContinue
        Write-Log -Msg "缓存裁剪: 超出${MaxCacheFiles}上限，删除 $($toDelete.Count) 个最旧文件"
    }
}

Write-Log -Msg "===== 开始归档 ($Date) ====="

# ---------- 每日荐股数据 (情墨新架构: 04_原始数据 + 05_参考数据) ----------
Archive-File -FilePath (Join-Path $SourceDir "代码文件\数据\dynamic_pool.json") -ArchiveSubDir "05_参考数据"
Archive-File -FilePath (Join-Path $SourceDir "代码文件\数据\data_full.json") -ArchiveSubDir "04_原始数据"
Archive-File -FilePath (Join-Path $SourceDir "代码文件\数据\data_scored.json") -ArchiveSubDir "04_原始数据"
Archive-File -FilePath (Join-Path $SourceDir "代码文件\数据\data_final.json") -ArchiveSubDir "04_原始数据"

# ---------- 板块/行业数据 (情墨新架构: 05_参考数据) ----------
Archive-File -FilePath (Join-Path $SourceDir "代码文件\数据\sector_data.json") -ArchiveSubDir "05_参考数据"
Archive-File -FilePath (Join-Path $SourceDir "代码文件\数据\industry_map.json") -ArchiveSubDir "05_参考数据"
Archive-File -FilePath (Join-Path $SourceDir "代码文件\数据\eastmoney_sector_map.json") -ArchiveSubDir "05_参考数据"

# ---------- 每日荐股报告 (情墨新架构: 03_分析报告/每日荐股) ----------
$reportDir = Join-Path $dailyDir "股票报告"
if (Test-Path $reportDir) {
    $reports = Get-ChildItem $reportDir -Filter "daily_report_*.html"
    $pdfReports = Get-ChildItem $reportDir -Filter "daily_report_*.pdf"
    $allReports = $reports + $pdfReports
    foreach ($rpt in $allReports) {
        $targetDir = Join-Path $archiveRoot "03_分析报告\每日荐股"
        if (-not (Test-Path $targetDir)) { New-Item -ItemType Directory -Path $targetDir -Force | Out-Null }
        $ext = [System.IO.Path]::GetExtension($rpt.Name)
        $baseName = [System.IO.Path]::GetFileNameWithoutExtension($rpt.Name)
        $archiveName = "${dateLabel}_${baseName}${ext}"
        Copy-Item -Path $rpt.FullName -Destination (Join-Path $targetDir $archiveName) -Force
        Write-Log -Msg "归档报告: $archiveName"
    }
}

# ---------- 重点股票数据 (情墨新架构: 02_评估数据) ----------
$keyStockDir = Join-Path $SourceDir "重点股票"
$keystockEvalData = Join-Path $keyStockDir "次日评估"
if (Test-Path $keystockEvalData) {
    $evalFiles = Get-ChildItem $keystockEvalData -Filter "评估数据_*.json" | Where-Object { $_.Name -match "\d{8}" }
    foreach ($ef in $evalFiles) {
        $targetDir = Join-Path $archiveRoot "02_评估数据"
        if (-not (Test-Path $targetDir)) { New-Item -ItemType Directory -Path $targetDir -Force | Out-Null }
        $archiveName = $ef.Name  # 源文件名已含日期，不再加前缀
        Copy-Item -Path $ef.FullName -Destination (Join-Path $targetDir $archiveName) -Force
        Write-Log -Msg "归档: $($ef.FullName)"
    }
}

# ---------- 每日荐股评估报告 (情墨新架构: 03_分析报告/后评估) ----------
$evalReportDir = Join-Path $dailyDir "评估报告"
if (Test-Path $evalReportDir) {
    $reports = Get-ChildItem $evalReportDir -Filter "每日荐股后评估报告.*"
    foreach ($rpt in $reports) {
        $targetDir = Join-Path $archiveRoot "03_分析报告\后评估"
        if (-not (Test-Path $targetDir)) { New-Item -ItemType Directory -Path $targetDir -Force | Out-Null }
        $ext = [System.IO.Path]::GetExtension($rpt.Name)
        $archiveName = "${dateLabel}_后评估报告${ext}"
        Copy-Item -Path $rpt.FullName -Destination (Join-Path $targetDir $archiveName) -Force
        Write-Log -Msg "归档评估报告: $archiveName"
    }
}

# ---------- S级资产双副本归档 (情墨新架构: 00_核心交易 + _backup) ----------
$coreDir = Join-Path $archiveRoot "00_核心交易"
$backupDir = Join-Path $archiveRoot "_backup"
if (-not (Test-Path $coreDir)) { New-Item -ItemType Directory -Path $coreDir -Force | Out-Null }
if (-not (Test-Path $backupDir)) { New-Item -ItemType Directory -Path $backupDir -Force | Out-Null }

$sAssets = @(
    @{Src="模拟交易\持仓记录\transactions.csv"; Name="transactions.csv"},
    @{Src="模拟交易\持仓记录\positions.json"; Name="positions.json"},
    @{Src="模拟交易\绩效报告\perf_summary.json"; Name="perf_summary.json"}
)
foreach ($asset in $sAssets) {
    $srcPath = Join-Path $SourceDir $asset.Src
    if (Test-Path $srcPath) {
        $dstCore = Join-Path $coreDir $asset.Name
        Copy-Item $srcPath $dstCore -Force
        if (Test-Path $backupDir) {
            $dstBackup = Join-Path $backupDir $asset.Name
            Copy-Item $srcPath $dstBackup -Force
            $h1 = (Get-FileHash $dstCore -Algorithm SHA256).Hash
            $h2 = (Get-FileHash $dstBackup -Algorithm SHA256).Hash
            if ($h1 -ne $h2) { Write-Log -Msg "S级备份校验失败: $($asset.Name)" -Level "ERROR" }
        }
        Write-Log -Msg "S级归档: $($asset.Name) → 00_核心交易 + _backup (SHA256校验通过)"
    }
}

# ---------- 交易快照归档 (情墨新架构: 01_交易快照) ----------
$snapshotSrc = Join-Path $SourceDir "模拟交易\每日快照"
if (Test-Path $snapshotSrc) {
    $snapshotTarget = Join-Path $archiveRoot "01_交易快照"
    if (-not (Test-Path $snapshotTarget)) { New-Item -ItemType Directory -Path $snapshotTarget -Force | Out-Null }
    Get-ChildItem $snapshotSrc -Filter "snapshot_*.json" | ForEach-Object {
        Copy-Item $_.FullName (Join-Path $snapshotTarget $_.Name) -Force
        Write-Log -Msg "快照归档: $($_.Name)"
    }
}

# ---------- 月度归档 (情墨新架构: 06_月度归档) ----------
$monthlyDir = Join-Path $SourceDir "临时报告"
$monthlyTarget = Join-Path $archiveRoot "06_月度归档"
if (-not (Test-Path $monthlyTarget)) { New-Item -ItemType Directory -Path $monthlyTarget -Force | Out-Null }
if (Test-Path $monthlyDir) {
    $monthlyFiles = Get-ChildItem $monthlyDir -Filter "月度*" -ErrorAction SilentlyContinue
    $monthlyFiles += Get-ChildItem $monthlyDir -Filter "monthly*" -ErrorAction SilentlyContinue
    foreach ($mf in $monthlyFiles) {
        Copy-Item $mf.FullName (Join-Path $monthlyTarget $mf.Name) -Force
        Write-Log -Msg "月度归档: $($mf.Name)"
    }
}

# ---------- 裁剪保留（情墨新架构路径） ----------
Trim-ToLatest -ArchiveSubDir "05_参考数据"
Trim-ToLatest -ArchiveSubDir "04_原始数据"
Trim-ToLatest -ArchiveSubDir "03_分析报告\每日荐股"

# 保留90天清理
Clean-OldArchives -ArchiveSubDir "05_参考数据"
Clean-OldArchives -ArchiveSubDir "04_原始数据"
Clean-OldArchives -ArchiveSubDir "03_分析报告\每日荐股"
Clean-OldArchives -ArchiveSubDir "03_分析报告\后评估"
Clean-OldArchives -ArchiveSubDir "02_评估数据"

# ---------- 缓存清理 (P2-3) ----------
# 旧缓存路径 (实际491文件所在)
$legacyCacheDir = Join-Path $SourceDir "代码文件\每日荐股\data_cache"
Invoke-RollingCleanup -CacheDir $legacyCacheDir
# 新缓存路径 (Arch五级分层目标位置)
$cacheDir = Join-Path $archiveRoot "cache"
if (-not (Test-Path $cacheDir)) { New-Item -ItemType Directory -Path $cacheDir -Force | Out-Null }
Invoke-RollingCleanup -CacheDir $cacheDir

# ---------- 汇总 ----------
Write-Log -Msg "归档完成。历史数据位置: $archiveRoot"
Write-Log -Msg "===== 归档结束 ====="
