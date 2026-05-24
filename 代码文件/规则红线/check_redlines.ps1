<#
.SYNOPSIS
    铁律量化 · 自动化红线合规检查脚本
.DESCRIPTION
    对照规则红线 v1.13 的 6 大检查维度，验证当前项目状态。
    支持 -Quick 模式用于 PreToolUse hook 快速预检。
.NOTES
    版本: v1.1
    用法: powershell -File check_redlines.ps1 [-Quick]
    参数: -Quick 仅执行 §4 文件完整性检查（约2秒），用于 hook 触发
    退出码: 0 = 全部通过, 1 = 有违规
#>
param(
    [switch]$Quick
)

$BASE = "C:\Users\34269\Documents\Claude\股票分析"
$DATA_DIR = "$BASE\代码文件\数据"
$CACHE_DIR = "$BASE\代码文件\每日荐股\data_cache"
$REDLINES_DIR = "$BASE\代码文件\规则红线"
$REPORT_FILE = "$REDLINES_DIR\check_redlines_report.txt"

# ── 全局状态 ──
$global:pass_count = 0
$global:warn_count = 0
$global:fail_count = 0
$global:report_lines = @()

# ── 辅助函数 ──
function Write-Result {
    param([string]$Section, [string]$Message, [string]$Status)
    $icon = switch ($Status) {
        "PASS" { [char]0x2705 }
        "WARN" { [char]0x26A0 }
        "FAIL" { [char]0x274C }
        default { "  " }
    }
    $color = switch ($Status) {
        "PASS" { "Green" }
        "WARN" { "Yellow" }
        "FAIL" { "Red" }
        default { "White" }
    }
    $line = "  $icon $Message"
    Write-Host $line -ForegroundColor $color
    $global:report_lines += $line
    switch ($Status) {
        "PASS" { $global:pass_count++ }
        "WARN" { $global:warn_count++ }
        "FAIL" { $global:fail_count++ }
    }
}

function Write-SectionHeader {
    param([string]$Title)
    $line = "`n[$Title]"
    Write-Host $line -ForegroundColor Cyan
    $global:report_lines += $line
}

function Format-FileSize {
    param([long]$Bytes)
    if ($Bytes -ge 1MB) { return "{0:N1} MB" -f ($Bytes / 1MB) }
    elseif ($Bytes -ge 1KB) { return "{0:N0} KB" -f ($Bytes / 1KB) }
    else { return "$Bytes B" }
}

function Test-FileExists {
    param([string]$Path, [string]$Label)
    if (Test-Path $Path) {
        $item = Get-Item $Path
        $size = Format-FileSize -Bytes $item.Length
        if ($item.Length -gt 0) {
            Write-Result -Section "" -Message "$Label 存在 ($size)" -Status "PASS"
        } else {
            Write-Result -Section "" -Message "$Label 存在但为空" -Status "FAIL"
        }
    } else {
        Write-Result -Section "" -Message "$Label 不存在" -Status "FAIL"
    }
}

# ══════════════════════════════════════════════════
#  报告开始
# ══════════════════════════════════════════════════
$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm"
Write-Host "================================================" -ForegroundColor Cyan
Write-Host "     铁律量化 . 红线合规检查报告" -ForegroundColor Cyan
Write-Host "     生成时间: $timestamp" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan
$global:report_lines += "================================================"
$global:report_lines += "     铁律量化 . 红线合规检查报告"
$global:report_lines += "     生成时间: $timestamp"
$global:report_lines += "================================================"

# ══════════════════════════════════════════════════
# S1 数据真实性 - 数据源文件检查
# ══════════════════════════════════════════════════
Write-SectionHeader ([char]0xA7 + "1 数据真实性")

$dataFiles = @("data_final.json", "data_full.json", "data_scored.json")
foreach ($f in $dataFiles) {
    $fullPath = "$DATA_DIR\$f"
    if (Test-Path $fullPath) {
        $item = Get-Item $fullPath
        $size = Format-FileSize -Bytes $item.Length
        if ($item.Length -gt 0) {
            Write-Result -Section "" -Message "$f 存在 ($size)" -Status "PASS"
        } else {
            Write-Result -Section "" -Message "$f 存在但为空文件" -Status "FAIL"
        }
    } else {
        Write-Result -Section "" -Message "$f 不存在" -Status "FAIL"
    }
}

