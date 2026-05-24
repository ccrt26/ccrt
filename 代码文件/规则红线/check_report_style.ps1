<#
.SYNOPSIS
    Tielv Quant - Report Style Compliance Check
.DESCRIPTION
    Checks generated HTML/DOCX reports against the frozen style baseline.
    Checks: HTML daily report styles, CSS files, DOCX generator scripts.
.PARAMETER Quick
    Quick mode - only check key items
.PARAMETER ReportPath
    Check a specific HTML report file
.NOTES
    Version: v1.0
    Usage: powershell -File check_report_style.ps1 [-Quick] [-ReportPath <path>]
    Exit: 0 = pass, 1 = fail
#>
param([switch]$Quick, [string]$ReportPath = "")

$BASE        = "C:\Users\34269\Documents\Claude\股票分析"
$RPT_DIR     = "$BASE\每日荐股\股票报告"
$RED_DIR     = "$BASE\代码文件\规则红线"
$OUT_FILE    = "$RED_DIR\check_report_style_report.txt"

$global:pc=0; $global:wc=0; $global:fc=0; $global:lines=@()

function Log {
    param([string]$M, [string]$S)
    $ico = switch ($S) {"PASS"{"[OK]"} "WARN"{"[!!]"} "FAIL"{"[XX]"} default{"[--]"}}
    $col = switch ($S) {"PASS"{"Green"} "WARN"{"Yellow"} "FAIL"{"Red"} default{"White"}}
    $line = "  $ico $M"
    Write-Host $line -ForegroundColor $col
    $global:lines += $line
    switch ($S){"PASS"{$global:pc++}"WARN"{$global:wc++}"FAIL"{$global:fc++}}
}

function Sec {
    param([string]$T)
    Write-Host "`n[$T]" -ForegroundColor Cyan
    $global:lines += "`n[$T]"
}

# Check a script file for brand color, font, heading defs
function Check-GenScript {
    param([string]$Path, [string]$Label)
    if (-not (Test-Path $Path)) { Log -M "$Label file not found" -S "FAIL"; return }
    $c = Get-Content $Path -Raw -Encoding UTF8
    $ok = $true
    if ($c -cnotmatch [regex]::Escape("#1a1a2e") -and $c -cnotmatch "1A1A2E") {
        Log -M "$Label missing brand color (#1a1a2e/1A1A2E)" -S "FAIL"; $ok = $false
    }
    if ($c -notmatch "Microsoft YaHei") {
        Log -M "$Label missing font" -S "FAIL"; $ok = $false
    }
    $hasHeadingDefs = ($c -match "Heading1" -or $c -match 'w:pStyle' -or $c -match '<h[12]' -or $c -match '\.hdr h1')
    if (-not $hasHeadingDefs) {
        Log -M "$Label missing heading defs" -S "WARN"
    }
    if ($ok) { Log -M "$Label style defs ok" -S "PASS" }
}

# Check HTML content for required CSS classes
function Check-HtmlCss {
    param([string]$Content, [string]$Label, [string[]]$Classes)
    foreach ($cls in $Classes) {
        if ($Content -match ('\.' + [regex]::Escape($cls) + '\b')) {
            Log -M "$Label .$cls found" -S "PASS"
        } else {
            Log -M "$Label .$cls NOT found" -S "FAIL"
        }
    }
}

# Check HTML content for brand colors
function Check-HtmlColors {
    param([string]$Content, [string]$Label)
    if ($Content -cmatch [regex]::Escape("#1a1a2e")) {
        Log -M "$Label brand color #1a1a2e" -S "PASS"
    } else { Log -M "$Label brand color missing" -S "FAIL" }
    if ($Content -match '\.up\s*\{[^}]*color\s*:\s*#e74c3c') {
        Log -M "$Label .up color ok" -S "PASS"
    } else { Log -M "$Label .up color not #e74c3c" -S "FAIL" }
    if ($Content -match '\.down\s*\{[^}]*color\s*:\s*#27ae60') {
        Log -M "$Label .down color ok" -S "PASS"
    } else { Log -M "$Label .down color not #27ae60" -S "FAIL" }
    if ($Content -match "Microsoft YaHei") {
        Log -M "$Label font ok" -S "PASS"
    } else { Log -M "$Label font missing" -S "FAIL" }
}

# ===== Main =====
$ts = Get-Date -Format "yyyy-MM-dd HH:mm"
Write-Host "================================================" -ForegroundColor Cyan
Write-Host "     Tielv Quant - Report Style Check" -ForegroundColor Cyan
Write-Host "     $ts" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan
$global:lines += "================================================"
$global:lines += "     Tielv Quant - Report Style Check"
$global:lines += "     $ts"
$global:lines += "================================================"

# S0: Style baseline doc
Sec "S0 - Baseline Doc"
$bd = "$BASE\规则红线\报告样式基线_v1.1.md"
if (Test-Path $bd) { Log -M "baseline doc exists" -S "PASS" }
else { Log -M "baseline doc missing" -S "FAIL" }

# S1: HTML report generator
Sec "S1 - gen_daily_html.ps1"
Check-GenScript -Path "$BASE\代码文件\每日荐股\分析逻辑\gen_daily_html.ps1" -Label "gen_daily_html.ps1"

