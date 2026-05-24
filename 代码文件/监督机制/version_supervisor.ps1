<#
.SYNOPSIS
    铁律量化 · 白皮书版本监督器
.DESCRIPTION
    自动检查4份白皮书的版本一致性：
    - 文件头版本号 vs 文件名版本号
    - 版本历史表顺序
    - CHANGELOG 版本倒序
    - DOCX 文件是否存在
    - 跨文档引用版本号是否过时
    - 文档版本索引是否最新
.NOTES
    版本: v1.0
    用法:
        .\version_supervisor.ps1          完整检查
        .\version_supervisor.ps1 -Quick   快速检查（仅报错）
    退出码: 0 = 正常, 1 = 有问题
#>
param(
    [switch]$Quick,
    [switch]$CrossCheck
)

# ═════ 配置：白皮书清单 ═══════════════════════════════════════
$WHITEPAPERS = @(
    @{
        Name     = '每日荐股分析逻辑白皮书'
        Dir      = '每日荐股\分析逻辑'
        Current  = 'v2.9'
        Date     = '2026-05-23'
    }
    @{
        Name     = '次日后评估白皮书'
        Dir      = '每日荐股\事后评估'
        Current  = 'v1.6'
        Date     = '2026-05-23'
    }
    @{
        Name     = '重点股票跟踪分析逻辑白皮书'
        Dir      = '重点股票\分析逻辑'
        Current  = 'v3.0'
        Date     = '2026-05-23'
    }
    @{
        Name     = '重点股票次日后评估白皮书'
        Dir      = '重点股票\次日评估'
        Current  = 'v1.4'
        Date     = '2026-05-22'
    }
    @{
        Name     = '分析的规则红线--Claude'
        Dir      = '规则红线'
        Current  = 'v1.14'
        Date     = '2026-05-24'
    }
    @{
        Name     = '模拟交易白皮书'
        Dir      = '模拟交易'
        Current  = 'v1.6'
        Date     = '2026-05-24'
    }
)

# ═════ 配置：团队名册 ═══════════════════════════════════════
$ROSTER = @{
    Name    = '团队名册'
    Dir     = '项目成员'
    Current = 'v1.7'
    Date    = '2026-05-23'
}

$ROOT = "C:\Users\34269\Documents\Claude\股票分析"
$ERRORS = @()
$WARNS  = @()

# ═════ 辅助函数 ══════════════════════════════════════════════
# SemVer 比较函数：支持 vX.Y 和 vX.Y.Z 格式
function Compare-Version([string]$a, [string]$b) {
    $a = $a.TrimStart('v'); $b = $b.TrimStart('v')
    $ap = ($a -split '\.') + @('0','0'); $bp = ($b -split '\.') + @('0','0')
    for ($i = 0; $i -lt 3; $i++) {
        $ai = [int]::Parse($ap[$i]); $bi = [int]::Parse($bp[$i])
        if ($ai -lt $bi) { return -1 }
        if ($ai -gt $bi) { return 1 }
    }
    return 0
}
function Is-Older([string]$a, [string]$b) { (Compare-Version $a $b) -lt 0 }

function Write-Result($ok, $msg) {
    if ($ok) {
        if (-not $Quick) { Write-Host "  ✅ $msg" -ForegroundColor Green }
    } else {
        Write-Host "  ❌ $msg" -ForegroundColor Red
        $script:ERRORS += $msg
    }
}
function Write-Warn($msg) {
    Write-Host "  ⚠️  $msg" -ForegroundColor Yellow
    $script:WARNS += $msg
}

# ═════ 1. 检查文件头版本号 vs 文件名 ═══════════════════════
function Check-HeaderVersion {
    Write-Host "`n[1/7] 文件头版本号 vs 文件名一致性" -ForegroundColor Cyan

    foreach ($wp in $WHITEPAPERS) {
        $path = "$ROOT\$($wp.Dir)\$($wp.Name)_$($wp.Current).md"
        if (-not (Test-Path $path)) {
            Write-Result $false "找不到文件: $path"
            continue
        }
        # 检查版本号出现在前5行
        $header = Get-Content $path -TotalCount 5 -Encoding UTF8
        $foundVersion = $header | Select-String $wp.Current
        if ($foundVersion) {
            Write-Result $true "$($wp.Name) $($wp.Current) — 版本号一致"
        } else {
            Write-Result $false "$($wp.Name) $($wp.Current) — 文件头未找到版本号 '$($wp.Current)'"
        }
    }
}