$null = Test-FileExists -Path "$DATA_DIR\industry_map.json" -Label "industry_map.json"
$null = Test-FileExists -Path "$DATA_DIR\sector_data.json" -Label "sector_data.json"

# 1c. 数据源字段标记
Write-SectionHeader ("§1 数据真实性 - 数据源字段标记")

$dataSourceCheckFiles = @("data_final.json", "data_full.json", "data_scored.json")
foreach ($f in $dataSourceCheckFiles) {
    $fullPath = "$DATA_DIR\$f"
    if (-not (Test-Path $fullPath)) { continue }
    try {
        $content = Get-Content $fullPath -Raw -Encoding UTF8
        $json = $content | ConvertFrom-Json
        $itemsToCheck = @()
        if ($json -is [System.Array]) {
            $itemsToCheck = $json
        } elseif ($json -is [PSCustomObject]) {
            if ($json.Stocks) { $itemsToCheck = $json.Stocks }
            elseif ($json.AllStocks) { $itemsToCheck = $json.AllStocks }
            else { $itemsToCheck = @($json) }
        }
        $totalItems = $itemsToCheck.Count
        if ($totalItems -eq 0) { $totalItems = 1; $itemsToCheck = @($json) }
        $hasSourceProp = $false
        $sourcePropCount = 0
        foreach ($item in $itemsToCheck) {
            if ($item -is [PSCustomObject]) {
                $props = $item.PSObject.Properties.Name
                $matchedProps = $props | Where-Object { $_ -match 'Source|来源' }
                if ($matchedProps) {
                    $hasSourceProp = $true
                    $sourcePropCount++
                }
            }
        }
        if ($hasSourceProp) {
            Write-Result -Section "" -Message "$f 包含 Source/来源 字段 ($sourcePropCount/$totalItems 条目)" -Status "PASS"
        } else {
            if ($content -match '"Source"|"来源"|"source"') {
                Write-Result -Section "" -Message "$f 原始文本包含 Source/来源 引用" -Status "PASS"
            } else {
                Write-Result -Section "" -Message "$f 中未找到 Source/来源 字段标记" -Status "WARN"
            }
        }
    } catch {
        Write-Result -Section "" -Message "$f 解析失败: $_" -Status "WARN"
    }
}

# ══════════════════════════════════════════════════
# S3 API 缓存 - 缓存文件检查
# ══════════════════════════════════════════════════
Write-SectionHeader ("§3 API 缓存")

if (Test-Path $CACHE_DIR) {
    $cacheFiles = Get-ChildItem $CACHE_DIR -File
    $cacheCount = $cacheFiles.Count
    $financialCount = @($cacheFiles | Where-Object { $_.Name -match '^Financial' }).Count
    $klineCount = @($cacheFiles | Where-Object { $_.Name -match '^KLine' }).Count
    $otherCount = $cacheCount - $financialCount - $klineCount
    Write-Result -Section "" -Message "data_cache/ 目录存在，包含 $cacheCount 个缓存文件" -Status "PASS"
    if ($financialCount -gt 0 -and $klineCount -gt 0) {
        Write-Result -Section "" -Message "Financial ($financialCount) + KLine ($klineCount) 两类数据均存在" -Status "PASS"
    } elseif ($financialCount -gt 0) {
        Write-Result -Section "" -Message "仅有 Financial ($financialCount) 数据，缺少 KLine" -Status "WARN"
    } elseif ($klineCount -gt 0) {
        Write-Result -Section "" -Message "仅有 KLine ($klineCount) 数据，缺少 Financial" -Status "WARN"
    }
    if ($otherCount -gt 0) {
        Write-Result -Section "" -Message "其他类型缓存文件: $otherCount 个" -Status "WARN"
    }
    $emptyCaches = @($cacheFiles | Where-Object { $_.Length -eq 0 })
    if ($emptyCaches.Count -gt 0) {
        Write-Result -Section "" -Message "发现 $($emptyCaches.Count) 个空缓存文件" -Status "WARN"
    }
} else {
    Write-Result -Section "" -Message "data_cache/ 目录不存在" -Status "FAIL"
    Write-Result -Section "" -Message "  缓存数据不可用 - 数据获取将无缓存兜底" -Status "WARN"
}