# S2: Latest HTML report
Sec "S2 - HTML Report Check"
$hfiles = @(Get-ChildItem "$RPT_DIR\daily_report_*.html" -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending)
if ($hfiles.Count -gt 0) {
    $c = Get-Content $hfiles[0].FullName -Raw -Encoding UTF8
    $lbl = "Report: $($hfiles[0].Name)"
    Check-HtmlColors -Content $c -Label $lbl
    Check-HtmlCss -Content $c -Label $lbl -Classes @("hdr","sec","card","card-grid","up","down","tag","ftr","t-green","t-yellow","t-red","sc-high","bg-green","c-name","c-scr","c-logic","note","s-bar")
    if ($c -match 'landscape') { Log -M "$lbl landscape ok" -S "PASS" }
    else { Log -M "$lbl landscape missing" -S "FAIL" }
} else { Log -M "no HTML reports found" -S "WARN" }

# If specified report, check it
if ($ReportPath -and (Test-Path $ReportPath)) {
    Sec "S2b - Specified Report"
    $c = Get-Content $ReportPath -Raw -Encoding UTF8
    $lbl = Split-Path $ReportPath -Leaf
    Check-HtmlColors -Content $c -Label $lbl
    Check-HtmlCss -Content $c -Label $lbl -Classes @("hdr","sec","card","up","down","tag","ftr","card-grid")
}

# S3: CSS file
Sec "S3 - report_style.css"
$css = "$BASE\代码文件\数据\report_style.css"
if (Test-Path $css) {
    $c = Get-Content $css -Raw -Encoding UTF8
    if ($c -cmatch [regex]::Escape("#1A1A2E")) { Log -M "css brand color ok" -S "PASS" }
    else { Log -M "css brand color missing" -S "FAIL" }
    if ($c -match "Microsoft YaHei") { Log -M "css font ok" -S "PASS" }
    else { Log -M "css font missing" -S "FAIL" }
    Check-HtmlCss -Content $c -Label "css" -Classes @("page","metrics","badge","findings-list","suggestion","footer","up","down")
} else { Log -M "report_style.css not found" -S "WARN" }

# S4: DOCX generators
Sec "S4 - DOCX Gen Scripts"
$scripts = @(
    "$BASE\代码文件\每日荐股\分析逻辑\gen_doc_v2.ps1",
    "$BASE\代码文件\每日荐股\事后评估\gen_eval_doc.ps1",
    "$BASE\代码文件\每日荐股\事后评估\gen_eval_doc_v1.5.ps1",
    "$BASE\代码文件\重点股票\分析逻辑\gen_doc.ps1",
    "$BASE\代码文件\规则红线\gen_redlines_doc.ps1",
    "$BASE\代码文件\重点股票\次日评估\gen_eval_doc.ps1"
)
foreach ($s in $scripts) {
    $sn = Split-Path $s -Leaf
    Check-GenScript -Path $s -Label $sn
}

# S5: md_to_docx.py
Sec "S5 - md_to_docx.py"
$py = "$BASE\代码文件\tools\md_to_docx.py"
if (Test-Path $py) {
    $c = Get-Content $py -Raw -Encoding UTF8
    $checks = @(
        @{n="C_PRIMARY"; p="C_PRIMARY.*RGBColor"},
        @{n="C_SECONDARY"; p="C_SECONDARY.*RGBColor"},
        @{n="FONT_FAMILY"; p="FONT_FAMILY"},
        @{n="SIZE_H1 18pt"; p="SIZE_H1.*Pt\(18"},
        @{n="SIZE_H2 14pt"; p="SIZE_H2.*Pt\(14"},
        @{n="SIZE_H3 12pt"; p="SIZE_H3.*Pt\(12"}
    )
    foreach ($chk in $checks) {
        if ($c -match $chk.p) { Log -M "md_to_docx.py: $($chk.n)" -S "PASS" }
        else { Log -M "md_to_docx.py: $($chk.n) NOT found" -S "FAIL" }
    }
} else { Log -M "md_to_docx.py not found" -S "FAIL" }

# S6: build_docx.ps1 files
if (-not $Quick) {
    Sec "S6 - build_docx.ps1 check"
    $builds = @(
        "$BASE\代码文件\规则红线\build_docx.ps1",
        "$BASE\代码文件\每日荐股\分析逻辑\build_docx.ps1",
        "$BASE\代码文件\每日荐股\事后评估\build_docx.ps1",
        "$BASE\代码文件\重点股票\分析逻辑\build_docx.ps1"
    )
    foreach ($b in $builds) {
        if (Test-Path $b) {
            $bc = Get-Content $b -Raw -Encoding UTF8
            if ($bc -match "md_to_docx") {
                Log -M "$(Split-Path $b -Leaf) uses md_to_docx" -S "PASS"
            } else { Log -M "$(Split-Path $b -Leaf) no md_to_docx ref" -S "WARN" }
        }
    }
}

# ===== Summary =====
Write-Host ""
$global:lines += ""
$total = $global:pc + $global:wc + $global:fc
if ($global:fc -eq 0 -and $global:wc -eq 0) {
    $v="[PASS] All styles compliant"; $vc="Green"
} elseif ($global:fc -eq 0) {
    $v="[WARN] $($global:wc) warnings"; $vc="Yellow"
} else {
    $v="[FAIL] $($global:wc) warnings, $($global:fc) failures"; $vc="Red"
}
$extra = "Pass=$global:pc Warn=$global:wc Fail=$global:fc Total=$total"
Write-Host $v -ForegroundColor $vc
Write-Host $extra -ForegroundColor $vc
$global:lines += $v; $global:lines += $extra
$global:lines -join "`r`n" | Out-File $OUT_FILE -Encoding UTF8
Write-Host "Report saved: $OUT_FILE" -ForegroundColor Gray
if ($global:fc -gt 0) { exit 1 } else { exit 0 }