# ═════ 2. 检查版本历史表顺序 ══════════════════════════════
function Check-VersionHistory {
    Write-Host "`n[2/7] 版本历史表 — 倒序检查" -ForegroundColor Cyan

    foreach ($wp in $WHITEPAPERS) {
        $path = "$ROOT\$($wp.Dir)\$($wp.Name)_$($wp.Current).md"
        $content = Get-Content $path -Encoding UTF8

        # 找版本历史表
        $inTable = $false
        $versions = @()
        foreach ($line in $content) {
            if ($line -match '^\|.*版本.*\|') { $inTable = $true; continue }
            if ($inTable -and $line -match '^\|:') { continue }
            if ($inTable -and $line -match '^\| *v') {
                $v = [regex]::Match($line, 'v\d+\.\d+(?:\.\d+)?').Value
                if ($v) { $versions += $v }
            }
            if ($inTable -and (-not ($line -match '^\|') -or $line -match '^---')) { $inTable = $false }
        }

        if ($versions.Count -ge 2) {
            # 检查是否为倒序
            $ok = $true
            for ($i = 0; $i -lt $versions.Count - 1; $i++) {
                if (Is-Older $versions[$i] $versions[$i+1]) { $ok = $false; break }
            }
            if ($ok) {
                Write-Result $true "$($wp.Name) — 版本历史倒序正确 ($($versions -join ' → '))"
            } else {
                Write-Result $false "$($wp.Name) — 版本历史非倒序: $($versions -join ' → ')"
            }
        } else {
            Write-Warn "$($wp.Name) — 版本历史表条目不足 ($($versions.Count) 条)"
        }
    }
}

# ═════ 3. 检查 CHANGELOG 版本倒序 ══════════════════════════
function Check-ChangelogOrder {
    Write-Host "`n[3/7] CHANGELOG 版本倒序检查" -ForegroundColor Cyan

    foreach ($wp in $WHITEPAPERS) {
        $clPath = "$ROOT\$($wp.Dir)\$($wp.Name)_CHANGELOG.md"
        if (-not (Test-Path $clPath)) {
            Write-Result $false "CHANGELOG 不存在: $clPath"
            continue
        }
        $content = Get-Content $clPath -Encoding UTF8
        $versions = @()
        foreach ($line in $content) {
            if ($line -match '^## v(\d+\.\d+(?:\.\d+)?)') {
                $versions += $matches[1]
            }
        }
        if ($versions.Count -ge 2) {
            $ok = $true
            for ($i = 0; $i -lt $versions.Count - 1; $i++) {
                if (Is-Older $versions[$i] $versions[$i+1]) { $ok = $false; break }
            }
            if ($ok) {
                Write-Result $true "$($wp.Name) — CHANGELOG 倒序正确 ($($versions -join ' → '))"
            } else {
                Write-Result $false "$($wp.Name) — CHANGELOG 非倒序: $($versions -join ' → ')"
            }
        } else {
            Write-Warn "$($wp.Name) — CHANGELOG 版本条目不足 ($($versions.Count) 条)"
        }
    }
}

# ═════ 4. 检查 DOCX 文件是否存在 ═══════════════════════════
function Check-DocxExists {
    Write-Host "`n[4/7] DOCX 文件存在性检查" -ForegroundColor Cyan

    foreach ($wp in $WHITEPAPERS) {
        $docx = "$ROOT\$($wp.Dir)\$($wp.Name)_$($wp.Current).docx"
        if (Test-Path $docx) {
            Write-Result $true "$($wp.Name) $($wp.Current).docx 存在"
        } else {
            Write-Result $false "$($wp.Name) $($wp.Current).docx 缺失！"
        }
    }
}