# ══════════════════════════════════════════════════
# S4 执行检查清单 - 关键文件完整性
# ══════════════════════════════════════════════════
Write-SectionHeader ("§4 执行检查清单")

$series = @(
    @{ Name = "规则红线"; MdDir = "$BASE\规则红线"; MdPat = '分析的规则红线--Claude_v*.md'; DoxPat = '分析的规则红线--Claude_v*.docx' }
    @{ Name = "每日荐股分析逻辑"; MdDir = "$BASE\每日荐股\分析逻辑"; MdPat = '每日荐股分析逻辑白皮书_v*.md'; DoxPat = '每日荐股分析逻辑白皮书_v*.docx' }
    @{ Name = "次日后评估 (每日荐股)"; MdDir = "$BASE\每日荐股\事后评估"; MdPat = '次日后评估白皮书_v*.md'; DoxPat = '次日后评估白皮书_v*.docx' }
    @{ Name = "重点股票跟踪分析逻辑"; MdDir = "$BASE\重点股票\分析逻辑"; MdPat = '重点股票跟踪分析逻辑白皮书_v*.md'; DoxPat = '重点股票跟踪分析逻辑白皮书_v*.docx' }
    @{ Name = "重点股票次日后评估"; MdDir = "$BASE\重点股票\次日评估"; MdPat = '重点股票次日后评估白皮书_v*.md'; DoxPat = '重点股票次日后评估白皮书_v*.docx' }
)

foreach ($s in $series) {
    $name = $s.Name
    $mdFiles = @(Get-ChildItem (Join-Path $s.MdDir $s.MdPat) -ErrorAction SilentlyContinue | Sort-Object Name -Descending)
    $dxFiles = @(Get-ChildItem (Join-Path $s.MdDir $s.DoxPat) -ErrorAction SilentlyContinue | Sort-Object Name -Descending)
    $mdVersions = @{}; $dxVersions = @{}
    foreach ($f in $mdFiles) { if ($f.Name -match '_v(\d+\.\d+(?:\.\d+)?)\.md$') { $mdVersions[$matches[1]] = $f.FullName } }
    foreach ($f in $dxFiles) { if ($f.Name -match '_v(\d+\.\d+(?:\.\d+)?)\.docx$') { $dxVersions[$matches[1]] = $f.FullName } }
    $allV = ($mdVersions.Keys + $dxVersions.Keys) | Sort-Object -Unique -Descending {
        $parts = $_ -split '\.'
        $padded = ($parts + @('0','0'))[0..2] | ForEach-Object { $_.PadLeft(6,'0') }
        [string]::Join('.', $padded)
    }
    $mdOnly = @(); $dxOnly = @(); $paired = @()
    foreach ($v in $allV) {
        $hMd = $mdVersions.ContainsKey($v); $hDx = $dxVersions.ContainsKey($v)
        if ($hMd -and $hDx) { $paired += $v }
        elseif ($hMd -and -not $hDx) { $mdOnly += $v }
        elseif (-not $hMd -and $hDx) { $dxOnly += $v }
    }
    $latest = if ($allV.Count -gt 0) { $allV[0] } else { "" }
    if ($paired.Count -gt 0) {
        Write-Result -Section "" -Message "$name v$latest -- 版本配对: .md + .docx 均存在" -Status "PASS"
    }
    if ($mdOnly.Count -gt 0) {
        Write-Result -Section "" -Message "$name -- .md 存在但缺少 .docx 的版本: v$($mdOnly -join ', v')" -Status "WARN"
    }
    if ($dxOnly.Count -gt 0) {
        Write-Result -Section "" -Message "$name -- .docx 存在但缺少 .md 的版本: v$($dxOnly -join ', v')" -Status "WARN"
    }
    if ($allV.Count -eq 0) {
        Write-Result -Section "" -Message "$name -- 未找到任何版本文件" -Status "FAIL"
    }
}

# 4b. CHANGELOG.md
Write-SectionHeader ("§4 执行检查清单 - CHANGELOG")

