# Pipeline Token Manager v1.2 — 流程引擎轻量Wrapper
# 内部委托给 pipeline_engine.ps1，保留CLI接口兼容
# v1.2: 对接 pipeline_engine.ps1 v1.0

param(
    [switch]$Start,
    [switch]$Advance,
    [switch]$Complete,
    [switch]$Status,
    [string]$Task = "",
    [string]$To = "",
    [int]$Stage = -1,
    [string[]]$Scope = @(),
    [switch]$Force
)

$ENGINE = Join-Path $PSScriptRoot "pipeline_engine.ps1"
$STAGES = @("情墨", "新安+旧影", "红结", "新安", "红枫", "PostEval")

function Get-StageIndex($roleName) {
    for ($i = 0; $i -lt $STAGES.Count; $i++) {
        if ($STAGES[$i] -eq $roleName) { return $i }
    }
    return -1
}

function Invoke-Engine {
    param([string]$EngineArgs)
    $cmd = "& '$ENGINE' $EngineArgs"
    try {
        $result = Invoke-Expression $cmd 2>&1
        if ($LASTEXITCODE -ne 0) {
            Write-Host $result -ForegroundColor Red
            exit $LASTEXITCODE
        }
        return $result
    } catch {
        Write-Host "[Token] Engine call failed: $_" -ForegroundColor Red
        exit 1
    }
}

# --- Status (format engine JSON for human reading) ---
if ($Status) {
    $json = Invoke-Engine "-Status"
    try {
        $token = $json | ConvertFrom-Json
        if (-not $token.active) {
            Write-Host "Pipeline: INACTIVE" -ForegroundColor Gray
            exit 0
        }
        Write-Host "Pipeline: ACTIVE" -ForegroundColor Green
        Write-Host "  Task: $($token.task)" -ForegroundColor White
        Write-Host "  Stage: $($token.stage)/6 — $($token.executor) ($($token.stage_name))" -ForegroundColor Cyan
        Write-Host "  Gates: G1=$($token.gate_1) G2=$($token.gate_2) G3=$($token.gate_3)" -ForegroundColor DarkGray
        Write-Host "  Attempts: $($token.attempts)/$($token.max_attempts)" -ForegroundColor $(if ($token.attempts -ge $token.max_attempts) { "Red" } else { "Gray" })
        Write-Host "  Next: $($token.next_action)" -ForegroundColor Magenta
        if ($token.l3_triggered) { Write-Host "  L3: $($token.l3_reason)" -ForegroundColor Red }
        Write-Host "  Started: $($token.started)  Updated: $($token.updated)" -ForegroundColor Gray
    } catch {
        Write-Host $json
    }
    exit 0
}

# --- Start ---
if ($Start) {
    if (-not $Task) {
        Write-Host "ERROR: -Start requires -Task" -ForegroundColor Red
        exit 1
    }
    $scopeArgs = ""
    if ($Scope.Count -gt 0) {
        $scopeArgs = "-Scope " + ($Scope | ForEach-Object { "`"$_`"" }) -join ', '
    }
    Invoke-Engine "-Start -Task `"$Task`" $scopeArgs"
    exit 0
}

# --- Advance ---
if ($Advance) {
    $targetStage = -1
    if ($To) {
        $idx = Get-StageIndex $To
        if ($idx -lt 0) {
            Write-Host "ERROR: Unknown role '$To'. Valid: $($STAGES -join ', ')" -ForegroundColor Red
            exit 1
        }
        $targetStage = $idx + 1
    } elseif ($Stage -gt 0 -and $Stage -le 6) {
        $targetStage = $Stage
    }

    if ($targetStage -gt 0) {
        $current = Invoke-Engine "-Status" | ConvertFrom-Json
        $currentStage = [int]$current.stage
        if ($targetStage -eq $currentStage) {
            Write-Host "WARNING: Already at stage $currentStage ($($STAGES[$currentStage - 1]))." -ForegroundColor Yellow
            exit 0
        }
        if ($targetStage -lt $currentStage) {
            Write-Host "ERROR: Cannot go backwards from stage $currentStage to $targetStage." -ForegroundColor Red
            exit 1
        }
        for ($s = $currentStage; $s -lt $targetStage; $s++) {
            Write-Host "Advancing from stage $s to $($s+1)..." -ForegroundColor DarkGray
            $scopeArgs = ""
            if ($Scope.Count -gt 0) {
                $scopeArgs = "-Scope " + ($Scope | ForEach-Object { "`"$_`"" }) -join ', '
            }
            if ($Force) {
                Invoke-Engine "-Advance -Force $scopeArgs"
            } else {
                Invoke-Engine "-Advance $scopeArgs"
            }
        }
    } else {
        $scopeArgs = ""
        if ($Scope.Count -gt 0) {
            $scopeArgs = "-Scope " + ($Scope | ForEach-Object { "`"$_`"" }) -join ', '
        }
        if ($Force) {
            Invoke-Engine "-Advance -Force $scopeArgs"
        } else {
            Invoke-Engine "-Advance $scopeArgs"
        }
    }
    exit 0
}

# --- Complete ---
if ($Complete) {
    Invoke-Engine "-Complete"
    exit 0
}

# No args: show help
Write-Host "Pipeline Token Manager v1.2 (engine wrapper)" -ForegroundColor Cyan
Write-Host ""
Write-Host "Usage:" -ForegroundColor White
Write-Host "  pipeline_token.ps1 -Start -Task 'description'   Create new pipeline"
Write-Host "  pipeline_token.ps1 -Advance [-To 'role'|-Stage N] [-Force]  Advance"
Write-Host "  pipeline_token.ps1 -Complete                       Complete & archive"
Write-Host "  pipeline_token.ps1 -Status                         Show current status"
Write-Host ""
Write-Host "Engine: pipeline_engine.ps1 (direct access for -Validate/-Retry)" -ForegroundColor DarkGray
Write-Host "Stages: $($STAGES -join ' -> ')" -ForegroundColor DarkGray