# ═════ 5. 检查 CHANGELOG 头部路径 ═════════════════════════
function Check-ChangelogPath {
    Write-Host "`n[5/7] CHANGELOG 头部路径版本号检查" -ForegroundColor Cyan

    foreach ($wp in $WHITEPAPERS) {
        $clPath = "$ROOT\$($wp.Dir)\$($wp.Name)_CHANGELOG.md"
        if (-not (Test-Path $clPath)) { continue }
        $header = Get-Content $clPath -TotalCount 5 -Encoding UTF8
        foreach ($line in $header) {
            if ($line -match '_v(\d+\.\d+)') {
                $refVersion = $matches[1]
                $refFull = "v$refVersion"
                if ($refFull -ne $wp.Current) {
                    Write-Result $false "$($wp.Name) CHANGELOG 头部引用 v$refVersion，当前应为 $($wp.Current)"
                } else {
                    Write-Result $true "$($wp.Name) CHANGELOG 头部路径正确"
                }
                break
            }
        }
    }
}

# ═════ 6. 检查跨文档引用 ═════════════════════════════════
function Check-CrossReferences {
    Write-Host "`n[6/7] 跨文档版本号引用检查" -ForegroundColor Cyan

    $anyIssue = $false

    foreach ($wp in $WHITEPAPERS) {
        $path = "$ROOT\$($wp.Dir)\$($wp.Name)_$($wp.Current).md"
        if (-not (Test-Path $path)) { continue }
        $rawContent = Get-Content $path -Raw -Encoding UTF8

        # 过滤掉版本历史表行（|开头）和代码块（```之间），仅检查正文引用
        $lines = $rawContent -split "`n"
        $bodyLines = @()
        $inCodeBlock = $false
        foreach ($line in $lines) {
            $trimmed = $line.Trim()
            if ($trimmed -match '^```') { $inCodeBlock = -not $inCodeBlock; continue }
            if ($inCodeBlock) { continue }
            if ($trimmed -match '^\|') { continue }  # 跳过表格行（含版本历史表）
            $bodyLines += $line
        }
        $content = $bodyLines -join "`n"

        # 检查是否引用了其他白皮书的旧版本号（按名称长度降序，避免短名误匹配长名）
        $sortedOthers = $WHITEPAPERS | Where-Object { $_.Name -ne $wp.Name } | Sort-Object { $_.Name.Length } -Descending
        $matchedPositions = @{}  # 记录已匹配位置，避免短名重复匹配长名的同一位置
        foreach ($other in $sortedOthers) {
            $escapedName = [regex]::Escape($other.Name)
            $refPattern = "${escapedName}_v(\d+\.\d+(?:\.\d+)?)"
            $refMatches = [regex]::Matches($content, $refPattern)
            foreach ($m in $refMatches) {
                # 跳过已被更长名称匹配的位置
                $pos = $m.Index
                $alreadyMatched = $false
                foreach ($range in $matchedPositions.GetEnumerator()) {
                    if ($pos -ge $range.Key -and $pos -lt ($range.Key + $range.Value)) {
                        $alreadyMatched = $true; break
                    }
                }
                if ($alreadyMatched) { continue }
                $matchedPositions[$m.Index] = $m.Length

                $refVersion = "v$($m.Groups[1].Value)"
                if ($refVersion -ne $other.Current) {
                    Write-Result $false "$($wp.Name) $($wp.Current) — 正文引用 $($other.Name) $refVersion，应为 $($other.Current)"
                    $anyIssue = $true
                }
            }
        }
        # 检查是否引用了旧版规则红线
        if ($content -match '规则红线.*?_v(\d+\.\d+(?:\.\d+)?)') {
            $refRedline = "v$($matches[1])"
            $redlineCurrent = ($WHITEPAPERS | Where-Object { $_.Name -match '规则红线' }).Current
            if ($refRedline -ne $redlineCurrent) {
                Write-Result $false "$($wp.Name) $($wp.Current) — 正文引用 规则红线 $refRedline，应为 $redlineCurrent"
                $anyIssue = $true
            }
        }
    }

    if (-not $anyIssue) {
        Write-Host "  ✅ 所有跨文档引用版本号正确" -ForegroundColor Green
    }
}