$changelogs = @(
    "$BASE\规则红线\分析的规则红线--Claude_CHANGELOG.md"
    "$BASE\每日荐股\分析逻辑\每日荐股分析逻辑白皮书_CHANGELOG.md"
    "$BASE\每日荐股\事后评估\次日后评估白皮书_CHANGELOG.md"
    "$BASE\重点股票\分析逻辑\重点股票跟踪分析逻辑白皮书_CHANGELOG.md"
    "$BASE\重点股票\次日评估\重点股票次日后评估白皮书_CHANGELOG.md"
)
foreach ($cl in $changelogs) {
    $label = Split-Path $cl -Leaf
    if (Test-Path $cl) {
        $item = Get-Item $cl
        if ($item.Length -gt 100) {
            Write-Result -Section "" -Message "$label 存在 ($(Format-FileSize -Bytes $item.Length))" -Status "PASS"
        } else {
            Write-Result -Section "" -Message "$label 存在但内容过短 ($(Format-FileSize -Bytes $item.Length))" -Status "WARN"
        }
    } else {
        Write-Result -Section "" -Message "$label 不存在" -Status "FAIL"
    }
}

# CHANGELOG 格式深度检查（非 Quick 模式）
if (-not $Quick) {
    $clRequiredTypes = @('Added', 'Changed', 'Deprecated', 'Removed', 'Fixed', 'Security')
    foreach ($cl in $changelogs) {
        if (-not (Test-Path $cl)) { continue }
        $clContent = Get-Content $cl -Raw -Encoding UTF8
        $clLabel = Split-Path $cl -Leaf
        # 检查最新版本条目是否有负责人行
        if ($clContent -match '## \[v?[\d\.]+\]') {
            $afterFirst = $clContent -split '## \[', 2
            if ($afterFirst.Count -ge 2) {
                $firstEntry = $afterFirst[1] -split '## \[', 2
                $entryText = $firstEntry[0]
                if ($entryText -notmatch '### 负责人') {
                    Write-Result -Section "" -Message "$clLabel — 最新版本条目缺少「负责人」行" -Status "WARN"
                }
            }
        }
        # 检查是否使用了标准变更类型标记
        $lines = $clContent -split "`n"
        $foundTypes = @{}
        foreach ($line in $lines) {
            $trimmed = $line.Trim()
            foreach ($t in $clRequiredTypes) {
                if ($trimmed -eq "### $t") { $foundTypes[$t] = $true }
            }
        }
        if ($foundTypes.Count -eq 0) {
            Write-Result -Section "" -Message "$clLabel — 未使用标准变更类型标记 (Added/Changed/Fixed 等)" -Status "WARN"
        }
    }
}

# 4c. 文档版本索引
Write-SectionHeader ("§4 执行检查清单 - 版本索引")
$vix = "$BASE\规则红线\文档版本索引.md"
if (Test-Path $vix) {
    $item = Get-Item $vix
    if ($item.Length -gt 200) {
        Write-Result -Section "" -Message "文档版本索引.md 存在 ($(Format-FileSize -Bytes $item.Length))" -Status "PASS"
    } else {
        Write-Result -Section "" -Message "文档版本索引.md 存在但内容过短" -Status "WARN"
    }
} else {
    Write-Result -Section "" -Message "文档版本索引.md 不存在" -Status "FAIL"
}

# ── Quick 模式：§4 检查完成后退出 ──
if ($Quick) {
    Write-Host ""
    Write-Host "============================================" -ForegroundColor Cyan
    Write-Host "[Quick] 预检完成: PASS $($global:pass_count) / WARN $($global:warn_count) / FAIL $($global:fail_count)" -ForegroundColor $(if ($global:fail_count -gt 0) { "Red" } elseif ($global:warn_count -gt 0) { "Yellow" } else { "Green" })
    exit $(if ($global:fail_count -gt 0) { 1 } else { 0 })
}

# ══════════════════════════════════════════════════
# S5.4 版本管理 - 版本一致性检查
# ══════════════════════════════════════════════════
Write-SectionHeader ("§5.4 版本管理")
Write-SectionHeader ("§5.4 版本管理 - 文件内外版本一致性")

