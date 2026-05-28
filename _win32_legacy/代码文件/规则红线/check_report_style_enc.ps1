<#
.SYNOPSIS
    閾佸緥閲忓寲 路 鎶ュ憡鏍峰紡鍚堣妫€鏌ヨ剼鏈?.DESCRIPTION
    瀵圭収銆婃姤鍛婃牱寮忓熀绾縚v1.0.md銆嬶紝妫€鏌ョ敓鎴愮殑HTML/DOCX鎶ュ憡鏄惁
    绗﹀悎宸插喕缁撶殑鏍峰紡瑙勮寖銆?    鏀寔妫€鏌ワ細
      - HTML姣忔棩鑽愯偂鎶ュ憡锛坓en_daily_html.ps1杈撳嚭锛?      - 鍚庤瘎浼癏TML鎶ュ憡锛坮eport_style.css鎺у埗锛?      - DOCX鏍峰紡瀹氫箟浠ｇ爜锛坓en_*.ps1涓殑鏍峰紡XML锛?.PARAMETER Quick
    蹇€熸鏌ユā寮忥紝浠呮鏌ュ叧閿鑹插€煎拰瀛椾綋瀹氫箟
.PARAMETER ReportPath
    鎸囧畾鍗曚釜HTML鎶ュ憡鏂囦欢杩涜妫€鏌ワ紙鍙€夛級
.NOTES
    鐗堟湰: v1.0
    鐢ㄦ硶: powershell -File check_report_style.ps1 [-Quick] [-ReportPath <path>]
    閫€鍑虹爜: 0 = 鍏ㄩ儴閫氳繃, 1 = 鏈夎繚瑙?#>
param(
    [switch]$Quick,
    [string]$ReportPath = ""
)
. "$PSScriptRoot/../lib/init_encoding.ps1"

$BASE = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$REPORT_DIR = "$BASE\姣忔棩鑽愯偂\鑲＄エ鎶ュ憡"
$EVAL_REPORT_DIR = "$BASE\鍘嗗彶鏁版嵁\eval"
$REDLINES_DIR = "$BASE\浠ｇ爜鏂囦欢\瑙勫垯绾㈢嚎"
$CHECK_REPORT_FILE = "$REDLINES_DIR\check_report_style_report.txt"

# -- 鍏ㄥ眬鐘舵€?--
$global:pass_count = 0
$global:warn_count = 0
$global:fail_count = 0
$global:report_lines = @()

# -- 鏍峰紡鍩虹嚎甯搁噺 --
$BRAND_DARK      = "#1a1a2e"
$COLOR_UP        = "#e74c3c"
$COLOR_DOWN      = "#27ae60"
$TAG_GREEN_BG    = "#d4edda"
$TAG_YELLOW_BG   = "#fff3cd"
$TAG_RED_BG      = "#f8d7da"

# -- 杈呭姪鍑芥暟 --
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

# -- 妫€鏌ュ嚱鏁?--

