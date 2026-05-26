<#
.SYNOPSIS
  - Checks all scripts have init_encoding reference
  - Checks no init_encoding appears before param() block
  - Outputs violations as [VIOLATION] lines
  - Exit code 0 = all OK, 1 = violations found
#>
param(
    [string]$RootDir = "",
    [switch]$Json = $false
)
. "$PSScriptRoot/../lib/init_encoding.ps1"

$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

if (-not $RootDir) {
    $RootDir = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
}
$codeDir = Join-Path $RootDir "代码文件"

$violations = @()
$missing = @()
$ok = 0
$total = 0

$scripts = @(Get-ChildItem -Path $codeDir -Recurse -Include '*.ps1','*.psm1' -File)
foreach ($s in $scripts) {
    # init_encoding.ps1 is the file being sourced — it should NOT dot-source itself
    if ($s.Name -eq 'init_encoding.ps1') { continue }
    $total++
    try {
        $lines = [System.IO.File]::ReadAllLines($s.FullName, [System.Text.Encoding]::UTF8)
        $hasInit = $false
        $paramLine = -1
        $initLine = -1

        for ($i = 0; $i -lt $lines.Count; $i++) {
            $line = $lines[$i]
            if ($line -match 'init_encoding\.ps1') {
                $hasInit = $true
                if ($initLine -lt 0) { $initLine = $i }
            }
            if ($line -match '^\s*param\s*\(') {
                if ($paramLine -lt 0) { $paramLine = $i }
            }
        }

        if (-not $hasInit) {
            $missing += [PSCustomObject]@{ File = $s.FullName; Issue = "Missing init_encoding" }
            continue
        }

        if ($paramLine -ge 0 -and $initLine -ge 0 -and $initLine -lt $paramLine) {
            $violations += [PSCustomObject]@{
                File = $s.FullName
                Issue = "init_encoding before param()"
                InitLine = $initLine + 1
                ParamLine = $paramLine + 1
            }
            continue
        }

        $ok++
    }
    catch {
        $violations += [PSCustomObject]@{ File = $s.FullName; Issue = "Read error: $_"; InitLine = 0; ParamLine = 0 }
    }
}

if ($Json) {
    @{ Total = $total; OK = $ok; Missing = $missing.Count; Violations = $violations.Count;
       MissingList = $missing; ViolationList = $violations } | ConvertTo-Json -Depth 4
}
else {
    Write-Host "Total scripts: $total | OK: $ok | Missing: $($missing.Count) | Violations: $($violations.Count)"
    Write-Host ""
    if ($missing.Count -gt 0) {
        Write-Host "--- Missing init_encoding ---"
        foreach ($m in $missing) { Write-Host "  [MISS] $($m.File)" }
    }
    if ($violations.Count -gt 0) {
        Write-Host "--- Violations (init_encoding before param) ---"
        foreach ($v in $violations) {
            Write-Host "  [VIOL] $($v.File) : init line $($v.InitLine), param line $($v.ParamLine)"
        }
    }
    if ($missing.Count -eq 0 -and $violations.Count -eq 0) {
        Write-Host "[PASS] All scripts have init_encoding in correct position."
    }
    else {
        Write-Host "[FAIL] Fix required."
    }
}

if ($missing.Count -gt 0 -or $violations.Count -gt 0) { exit 1 }
exit 0
