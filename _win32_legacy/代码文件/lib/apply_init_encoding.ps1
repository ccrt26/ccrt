<#
.SYNOPSIS
  - scripts with param(): inserts AFTER param() block closing ')'
  - scripts without param(): inserts at line 1
  - .psm1 modules: inserts at line 1
#>
param(
    [string]$RootDir = "",
    [switch]$WhatIf = $false,
    [switch]$Force = $false
)
. "$PSScriptRoot/../lib/init_encoding.ps1"

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$PSDefaultParameterValues['*:Encoding'] = 'utf8'
$OutputEncoding = [System.Text.Encoding]::UTF8

if (-not $RootDir) {
    $RootDir = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
}
$libDir = Join-Path $RootDir "代码文件\lib"
$codeDir = Join-Path $RootDir "代码文件"

if (-not (Test-Path $libDir)) {
    Write-Error "Lib dir not found: $libDir"
    exit 1
}

$results = @{ Total = 0; Applied = 0; Skipped = 0; Errors = 0; Files = @() }

function Get-RelativeDotSource {
    param([string]$ScriptPath)
    $relative = (Resolve-Path $ScriptPath -Relative).Replace('\', '/')
    $depth = ($relative -split '/').Count - 3  # minus '.', '代码文件', filename
    if ($depth -lt 1) { $depth = 1 }
    $dots = ("../" * $depth).TrimEnd('/')
    return ". ""`$PSScriptRoot/$dots/lib/init_encoding.ps1"""
}

function Find-ParamBlockEnd {
    param([string[]]$Content)
    # Walk lines to find top-level param() block closing
    $inParam = $false; $parenDepth = 0
    for ($i = 0; $i -lt $Content.Count; $i++) {
        $line = $Content[$i].Trim()
        if ($line -match '^param\s*\(') {
            $inParam = $true
            $openCount = ($line.ToCharArray() | Where-Object { $_ -eq '(' }).Count
            $closeCount = ($line.ToCharArray() | Where-Object { $_ -eq ')' }).Count
            $parenDepth = $openCount - $closeCount
            if ($parenDepth -le 0) { return $i }  # single-line param()
            continue
        }
        if ($inParam) {
            $openCount = ($line.ToCharArray() | Where-Object { $_ -eq '(' }).Count
            $closeCount = ($line.ToCharArray() | Where-Object { $_ -eq ')' }).Count
            $parenDepth += ($openCount - $closeCount)
            if ($parenDepth -le 0) { return $i }
        }
    }
    return -1
}

function Apply-ToScript {
    param([string]$Path)
    $results.Total++
    try {
        # Never modify init_encoding.ps1 itself (would cause self-referencing recursion)
        if ($Path -match '[/\\]init_encoding\.ps1$') {
            Write-Host "  [SKIP] $Path (init_encoding itself, never modified)"
            $results.Skipped++
            $results.Files += [PSCustomObject]@{ Path = $Path; Status = "SKIP"; Detail = "init_encoding itself" }
            return
        }

        $content = [System.IO.File]::ReadAllLines($Path, [System.Text.Encoding]::UTF8)
        $raw = [System.IO.File]::ReadAllText($Path, [System.Text.Encoding]::UTF8)

        # Skip if already has init_encoding (unless -Force)
        if ($raw -match 'init_encoding\.ps1' -and -not $Force) {
            Write-Host "  [SKIP] $Path (already present)"
            $results.Skipped++
            $results.Files += [PSCustomObject]@{ Path = $Path; Status = "SKIP"; Detail = "already present" }
            return
        }

        # -Force mode: remove existing init_encoding line(s) before re-inserting
        if ($Force -and $raw -match 'init_encoding\.ps1') {
            $content = $content | Where-Object { $_ -notmatch 'init_encoding\.ps1' }
            Write-Host "  [FORCE] $Path (removed existing init_encoding, re-inserting)"
        }

        $ds = Get-RelativeDotSource $Path
        $paramEnd = Find-ParamBlockEnd $content
        $isModule = $Path -match '\.psm1$'

        $newContent = [System.Collections.ArrayList]@()
        if ($paramEnd -ge 0) {
            # Has param(): insert after closing ')'
            for ($i = 0; $i -le $paramEnd; $i++) {
                [void]$newContent.Add($content[$i])
            }
            [void]$newContent.Add($ds)
            for ($i = $paramEnd + 1; $i -lt $content.Count; $i++) {
                [void]$newContent.Add($content[$i])
            }
        }
        else {
            # No param() or module: insert at line 1
            [void]$newContent.Add($ds)
            for ($i = 0; $i -lt $content.Count; $i++) {
                [void]$newContent.Add($content[$i])
            }
        }

        if ($WhatIf) {
            Write-Host "  [WHATIF] $Path (would apply)"
            $results.Skipped++
            return
        }

        [System.IO.File]::WriteAllLines($Path, $newContent, [System.Text.Encoding]::UTF8)
        Write-Host "  [OK] $Path (param_end=$paramEnd)"
        $results.Applied++
        $results.Files += [PSCustomObject]@{ Path = $Path; Status = "OK"; Detail = "param_end=$paramEnd" }
    }
    catch {
        Write-Host "  [ERROR] $Path : $_"
        $results.Errors++
        $results.Files += [PSCustomObject]@{ Path = $Path; Status = "ERROR"; Detail = "$_" }
    }
}

Write-Host "Root: $RootDir"
Write-Host "Code: $codeDir"
if ($WhatIf) { Write-Host "WHATIF MODE - no changes will be written" }
Write-Host ""

$scripts = @(Get-ChildItem -Path $codeDir -Recurse -Include '*.ps1','*.psm1' -File)
Write-Host "Found $($scripts.Count) scripts"
Write-Host ""

foreach ($s in $scripts) {
    Apply-ToScript $s.FullName
}

Write-Host ""
Write-Host "=== Summary ==="
Write-Host "Total:   $($results.Total)"
Write-Host "Applied: $($results.Applied)"
Write-Host "Skipped: $($results.Skipped)"
Write-Host "Errors:  $($results.Errors)"

if ($results.Errors -gt 0) { exit 1 }
exit 0