function Check-HtmlColorScheme {
    param([string]$Content, [string]$Label)
    $issues = @()
    if ($Content -cnotmatch [regex]::Escape($BRAND_DARK)) {
        $issues += "missing_brand_color"
    }
    if ($Content -notmatch '\.up\s*\{[^}]*color\s*:\s*#e74c3c') {
        $issues += "wrong_up_color"
    }
    if ($Content -notmatch '\.down\s*\{[^}]*color\s*:\s*#27ae60') {
        $issues += "wrong_down_color"
    }
    if ($Content -notmatch 'Microsoft YaHei') {
        $issues += "missing_font"
    }

    if ($issues.Count -eq 0) {
        Write-Result -Section "" -Message ("{0}: 棰滆壊鏂规鍜屽瓧浣撳悎瑙? -f $Label) -Status "PASS"
    } else {
        $issueMap = @{
            "missing_brand_color" = "缂哄皯鍝佺墝鑹?$BRAND_DARK"
            "wrong_up_color" = ".up 棰滆壊涓嶆槸 $COLOR_UP"
            "wrong_down_color" = ".down 棰滆壊涓嶆槸 $COLOR_DOWN"
            "missing_font" = "缂哄皯 Microsoft YaHei 瀛椾綋澹版槑"
        }
        foreach ($code in $issues) {
            $msg = "{0}: {1}" -f $Label, $issueMap[$code]
            Write-Result -Section "" -Message $msg -Status "FAIL"
        }
    }
    return ($issues.Count -eq 0)
}

function Check-HtmlCssClasses {
    param([string]$Content, [string]$Label, [string[]]$RequiredClasses)
    $missing = @()
    foreach ($cls in $RequiredClasses) {
        if ($Content -notmatch '\.' + [regex]::Escape($cls) + '\b') {
            $missing += $cls
        }
    }
    if ($missing.Count -eq 0) {
        Write-Result -Section "" -Message ("{0}: 蹇呴渶CSS绫诲叏閮ㄥ瓨鍦? -f $Label) -Status "PASS"
    } else {
        Write-Result -Section "" -Message ("{0}: 缂哄皯CSS绫? {1}" -f $Label, ($missing -join ', ')) -Status "FAIL"
    }
    return ($missing.Count -eq 0)
}

function Check-HtmlTagColors {
    param([string]$Content, [string]$Label)
    $ok = $true
    if ($Content -notmatch 't-green\s*\{[^}]*background\s*:\s*#d4edda[^}]*color\s*:\s*#155724') {
        if ($Content -notmatch 't-green\s*\{[^}]*#[^}]*d4edda') {
            Write-Result -Section "" -Message ("{0}: .t-green 鑳屾櫙鑹蹭笉鏄?{1}" -f $Label, $TAG_GREEN_BG) -Status "FAIL"
            $ok = $false
        }
    }
    if ($Content -notmatch 't-yellow') {
        Write-Result -Section "" -Message ("{0}: 缂哄皯 .t-yellow 瀹氫箟" -f $Label) -Status "FAIL"
        $ok = $false
    }
    if ($Content -notmatch 't-red') {
        Write-Result -Section "" -Message ("{0}: 缂哄皯 .t-red 瀹氫箟" -f $Label) -Status "FAIL"
        $ok = $false
    }
    if ($ok) { Write-Result -Section "" -Message ("{0}: 鏍囩棰滆壊鍚堣" -f $Label) -Status "PASS" }
    return $ok
}

function Check-HtmlLayout {
    param([string]$Content, [string]$Label)
    $ok = $true
    $layoutChecks = @(
        @{Pattern = '\.hdr\s*\{'; Name = '.hdr 椤靛ご' },
        @{Pattern = '\.sec\s*\{'; Name = '.sec 鍐呭鍖哄潡' },
        @{Pattern = '\.card-grid\s*\{'; Name = '.card-grid 鍗＄墖缃戞牸' },
        @{Pattern = '@page\s*\{[^}]*landscape'; Name = '妯悜椤甸潰澹版槑' }
    )
    foreach ($check in $layoutChecks) {
        if ($Content -notmatch $check.Pattern) {
            Write-Result -Section "" -Message ("{0}: 缂哄皯 {1}" -f $Label, $check.Name) -Status "FAIL"
            $ok = $false
        }
    }
    if ($ok) { Write-Result -Section "" -Message ("{0}: 甯冨眬缁撴瀯鍚堣" -f $Label) -Status "PASS" }
    return $ok
}

function Check-StyleGeneratorScript {
    param([string]$FilePath, [string]$Label)
    if (-not (Test-Path $FilePath)) {
        Write-Result -Section "" -Message ("{0}: 鏂囦欢涓嶅瓨鍦? -f $Label) -Status "FAIL"
        return $false
    }
    $content = Get-Content $FilePath -Raw -Encoding UTF8
    $ok = $true
    if ($content -cnotmatch [regex]::Escape($BRAND_DARK)) {
        Write-Result -Section "" -Message ("{0}: 缂哄皯鍝佺墝鑹?{1}" -f $Label, $BRAND_DARK) -Status "FAIL"
        $ok = $false
    }
    if ($content -notmatch 'Microsoft YaHei') {
        Write-Result -Section "" -Message ("{0}: 缂哄皯 Microsoft YaHei 瀛椾綋澹版槑" -f $Label) -Status "FAIL"
        $ok = $false
    }
    $headingCount = @([regex]::Matches($content, 'Heading1')) +
                    @([regex]::Matches($content, 'Heading2')) +
                    @([regex]::Matches($content, 'Heading3'))
    if ($headingCount.Count -eq 0) {
        Write-Result -Section "" -Message ("{0}: 鏈壘鍒版枃妗ｆ爣棰樺眰绾у畾涔? -f $Label) -Status "WARN"
    }
    if ($content -notmatch 'fill="1A1A2E"') {
        if ($content -notmatch 'fill="1a1a2e"') {
            Write-Result -Section "" -Message ("{0}: 琛ㄥご鑳屾櫙鑹蹭笉鏄?#1A1A2E" -f $Label) -Status "WARN"
        }
    }
    if ($ok) { Write-Result -Section "" -Message ("{0}: 鏍峰紡鐢熸垚浠ｇ爜鍚堣" -f $Label) -Status "PASS" }
    return $ok
}

# ==================================================
#  妫€鏌ュ紑濮?# ==================================================
$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm"
Write-Host "================================================" -ForegroundColor Cyan
Write-Host "     閾佸緥閲忓寲 . 鎶ュ憡鏍峰紡鍚堣妫€鏌? -ForegroundColor Cyan
Write-Host "     鐢熸垚鏃堕棿: $timestamp" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan
$global:report_lines += "================================================"
$global:report_lines += "     閾佸緥閲忓寲 . 鎶ュ憡鏍峰紡鍚堣妫€鏌?
$global:report_lines += "     鐢熸垚鏃堕棿: $timestamp"
$global:report_lines += "================================================"

# -- S1: 妫€鏌ュ崟涓狧TML鎶ュ憡锛堝鏋滄寚瀹氾級 --
if ($ReportPath) {
    Write-SectionHeader "鎸囧畾鎶ュ憡妫€鏌?
    if (-not (Test-Path $ReportPath)) {
        Write-Result -Section "" -Message ("鎶ュ憡鏂囦欢涓嶅瓨鍦? {0}" -f $ReportPath) -Status "FAIL"
        goto Summary
    }
    $content = Get-Content $ReportPath -Raw -Encoding UTF8
    $label = Split-Path $ReportPath -Leaf
    Check-HtmlColorScheme -Content $content -Label $label
    Check-HtmlCssClasses -Content $content -Label $label -RequiredClasses @("hdr", "sec", "card", "up", "down", "tag", "ftr")
    Check-HtmlTagColors -Content $content -Label $label
    Check-HtmlLayout -Content $content -Label $label
    goto Summary
}

# -- S2: 妫€鏌ユ瘡鏃ヨ崘鑲TML鎶ュ憡鏍峰紡鐢熸垚浠ｇ爜 --
Write-SectionHeader "S1 - 姣忔棩鑽愯偂HTML鎶ュ憡鏍峰紡鐢熸垚浠ｇ爜"
$genDailyHtml = "$BASE\浠ｇ爜鏂囦欢\姣忔棩鑽愯偂\鍒嗘瀽閫昏緫\gen_daily_html.ps1"
Check-StyleGeneratorScript -FilePath $genDailyHtml -Label "gen_daily_html.ps1"

# 涔熸鏌ユ渶杩戠敓鎴愮殑瀹為檯HTML鎶ュ憡
Write-SectionHeader "S2 - 鏈€杩戠敓鎴愮殑HTML鎶ュ憡"
$htmlFiles = @(Get-ChildItem "$REPORT_DIR\daily_report_*.html" -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending)
if ($htmlFiles.Count -gt 0) {
    $latest = $htmlFiles[0]
    $content = Get-Content $latest.FullName -Raw -Encoding UTF8
    $label = "鏈€鏂版姤鍛? $($latest.Name)"
    Check-HtmlColorScheme -Content $content -Label $label
    Check-HtmlCssClasses -Content $content -Label $label -RequiredClasses @("hdr", "sec", "card", "up", "down", "tag", "ftr", "card-grid")
    Check-HtmlTagColors -Content $content -Label $label
    Check-HtmlLayout -Content $content -Label $label
} else {
    Write-Result -Section "" -Message "鏈壘鍒版瘡鏃ヨ崘鑲TML鎶ュ憡鏂囦欢" -Status "WARN"
}

# -- S3: 妫€鏌ュ閮–SS鏍峰紡鏂囦欢 --
Write-SectionHeader "S3 - 澶栭儴CSS鏍峰紡鏂囦欢"
$cssFile = "$BASE\浠ｇ爜鏂囦欢\鏁版嵁\report_style.css"
if (Test-Path $cssFile) {
    $cssContent = Get-Content $cssFile -Raw -Encoding UTF8
    $cssLabel = "report_style.css"

    if ($cssContent -cmatch [regex]::Escape($BRAND_DARK)) {
        Write-Result -Section "" -Message ("{0}: 鍝佺墝鑹插瓨鍦? -f $cssLabel) -Status "PASS"
    } else {
        Write-Result -Section "" -Message ("{0}: 缂哄皯鍝佺墝鑹?{1}" -f $cssLabel, $BRAND_DARK) -Status "FAIL"
    }
    if ($cssContent -match 'Microsoft YaHei') {
        Write-Result -Section "" -Message ("{0}: 瀛椾綋澹版槑瀛樺湪" -f $cssLabel) -Status "PASS"
    } else {
        Write-Result -Section "" -Message ("{0}: 缂哄皯 Microsoft YaHei 瀛椾綋澹版槑" -f $cssLabel) -Status "FAIL"
    }
    if ($cssContent -match 'th\s*\{[^}]*background\s*:\s*#1A1A2E') {
        Write-Result -Section "" -Message ("{0}: 琛ㄦ牸琛ㄥご鑳屾櫙鑹插悎瑙? -f $cssLabel) -Status "PASS"
    } else {
        Write-Result -Section "" -Message ("{0}: 琛ㄦ牸琛ㄥご鑳屾櫙鑹蹭笉鏄?#1A1A2E" -f $cssLabel) -Status "FAIL"
    }
    Check-HtmlColorScheme -Content $cssContent -Label $cssLabel
    Check-HtmlCssClasses -Content $cssContent -Label $cssLabel -RequiredClasses @("page", "metrics", "badge", "findings-list", "suggestion", "footer")
} else {
    Write-Result -Section "" -Message "report_style.css 涓嶅瓨鍦? -Status "WARN"
}

# -- S4: 妫€鏌OCX鏍峰紡鐢熸垚浠ｇ爜 --
Write-SectionHeader "S4 - DOCX鏍峰紡鐢熸垚浠ｇ爜妫€鏌?
$docxGenScripts = @(
    @{ Path = "$BASE\浠ｇ爜鏂囦欢\姣忔棩鑽愯偂\鍒嗘瀽閫昏緫\gen_doc_v2.ps1"; Name = "姣忔棩鑽愯偂鐧界毊涔?gen_doc_v2.ps1" },
    @{ Path = "$BASE\浠ｇ爜鏂囦欢\姣忔棩鑽愯偂\浜嬪悗璇勪及\gen_eval_doc.ps1"; Name = "鍚庤瘎浼扮櫧鐨功(鏃? gen_eval_doc.ps1" },
    @{ Path = "$BASE\浠ｇ爜鏂囦欢\姣忔棩鑽愯偂\浜嬪悗璇勪及\gen_eval_doc_v1.5.ps1"; Name = "鍚庤瘎浼扮櫧鐨功(v1.5) gen_eval_doc_v1.5.ps1" },
    @{ Path = "$BASE\浠ｇ爜鏂囦欢\閲嶇偣鑲＄エ\鍒嗘瀽閫昏緫\gen_doc.ps1"; Name = "閲嶇偣鑲＄エ鐧界毊涔?gen_doc.ps1" },
    @{ Path = "$BASE\浠ｇ爜鏂囦欢\瑙勫垯绾㈢嚎\gen_redlines_doc.ps1"; Name = "瑙勫垯绾㈢嚎 gen_redlines_doc.ps1" },
    @{ Path = "$BASE\浠ｇ爜鏂囦欢\閲嶇偣鑲＄エ\娆℃棩璇勪及\gen_eval_doc.ps1"; Name = "閲嶇偣鑲＄エ鍚庤瘎浼?gen_eval_doc.ps1" }
)
foreach ($script in $docxGenScripts) {
    Check-StyleGeneratorScript -FilePath $script.Path -Label $script.Name
}

# -- S5: 妫€鏌d_to_docx.py鏍峰紡甯搁噺 --
Write-SectionHeader "S5 - md_to_docx.py 鏍峰紡甯搁噺"
$mdToDocx = "$BASE\浠ｇ爜鏂囦欢\tools\md_to_docx.py"
if (Test-Path $mdToDocx) {
    $pyContent = Get-Content $mdToDocx -Raw -Encoding UTF8
    $colorChecks = @(
        @{ Pattern = 'C_PRIMARY\s*=\s*RGBColor\(0x1A,\s*0x1A,\s*0x2E\)'; Name = "C_PRIMARY = #1A1A2E" },
        @{ Pattern = 'C_SECONDARY\s*=\s*RGBColor\(0x16,\s*0x21,\s*0x3E\)'; Name = "C_SECONDARY = #16213E" },
        @{ Pattern = 'C_BODY\s*=\s*RGBColor\(0x33,\s*0x33,\s*0x33\)'; Name = "C_BODY = #333333" },
        @{ Pattern = 'SIZE_H1\s*=\s*Pt\(18\)'; Name = "SIZE_H1 = 18pt" },
        @{ Pattern = 'SIZE_H2\s*=\s*Pt\(14\)'; Name = "SIZE_H2 = 14pt" },
        @{ Pattern = 'SIZE_H3\s*=\s*Pt\(12\)'; Name = "SIZE_H3 = 12pt" }
    )
    foreach ($check in $colorChecks) {
        if ($pyContent -match $check.Pattern) {
            Write-Result -Section "" -Message ("md_to_docx.py: {0}" -f $check.Name) -Status "PASS"
        } else {
            Write-Result -Section "" -Message ("md_to_docx.py: {0} 鏈壘鍒? -f $check.Name) -Status "FAIL"
        }
    }
} else {
    Write-Result -Section "" -Message "md_to_docx.py 涓嶅瓨鍦? -Status "FAIL"
}

# -- S6: 妫€鏌ユ牱寮忓熀绾挎枃妗ｆ湰韬槸鍚﹀瓨鍦?--
Write-SectionHeader "S6 - 鏍峰紡鍩虹嚎鏂囨。瀹屾暣鎬?
$baselineDoc = "$BASE\瑙勫垯绾㈢嚎\鎶ュ憡鏍峰紡鍩虹嚎_v1.0.md"
if (Test-Path $baselineDoc) {
    $item = Get-Item $baselineDoc
    if ($item.Length -gt 1000) {
        Write-Result -Section "" -Message ("鎶ュ憡鏍峰紡鍩虹嚎_v1.0.md 瀛樺湪 ({0} bytes)" -f $item.Length) -Status "PASS"
    } else {
        Write-Result -Section "" -Message "鎶ュ憡鏍峰紡鍩虹嚎_v1.0.md 鍐呭杩囩煭" -Status "WARN"
    }
} else {
    Write-Result -Section "" -Message "鎶ュ憡鏍峰紡鍩虹嚎_v1.0.md 涓嶅瓨鍦? -Status "FAIL"
}

# -- 蹇€熸ā寮忥細鏃╂湡閫€鍑?--
if ($Quick) {
    goto Summary
}

# -- S7: 妫€鏌ユ墍鏈塨uild_docx.ps1鐨勬牱寮忎竴鑷存€?--
Write-SectionHeader "S7 - build_docx.ps1 妯℃澘妫€鏌?
$buildDocxScripts = @(
    "$BASE\浠ｇ爜鏂囦欢\瑙勫垯绾㈢嚎\build_docx.ps1",
    "$BASE\浠ｇ爜鏂囦欢\姣忔棩鑽愯偂\鍒嗘瀽閫昏緫\build_docx.ps1",
    "$BASE\浠ｇ爜鏂囦欢\姣忔棩鑽愯偂\浜嬪悗璇勪及\build_docx.ps1",
    "$BASE\浠ｇ爜鏂囦欢\閲嶇偣鑲＄エ\鍒嗘瀽閫昏緫\build_docx.ps1"
)
foreach ($bScript in $buildDocxScripts) {
    if (Test-Path $bScript) {
        $bContent = Get-Content $bScript -Raw -Encoding UTF8
        if ($bContent -match 'md_to_docx\.py') {
            Write-Result -Section "" -Message ("{0}: 浣跨敤 md_to_docx.py 妯℃澘" -f (Split-Path $bScript -Leaf)) -Status "PASS"
        } else {
            Write-Result -Section "" -Message ("{0}: 鏈壘鍒?md_to_docx.py 寮曠敤" -f (Split-Path $bScript -Leaf)) -Status "WARN"
        }
    }
}

# ==================================================
#  Summary / 鎬讳綋鍒ゅ畾
# ==================================================
:Summary
Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
$global:report_lines += ""
$global:report_lines += "============================================"

$total = $global:pass_count + $global:warn_count + $global:fail_count
if ($global:fail_count -eq 0 -and $global:warn_count -eq 0) {
    $verdict = "[PASS] 鍏ㄩ儴鏍峰紡鍚堣"
    $extra = "鍏ㄩ儴閫氳繃 ($global:pass_count/$total)"
    $vColor = "Green"
} elseif ($global:fail_count -eq 0) {
    $verdict = "[WARN] 鍩烘湰鍚堣 ($($global:warn_count) 涓鍛?"
    $extra = "閫氳繃 $($global:pass_count)/$total锛岃鍛?$($global:warn_count)"
    $vColor = "Yellow"
} else {
    $verdict = "[FAIL] 鏍峰紡涓嶅悎瑙?($($global:warn_count) 涓鍛婏紝$($global:fail_count) 涓繚瑙?"
    $extra = "閫氳繃 $($global:pass_count)/$total锛岃鍛?$($global:warn_count)锛岃繚瑙?$($global:fail_count)"
    $vColor = "Red"
}
Write-Host "鎬讳綋鍒ゅ畾: $verdict" -ForegroundColor $vColor
Write-Host $extra -ForegroundColor $vColor
Write-Host "鍩虹嚎鏂囨。: 瑙勫垯绾㈢嚎\鎶ュ憡鏍峰紡鍩虹嚎_v1.0.md" -ForegroundColor $vColor
$global:report_lines += "鎬讳綋鍒ゅ畾: $verdict"
$global:report_lines += $extra
$global:report_lines += "鍩虹嚎鏂囨。: 瑙勫垯绾㈢嚎\鎶ュ憡鏍峰紡鍩虹嚎_v1.0.md"

# 淇濆瓨鎶ュ憡
$global:report_lines -join "`r`n" | Out-File -FilePath $CHECK_REPORT_FILE -Encoding UTF8
Write-Host ""
Write-Host "鎶ュ憡宸蹭繚瀛? $CHECK_REPORT_FILE" -ForegroundColor Gray

# 閫€鍑虹爜
if ($global:fail_count -gt 0) { exit 1 }
exit 0
