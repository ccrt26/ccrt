# 依赖: 被 run_full_audit.ps1 dot-source 加载
# $rootDir 由主脚本在 dot-source 前定义，本模块直接使用

$ErrorActionPreference = "Continue"
$auditDir = Join-Path $rootDir "历史数据"
$reportOutDir = Join-Path $rootDir "历史数据\审计报告"
$redlinesDir = Join-Path $rootDir "代码文件\规则红线"
$supervisorDir = Join-Path $rootDir "代码文件\监督机制"
$scriptsDir = Join-Path $rootDir "代码文件\每日荐股\scripts"
$dataDir = Join-Path $rootDir "代码文件\数据"
$dateNum = $Date -replace '-',''

# ---- 状态 ----
$script:results = @{}
$script:failures = @()
$script:warnings = @()
$script:metrics = @{}

function Add-Check {
    param([string]$Section, [string]$Id, [string]$Desc, [string]$Status, [string]$Detail = "")
    $key = "${Section}_${Id}"
    $script:results[$key] = @{ section=$Section; id=$Id; desc=$Desc; status=$Status; detail=$Detail }
    $icon = if($Status -eq 'PASS'){[char]0x2705}elseif($Status -eq 'WARN'){[char]0x26A0}else{[char]0x274C}
    $color = if($Status -eq 'PASS'){'Green'}elseif($Status -eq 'WARN'){'Yellow'}else{'Red'}
    Write-Host "  $icon [$Section-$Id] $Desc" -ForegroundColor $color
    if ($Detail) { Write-Host "         $Detail" -ForegroundColor DarkGray }
    if ($Status -eq 'FAIL') { $script:failures += "[${Section}-${Id}] $Desc — $Detail" }
    if ($Status -eq 'WARN') { $script:warnings += "[${Section}-${Id}] $Desc — $Detail" }
}

function Test-FileFreshness {
    param([string]$Path, [double]$MaxHours = 48)
    if (-not (Test-Path $Path)) { return $null }
    $age = ((Get-Date) - (Get-Item $Path).LastWriteTime).TotalHours
    return ($age -le $MaxHours)
}

function Test-UTF8Validity {
    param([string]$Path)
    try {
        $bytes = [System.IO.File]::ReadAllBytes($Path)
        if ($bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF) {
            $text = [System.Text.Encoding]::UTF8.GetString($bytes, 3, $bytes.Length - 3)
        } else {
            $text = [System.Text.Encoding]::UTF8.GetString($bytes)
        }
        $reencoded = [System.Text.Encoding]::UTF8.GetBytes($text)
        return $true
    } catch { return $false }
}

function Test-HasBOM {
    param([string]$Path)
    try {
        $bytes = [System.IO.File]::ReadAllBytes($Path)
        return ($bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF)
    } catch { return $false }
}

function Invoke-ExistingScript {
    param([string]$ScriptPath, [string[]]$ExtraArgs = @())
    if (-not (Test-Path $ScriptPath)) { return $null }
    try {
        $savedErr = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        $output = & $ScriptPath @ExtraArgs 2>&1 | Out-String
        $exitCode = $LASTEXITCODE
        $ErrorActionPreference = $savedErr
        return @{ ExitCode = $exitCode; Output = $output }
    } catch {
        return @{ ExitCode = -1; Output = $_.Exception.Message }
    }
}

Write-Host ""
Write-Host "╔══════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║  铁律量化 · 综合审计 (Phase 1)        ║" -ForegroundColor Cyan
Write-Host "║  Gauge 审计官 | $Date              ║" -ForegroundColor Cyan
Write-Host "╚══════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""