$versionFiles = @(
    "$BASE\规则红线\分析的规则红线--Claude_v1.13.md"
    "$BASE\每日荐股\分析逻辑\每日荐股分析逻辑白皮书_v2.9.md"
    "$BASE\每日荐股\分析逻辑\每日荐股分析逻辑白皮书_v2.3.md"
    "$BASE\每日荐股\分析逻辑\每日荐股分析逻辑白皮书_v2.1.md"
    "$BASE\每日荐股\事后评估\次日后评估白皮书_v1.6.md"
    "$BASE\每日荐股\事后评估\次日后评估白皮书_v1.4.md"
    "$BASE\重点股票\分析逻辑\重点股票跟踪分析逻辑白皮书_v3.0.md"
    "$BASE\重点股票\分析逻辑\重点股票跟踪分析逻辑白皮书_v2.0.md"
    "$BASE\重点股票\次日评估\重点股票次日后评估白皮书_v1.4.md"
    "$BASE\重点股票\次日评估\重点股票次日后评估白皮书_v1.3.md"
)

foreach ($f in $versionFiles) {
    if (-not (Test-Path $f)) { continue }
    $leaf = Split-Path $f -Leaf
    $fnVer = ""
    if ($leaf -match '_v(\d+\.\d+)\.md$') { $fnVer = $matches[1] }
    $lines = Get-Content $f -TotalCount 20 -Encoding UTF8
    $inVer = ""
    # Pattern: **版本**：vX.Y
    foreach ($ln in $lines) {
        if ($ln -match '\*\*版本\*\*.*v(\d+\.\d+)') { $inVer = $matches[1]; break }
    }
    # Pattern: 版本：vX.Y
    if (-not $inVer) {
        foreach ($ln in $lines) {
            if ($ln -match '版本[：:]\s*v(\d+\.\d+)') { $inVer = $matches[1]; break }
        }
    }
    # Pattern: 当前版本: vX.Y
    if (-not $inVer) {
        foreach ($ln in $lines) {
            if ($ln -match '当前版本[：:]\s*v(\d+\.\d+)') { $inVer = $matches[1]; break }
        }
    }
    # Pattern: # Header vX.Y
    if (-not $inVer) {
        foreach ($ln in $lines) {
            if ($ln -match '#.*v(\d+\.\d+)') { $inVer = $matches[1]; break }
        }
    }
    if ($fnVer -and $inVer) {
        if ($fnVer -eq $inVer) {
            Write-Result -Section "" -Message "$leaf -- 文件名 v$fnVer = 文档内 v$inVer" -Status "PASS"
        } else {
            Write-Result -Section "" -Message "$leaf -- 文件名 v$fnVer != 文档内 v$inVer" -Status "FAIL"
        }
    } elseif ($fnVer -and -not $inVer) {
        Write-Result -Section "" -Message "$leaf -- 文件名 v$fnVer，但未找到内部版本声明" -Status "WARN"
    }
}

# 5b. 版本索引对比
Write-SectionHeader ("§5.4 版本管理 - 版本索引与实际情况对比")

$idxMap = @{
    "规则红线" = "v1.13"
    "每日荐股分析逻辑" = "v2.9"
    "次日后评估 (每日荐股)" = "v1.6"
    "重点股票跟踪分析逻辑" = "v3.0"
    "重点股票次日后评估" = "v1.4"
}

foreach ($s in $series) {
    $name = $s.Name
    $mdFiles = @(Get-ChildItem (Join-Path $s.MdDir $s.MdPat) -ErrorAction SilentlyContinue | Sort-Object Name -Descending)
    $dxFiles = @(Get-ChildItem (Join-Path $s.MdDir $s.DoxPat) -ErrorAction SilentlyContinue | Sort-Object Name -Descending)
    $allV = @()
    foreach ($f in $mdFiles) { if ($f.Name -match '_v(\d+\.\d+)') { $allV += $matches[1] } }
    foreach ($f in $dxFiles) { if ($f.Name -match '_v(\d+\.\d+)') { $allV += $matches[1] } }
    $actual = if ($allV.Count -gt 0) { ($allV | Sort-Object -Descending { [version]($_ + '.0') })[0] } else { "" }
    $idxV = $idxMap[$name]
    if ($actual) {
        if ($idxV -and "v$actual" -ne $idxV) {
            Write-Result -Section "" -Message "版本索引: $name $idxV，实际最新: v$actual -- 版本索引未更新" -Status "WARN"
        } elseif ($idxV) {
            Write-Result -Section "" -Message "版本索引: $name $idxV = 实际 v$actual" -Status "PASS"
        }
    }
}