# ═════ 7. 检查文档版本索引 ════════════════════════════════
function Check-VersionIndex {
    Write-Host "`n[7/7] 文档版本索引检查" -ForegroundColor Cyan

    $idxPath = "$ROOT\规则红线\文档版本索引.md"
    if (-not (Test-Path $idxPath)) {
        Write-Result $false "文档版本索引不存在: $idxPath"
        return
    }
    $content = Get-Content $idxPath -Encoding UTF8

    foreach ($wp in $WHITEPAPERS) {
        $found = $false
        $correct = $false
        foreach ($line in $content) {
            if ($line -match [regex]::Escape($wp.Name) -and $line -match '\|\s*✅\s*当前\s*\|') {
                $found = $true
                if ($line -match [regex]::Escape($wp.Current)) {
                    $correct = $true
                }
                break
            }
        }
        if ($found -and $correct) {
            Write-Result $true "$($wp.Name) — 索引中版本正确 ($($wp.Current))"
        } elseif ($found) {
            Write-Result $false "$($wp.Name) — 索引中版本标记为当前但版本号不是 $($wp.Current)"
        } else {
            Write-Result $false "$($wp.Name) — 索引中未找到当前版本标记"
        }
    }
}

# ═════ 8. 团队名册版本号检查（§5.4.8.2 第6条）═════════════
function Check-RosterVersion {
    Write-Host "`n[8/9] 团队名册版本号检查" -ForegroundColor Cyan

    # 8.1 检查当前版本文件是否存在
    $rosterMd = "$ROOT\$($ROSTER.Dir)\$($ROSTER.Name)_$($ROSTER.Current).md"
    if (Test-Path $rosterMd) {
        # 检查文件头版本号
        $header = Get-Content $rosterMd -TotalCount 5 -Encoding UTF8
        $foundVersion = $header | Select-String $ROSTER.Current
        if ($foundVersion) {
            Write-Result $true "$($ROSTER.Name) $($ROSTER.Current) — 文件存在且版本号一致"
        } else {
            Write-Result $false "$($ROSTER.Name) $($ROSTER.Current) — 文件头未找到版本号 '$($ROSTER.Current)'"
        }
    } else {
        Write-Result $false "$($ROSTER.Name) — 当前版本文件不存在: $rosterMd"
    }

    # 8.2 检查双格式同步：.xlsx 是否存在
    $rosterXlsx = "$ROOT\$($ROSTER.Dir)\$($ROSTER.Name)_$($ROSTER.Current).xlsx"
    if (Test-Path $rosterXlsx) {
        Write-Result $true "$($ROSTER.Name) $($ROSTER.Current).xlsx — 双格式同步正常"
    } else {
        Write-Result $false "$($ROSTER.Name) $($ROSTER.Current).xlsx 缺失！须从.md同步生成（§5.4.8.4）"
    }

    # 8.3 检查是否存在无版本号文件（违规）
    $unversionedMd = "$ROOT\$($ROSTER.Dir)\$($ROSTER.Name).md"
    $unversionedXlsx = "$ROOT\$($ROSTER.Dir)\$($ROSTER.Name).xlsx"
    if (Test-Path $unversionedMd) {
        Write-Result $false "$($ROSTER.Name).md — 存在无版本号文件！应删除，当前版本为 $($ROSTER.Name)_$($ROSTER.Current).md"
    }
    if (Test-Path $unversionedXlsx) {
        Write-Result $false "$($ROSTER.Name).xlsx — 存在无版本号文件！应删除，当前版本为 $($ROSTER.Name)_$($ROSTER.Current).xlsx"
    }

    # 8.4 检查文档版本索引中的名册版本是否一致
    $idxPath = "$ROOT\规则红线\文档版本索引.md"
    if (Test-Path $idxPath) {
        $idxContent = Get-Content $idxPath -Encoding UTF8
        $rosterInIndex = $false
        foreach ($line in $idxContent) {
            if ($line -match [regex]::Escape($ROSTER.Name) -and $line -match '\|\s*v?(\d+\.\d+)') {
                $rosterInIndex = $true
                $indexVersion = "v$($matches[1])"
                if ($indexVersion -eq $ROSTER.Current) {
                    Write-Result $true "文档版本索引中 $($ROSTER.Name) 版本一致 ($($ROSTER.Current))"
                } else {
                    Write-Result $false "文档版本索引中 $($ROSTER.Name) 版本为 $indexVersion，应为 $($ROSTER.Current)"
                }
                break
            }
        }
        if (-not $rosterInIndex) {
            Write-Result $false "文档版本索引中未找到 $($ROSTER.Name) 条目"
        }
    }
}

