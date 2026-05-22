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
    [string]$SourceDir = "C:\Users\34269\Documents\Claude\股票分析",
    [int]$RetentionDays = 90
)

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

Write-Log -Msg "===== 开始归档 ($Date) ====="

# ---------- 每日荐股数据 ----------
Archive-File -FilePath (Join-Path $SourceDir "代码文件\数据\dynamic_pool.json") -ArchiveSubDir "daily_pool"
Archive-File -FilePath (Join-Path $SourceDir "代码文件\数据\data_full.json") -ArchiveSubDir "raw_data"
Archive-File -FilePath (Join-Path $SourceDir "代码文件\数据\data_scored.json") -ArchiveSubDir "scored"
Archive-File -FilePath (Join-Path $SourceDir "代码文件\数据\data_final.json") -ArchiveSubDir "final"

# ---------- 板块/行业数据 ----------
Archive-File -FilePath (Join-Path $SourceDir "代码文件\数据\sector_data.json") -ArchiveSubDir "sector"
Archive-File -FilePath (Join-Path $SourceDir "代码文件\数据\industry_map.json") -ArchiveSubDir "sector"
Archive-File -FilePath (Join-Path $SourceDir "代码文件\数据\eastmoney_sector_map.json") -ArchiveSubDir "sector"

# ---------- 每日荐股报告 ----------
$reportDir = Join-Path $dailyDir "股票报告"
if (Test-Path $reportDir) {
    $reports = Get-ChildItem $reportDir -Filter "daily_report_*.html"
    $pdfReports = Get-ChildItem $reportDir -Filter "daily_report_*.pdf"
    $allReports = $reports + $pdfReports
    foreach ($rpt in $allReports) {
        $targetDir = Join-Path $archiveRoot "reports"
        if (-not (Test-Path $targetDir)) { New-Item -ItemType Directory -Path $targetDir -Force | Out-Null }
        $ext = [System.IO.Path]::GetExtension($rpt.Name)
        $baseName = [System.IO.Path]::GetFileNameWithoutExtension($rpt.Name)
        $archiveName = "${dateLabel}_${baseName}${ext}"
        Copy-Item -Path $rpt.FullName -Destination (Join-Path $targetDir $archiveName) -Force
        Write-Log -Msg "归档报告: $archiveName"
    }
}

# ---------- 重点股票数据 ----------
$keyStockDir = Join-Path $SourceDir "重点股票"
$keystockEvalData = Join-Path $keyStockDir "次日评估"
if (Test-Path $keystockEvalData) {
    $evalFiles = Get-ChildItem $keystockEvalData -Filter "评估数据_*.json" | Where-Object { $_.Name -match "\d{8}" }
    foreach ($ef in $evalFiles) {
        $targetDir = Join-Path $archiveRoot "重点股票"
        if (-not (Test-Path $targetDir)) { New-Item -ItemType Directory -Path $targetDir -Force | Out-Null }
        $archiveName = "${dateLabel}_$($ef.Name)"
        Copy-Item -Path $ef.FullName -Destination (Join-Path $targetDir $archiveName) -Force
        Write-Log -Msg "归档: $($ef.FullName)"
    }
}

# ---------- 每日荐股评估报告 ----------
$evalReportDir = Join-Path $dailyDir "评估报告"
if (Test-Path $evalReportDir) {
    $reports = Get-ChildItem $evalReportDir -Filter "每日荐股后评估报告.*"
    foreach ($rpt in $reports) {
        $targetDir = Join-Path $archiveRoot "eval"
        if (-not (Test-Path $targetDir)) { New-Item -ItemType Directory -Path $targetDir -Force | Out-Null }
        $ext = [System.IO.Path]::GetExtension($rpt.Name)
        $archiveName = "${dateLabel}_后评估报告${ext}"
        Copy-Item -Path $rpt.FullName -Destination (Join-Path $targetDir $archiveName) -Force
        Write-Log -Msg "归档评估报告: $archiveName"
    }
}

# ---------- 裁剪保留（只保留最新5份，避免囤积） ----------
Trim-ToLatest -ArchiveSubDir "daily_pool"
Trim-ToLatest -ArchiveSubDir "raw_data"
Trim-ToLatest -ArchiveSubDir "scored"
Trim-ToLatest -ArchiveSubDir "final"
Trim-ToLatest -ArchiveSubDir "sector"
Trim-ToLatest -ArchiveSubDir "reports"

# 保留90天清理
Clean-OldArchives -ArchiveSubDir "daily_pool"
Clean-OldArchives -ArchiveSubDir "raw_data"
Clean-OldArchives -ArchiveSubDir "scored"
Clean-OldArchives -ArchiveSubDir "final"
Clean-OldArchives -ArchiveSubDir "sector"
Clean-OldArchives -ArchiveSubDir "reports"
Clean-OldArchives -ArchiveSubDir "eval"
Clean-OldArchives -ArchiveSubDir "重点股票"

# ---------- 汇总 ----------
Write-Log -Msg "归档完成。历史数据位置: $archiveRoot"
Write-Log -Msg "===== 归档结束 ====="