# 5c. 最新版本汇总
Write-SectionHeader ("§5.4 版本管理 - 最新版本汇总")
foreach ($s in $series) {
    $mdFiles = @(Get-ChildItem (Join-Path $s.MdDir $s.MdPat) -ErrorAction SilentlyContinue | Sort-Object Name -Descending)
    $dxFiles = @(Get-ChildItem (Join-Path $s.MdDir $s.DoxPat) -ErrorAction SilentlyContinue | Sort-Object Name -Descending)
    $allV = @()
    foreach ($f in $mdFiles) { if ($f.Name -match '_v(\d+\.\d+)') { $allV += $matches[1] } }
    foreach ($f in $dxFiles) { if ($f.Name -match '_v(\d+\.\d+)') { $allV += $matches[1] } }
    $actual = if ($allV.Count -gt 0) { ($allV | Sort-Object -Descending { [version]($_ + '.0') })[0] } else { "N/A" }
    Write-Host "  $($s.Name): v$actual" -ForegroundColor White
    $global:report_lines += "  $($s.Name): v$actual"
}

# ══════════════════════════════════════════════════
# 附加检查 - 核心脚本文件
# ══════════════════════════════════════════════════
Write-SectionHeader "附加检查 - 核心文件"

$scripts = @(
    "$BASE\代码文件\数据\data_final.json"
    "$BASE\代码文件\数据\data_full.json"
    "$BASE\代码文件\数据\data_scored.json"
    "$BASE\代码文件\数据\stock_data_raw.json"
    "$BASE\代码文件\每日荐股\事后评估\gen_eval_doc.ps1"
    "$BASE\代码文件\规则红线\gen_redlines_doc.ps1"
    "$BASE\代码文件\规则红线\check_redlines.ps1"
    "$BASE\代码文件\规则红线\check_report_style.ps1"
    "$BASE\代码文件\tools\md_to_docx.py"
    "$BASE\规则红线\报告样式基线_v1.0.md"
)
foreach ($scr in $scripts) {
    $label = Split-Path $scr -Leaf
    if (Test-Path $scr) {
        $item = Get-Item $scr
        Write-Result -Section "" -Message "$label 存在 ($(Format-FileSize -Bytes $item.Length))" -Status "PASS"
    } else {
        Write-Result -Section "" -Message "$label 不存在" -Status "FAIL"
    }
}

# ══════════════════════════════════════════════════
# 总体判定
# ══════════════════════════════════════════════════
Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
$global:report_lines += ""
$global:report_lines += "============================================"

$total = $global:pass_count + $global:warn_count + $global:fail_count
if ($global:fail_count -eq 0 -and $global:warn_count -eq 0) {
    $verdict = "[PASS] 完全合规"
    $extra = "全部通过 ($global:pass_count/$total)"
    $vColor = "Green"
} elseif ($global:fail_count -eq 0) {
    $verdict = "[WARN] 基本合规 (存在 $($global:warn_count) 个警告)"
    $extra = "通过 $($global:pass_count)/$total，警告 $($global:warn_count)"
    $vColor = "Yellow"
} else {
    $verdict = "[FAIL] 不合规 (存在 $($global:warn_count) 个警告，$($global:fail_count) 个违规)"
    $extra = "通过 $($global:pass_count)/$total，警告 $($global:warn_count)，违规 $($global:fail_count)"
    $vColor = "Red"
}
Write-Host "总体判定: $verdict" -ForegroundColor $vColor
Write-Host $extra -ForegroundColor $vColor
Write-Host "需手动修正后再提交。" -ForegroundColor $vColor
$global:report_lines += "总体判定: $verdict"
$global:report_lines += $extra
$global:report_lines += "需手动修正后再提交。"

# 保存报告
$global:report_lines -join "`r`n" | Out-File -FilePath $REPORT_FILE -Encoding UTF8
Write-Host ""
Write-Host "报告已保存: $REPORT_FILE" -ForegroundColor Gray

# 退出码
if ($global:fail_count -gt 0) { exit 1 }
exit 0