# ═════ 9. CHANGELOG 交叉验证（-CrossCheck）═════════════════
function Invoke-CrossCheck {
    Write-Host "`n[9/9] CHANGELOG 交叉验证 — 条目声明 vs 代码事实" -ForegroundColor Cyan
    Write-Host "  (检测最新CHANGELOG条目中的变更声明是否与代码一致)" -ForegroundColor DarkGray
    Write-Host ""

    $anyIssue = $false
    $codeDir = "$ROOT\代码文件"

    # 从CHANGELOG行中提取简短的代码关键词（反引号内、文件路径、驼峰名）
    function Extract-SearchTerms($text) {
        $terms = @()
        # 反引号内的内容（如 `VetoedStocks`、`FullTable`）
        if ($text -match '`([^`]+)`') { $terms += $matches[1] }
        # .py/.ps1/.psm1 文件名
        if ($text -match '([\w_\-]+\.(?:py|ps1|psm1))') { $terms += $matches[1] }
        # 双引号内的简短内容（2-6个字）
        if ($text -match '"([^"]{2,10})"') { $terms += $matches[1] }
        # 函数/变量名风格（驼峰或含下划线，不含空格，>3字符）
        if ($text -match '\b([A-Z][a-zA-Z]+[a-z][A-Z][a-zA-Z]+)\b') { $terms += $matches[1] }
        if ($text -match '\b([a-z]+_[a-z_]{3,})\b') { $terms += $matches[1] }
        return $terms | Where-Object { $_ -and $_.Length -ge 4 -and $_ -notin $STOP_WORDS } | Select-Object -Unique
    }

    # 判断是"移除"还是"新增"类型
    function Get-ChangeType($text) {
        if ($text -match '移除|删除|去除|不再') { return 'removed' }
        if ($text -match '新增|添加|增加|新[增建]') { return 'added' }
        return 'modified'
    }

    # 常见停用词（不验证的通用词）
    $STOP_WORDS = @('price', 'data', 'Users', 'Claude', 'Date', 'Name', 'Code', 'Index', 'line', 'color',
                    'mode', 'path', 'file', 'type', 'size', 'time', 'text', 'open', 'close', 'high', 'low',
                    'start', 'end', 'delta', 'range', 'table', 'html', 'json', 'pdf', 'docx',
                    '移除', '新增', '添加', '修改', 'gen_daily_html', 'batch_data_collector',
                    'scoring_engine_v2', 'scoring_engine', 'version_supervisor', 'check_redlines')

    foreach ($wp in $WHITEPAPERS) {
        $clPath = "$ROOT\$($wp.Dir)\$($wp.Name)_CHANGELOG.md"
        if (-not (Test-Path $clPath)) { continue }

        $content = Get-Content $clPath -Encoding UTF8
        $latestEntry = ""
        $inLatest = $false
        foreach ($line in $content) {
            if ($line -match '^## v\d+') {
                if ($inLatest) { break }
                $inLatest = $true; continue
            }
            if ($inLatest) { $latestEntry += "$line`n" }
        }
        if (-not $latestEntry) { continue }

        Write-Host "  >> $($wp.Name)" -ForegroundColor Green

        $lines = $latestEntry -split "`n"
        $lineChecked = 0
        foreach ($line in $lines) {
            $trimmed = $line.Trim()
            if ($trimmed -notmatch '^- ') { continue }

            $changeType = Get-ChangeType $trimmed
            $terms = Extract-SearchTerms $trimmed
            if (-not $terms) { continue }

            $lineChecked++
            $actionLabel = @{ 'removed'='已移除'; 'added'='已新增'; 'modified'='已修改' }[$changeType]

            foreach ($term in $terms) {
                # 如果"移除"声明匹配到的是文件名本身，免检（常见句式："xxx.py：移除aaa"）
                if ($changeType -eq 'removed' -and $term -match '\.(py|ps1|psm1|md)$') { continue }

                # 搜索代码文件 + 白皮书文档（排除CHANGELOG自身避免自引用）
                $searchDirs = @($codeDir, "$ROOT\每日荐股", "$ROOT\重点股票", "$ROOT\规则红线")
                $fileMatches = $searchDirs | ForEach-Object {
                    Get-ChildItem -Path $_ -Recurse -Include *.py,*.ps1,*.psm1,*.md -ErrorAction SilentlyContinue
                } | Where-Object { $_.Name -notmatch 'CHANGELOG' } |
                  Select-String -Pattern $term -SimpleMatch -ErrorAction SilentlyContinue
                $matchCount = ($fileMatches | Measure-Object).Count

                if ($changeType -eq 'removed' -and $matchCount -gt 0) {
                    Write-Host "    ❌ '$actionLabel $term' 但代码中仍出现 $matchCount 次" -ForegroundColor Red
                    $anyIssue = $true
                } elseif ($changeType -eq 'added' -and $matchCount -eq 0) {
                    Write-Host "    ❌ '$actionLabel $term' 但代码中未找到" -ForegroundColor Red
                    $anyIssue = $true
                } elseif ($matchCount -gt 0) {
                    Write-Host "    ✅ '$term' 代码中匹配 $matchCount 次" -ForegroundColor Green
                }
            }
        }

        if ($lineChecked -eq 0) {
            Write-Host "    (无可提取的代码关键词)" -ForegroundColor DarkGray
        }
        Write-Host ""
    }

    if (-not $anyIssue) {
        Write-Host "  ✅ CHANGELOG 交叉验证全部通过！" -ForegroundColor Green
    } else {
        Write-Host "  ⚠️  发现不一致，请核实CHANGELOG条目" -ForegroundColor Yellow
    }

    return (-not $anyIssue)
}

