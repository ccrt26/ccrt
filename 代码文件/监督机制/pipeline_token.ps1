# Pipeline Token Manager v1.0
# Manages .claude/pipeline_active.json lifecycle
# Usage: -Start "task" | -Advance [role] | -Complete | -Status

param(
    [switch]$Start,
    [switch]$Advance,
    [switch]$Complete,
    [switch]$Status,
    [string]$Task = "",
    [string]$To = "",
    [int]$Stage = -1
)

$BASE = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$TOKEN_FILE = "$BASE\.claude\pipeline_active.json"
$HISTORY_DIR = "$BASE\.claude\pipeline_history"
$STAGES = @("情墨", "新安+旧影", "红结", "新安", "红枫", "PostEval")

function Get-CurrentToken {
    if (-not (Test-Path $TOKEN_FILE)) { return $null }
    try {
        return Get-Content $TOKEN_FILE -Raw -Encoding UTF8 | ConvertFrom-Json
    } catch {
        return $null
    }
}

function Show-Status {
    $token = Get-CurrentToken
    if (-not $token -or -not $token.active) {
        Write-Host "Pipeline: INACTIVE" -ForegroundColor Gray
        return
    }
    Write-Host "Pipeline: ACTIVE" -ForegroundColor Green
    Write-Host "  Task: $($token.task)" -ForegroundColor White
    Write-Host "  Stage: $($token.stage)/6 - $($token.executor)" -ForegroundColor Cyan
    Write-Host "  Started: $($token.started)" -ForegroundColor Gray
    Write-Host "  Updated: $($token.updated)" -ForegroundColor Gray
}

function Get-StageIndex($roleName) {
    for ($i = 0; $i -lt $STAGES.Count; $i++) {
        if ($STAGES[$i] -eq $roleName) { return $i }
    }
    return -1
}

# --- Status ---
if ($Status) {
    Show-Status
    exit 0
}

# --- Start ---
if ($Start) {
    if (-not $Task) {
        Write-Host "ERROR: -Start requires -Task" -ForegroundColor Red
        exit 1
    }
    $existing = Get-CurrentToken
    if ($existing -and $existing.active) {
        Write-Host "WARNING: Active pipeline exists. Complete or cancel it first." -ForegroundColor Yellow
        Show-Status
        exit 1
    }
    $now = Get-Date -Format 'yyyy-MM-ddTHH:mm:ss'
    @{
        active   = $true
        task     = $Task
        started  = $now
        executor = "情墨"
        stage    = 1
        updated  = $now
    } | ConvertTo-Json | Set-Content $TOKEN_FILE -Encoding UTF8
    Write-Host "[Pipeline] Token created - Stage 1/6: 情墨" -ForegroundColor Green
    Write-Host "  Task: $Task" -ForegroundColor White
    exit 0
}

# --- Advance ---
if ($Advance) {
    $token = Get-CurrentToken
    if (-not $token -or -not $token.active) {
        Write-Host "ERROR: No active pipeline. Use -Start first." -ForegroundColor Red
        exit 1
    }
    $now = Get-Date -Format 'yyyy-MM-ddTHH:mm:ss'
    if ($To) {
        $idx = Get-StageIndex $To
        if ($idx -lt 0) {
            Write-Host "ERROR: Unknown role '$To'. Valid: $($STAGES -join ', ')" -ForegroundColor Red
            exit 1
        }
        $token.executor = $To
        $token.stage = $idx + 1
    } elseif ($Stage -gt 0 -and $Stage -le 6) {
        $token.stage = $Stage
        $token.executor = $STAGES[$Stage - 1]
    } else {
        if ($token.stage -ge 6) {
            Write-Host "WARNING: Already at final stage (6/6). Use -Complete." -ForegroundColor Yellow
            exit 1
        }
        $token.stage += 1
        $token.executor = $STAGES[$token.stage - 1]
    }
    $token.updated = $now
    $token | ConvertTo-Json | Set-Content $TOKEN_FILE -Encoding UTF8
    Write-Host "[Pipeline] Advanced to Stage $($token.stage)/6: $($token.executor)" -ForegroundColor Green
    exit 0
}

# --- Complete ---
if ($Complete) {
    $token = Get-CurrentToken
    if (-not $token -or -not $token.active) {
        Write-Host "WARNING: No active pipeline to complete." -ForegroundColor Yellow
        exit 0
    }
    if (-not (Test-Path $HISTORY_DIR)) {
        New-Item -ItemType Directory -Path $HISTORY_DIR -Force | Out-Null
    }
    $archiveName = "pipeline_$(Get-Date -Format 'yyyyMMdd_HHmmss').json"
    $token | Add-Member -MemberType NoteProperty -Name "completed" -Value (Get-Date -Format 'yyyy-MM-ddTHH:mm:ss') -Force
    $token.active = $false
    $token | ConvertTo-Json | Set-Content "$HISTORY_DIR\$archiveName" -Encoding UTF8
    Remove-Item $TOKEN_FILE -Force -ErrorAction SilentlyContinue
    Write-Host "[Pipeline] Completed and archived: $archiveName" -ForegroundColor Green
    Write-Host "  Task: $($token.task)" -ForegroundColor White
    exit 0
}

# No args: show help
Write-Host "Pipeline Token Manager v1.0" -ForegroundColor Cyan
Write-Host ""
Write-Host "Usage:" -ForegroundColor White
Write-Host "  pipeline_token.ps1 -Start -Task 'description'   Create new pipeline"
Write-Host "  pipeline_token.ps1 -Advance -To '红结'          Advance to role"
Write-Host "  pipeline_token.ps1 -Advance                       Auto-advance"
Write-Host "  pipeline_token.ps1 -Complete                       Complete & archive"
Write-Host "  pipeline_token.ps1 -Status                         Show current status"
Write-Host ""
Write-Host "Stages: $($STAGES -join ' -> ')" -ForegroundColor DarkGray