# ═════ 主流程 ══════════════════════════════════════════════
if ($CrossCheck) {
    Write-Host "╔═══════════════════════════════════════════════╗" -ForegroundColor Cyan
    Write-Host "║   铁律量化 · CHANGELOG 交叉验证                ║" -ForegroundColor Cyan
    Write-Host "╚═══════════════════════════════════════════════╝" -ForegroundColor Cyan
    $ok = Invoke-CrossCheck
    if ($ok) { exit 0 } else { exit 1 }
    return
}

Write-Host "╔═══════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║   铁律量化 · 白皮书版本监督器 v1.0            ║" -ForegroundColor Cyan
Write-Host "╚═══════════════════════════════════════════════╝" -ForegroundColor Cyan

Check-HeaderVersion
Check-VersionHistory
Check-ChangelogOrder
Check-DocxExists
Check-ChangelogPath
Check-CrossReferences
Check-VersionIndex
Check-RosterVersion

# ═════ 汇总 ═══════════════════════════════════════════════
Write-Host "`n" ("=" * 50) -ForegroundColor Cyan
Write-Host "检查完成: 错误 $($ERRORS.Count)  |  警告 $($WARNS.Count)" -ForegroundColor Cyan

if ($ERRORS.Count -gt 0) {
    Write-Host "`n❌ 需要修复的问题:" -ForegroundColor Red
    foreach ($e in $ERRORS) { Write-Host "  - $e" -ForegroundColor Red }
    if ($Quick) { exit 1 }
}
if ($WARNS.Count -gt 0 -and -not $Quick) {
    Write-Host "`n⚠️  建议关注的问题:" -ForegroundColor Yellow
    foreach ($w in $WARNS) { Write-Host "  - $w" -ForegroundColor Yellow }
}

if ($ERRORS.Count -eq 0) {
    Write-Host "`n✅ 所有版本检查通过！" -ForegroundColor Green
}

if ($ERRORS.Count -gt 0) { exit 1 } else { exit 0 }
