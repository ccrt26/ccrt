# 铁律量化 · Pipeline Engine v1.0
# 流程状态机引擎 — 管理6阶段全生命周期，输出阿黑执行指令
# 设计文档: 审计报告/架构设计/design_pipeline_engine_v1.0_流程引擎化.md
# 代码等级: L1 (策略/基础设施)
# BOM: UTF-8 with BOM for Windows PowerShell compatibility

param(
    [switch]$Status,
    [switch]$Start,
    [switch]$Validate,
    [switch]$Advance,
    [switch]$Retry,
    [switch]$Complete,
    [string]$Task = "",
    [string]$OutputPath = "",
    [string[]]$Scope = @(),
    [switch]$Force
)
. "$PSScriptRoot/../lib/init_encoding.ps1"

$ErrorActionPreference = "Stop"
$BASE = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$TOKEN_FILE = "$BASE\.claude\pipeline_active.json"
$HISTORY_DIR = "$BASE\.claude\pipeline_history"
$DESIGN_DIR = "$BASE\审计报告\架构设计"
$AUDIT_DIR = "$BASE\审计报告"
$CODE_DIR = "$BASE\代码文件"

$STAGE_EXECUTORS = @("情墨", "新安+旧影", "红结", "新安", "红枫", "PostEval")
$STAGE_NAMES = @("架构设计", "架构审查", "编码实现", "上线前验证", "灰度部署", "后评估")

$SCRIPT_NAME = [System.IO.Path]::GetFileName($PSCommandPath)

# ============================================================
# Utility Functions
# ============================================================

function Write-EngineError($Message, $Detail = "") {
    $err = @{ error = $true; message = $Message; detail = $Detail; script = $SCRIPT_NAME }
    $err | ConvertTo-Json -Compress | Write-Output
    exit 1
}

function Get-UTCTimestamp {
    return (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ss")
}

function Read-Token {
    if (-not (Test-Path $TOKEN_FILE)) { return $null }
    try {
        $content = Get-Content $TOKEN_FILE -Raw -Encoding UTF8
        if (-not $content.Trim()) { return $null }
        return $content | ConvertFrom-Json
    } catch {
        return $null
    }
}

function Write-Token($Token) {
    $dir = Split-Path $TOKEN_FILE -Parent
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
    $Token | ConvertTo-Json -Depth 4 | Set-Content $TOKEN_FILE -Encoding UTF8
}

function Write-History($Token) {
    if (-not (Test-Path $HISTORY_DIR)) { New-Item -ItemType Directory -Path $HISTORY_DIR -Force | Out-Null }
    $ts = Get-Date -Format "yyyyMMdd_HHmmss"
    $fname = "pipeline_${ts}_stage$($Token.stage).json"
    $Token | ConvertTo-Json -Depth 4 | Set-Content "$HISTORY_DIR\$fname" -Encoding UTF8
}

# Schema migration: upgrade old token format to v1.0
function Migrate-Schema($Token) {
    $props = $Token | Get-Member -MemberType NoteProperty | ForEach-Object { $_.Name }
    if ("schema_version" -in $props) { return $Token }

    $migrated = @{
        schema_version = "1.0"
        active         = $Token.active
        task           = if ($Token.task) { $Token.task } else { "" }
        stage          = if ($Token.stage) { [int]$Token.stage } else { 0 }
        executor       = if ($Token.executor) { $Token.executor } else { "" }
        stage_name     = ""
        next_action    = "invoke_role"
        gate_1         = "PENDING"
        gate_2         = "PENDING"
        gate_3         = "PENDING"
        attempts       = 0
        max_attempts   = 3
        l3_triggered   = $false
        l3_reason      = ""
        files_scope    = @()
        loop_context   = ""
        stage_history  = @()
        started        = if ($Token.started) { $Token.started } else { Get-UTCTimestamp }
        updated        = Get-UTCTimestamp
    }
    if ($migrated.stage -ge 1 -and $migrated.stage -le 6) {
        $migrated.stage_name = $STAGE_NAMES[$migrated.stage - 1]
    }
    Write-Host "[Engine] Schema migrated to v1.0" -ForegroundColor DarkGray
    return $migrated
}

function Get-LoopContext($S) {
    $idx = $S - 1
    if ($idx -lt 0 -or $idx -ge $STAGE_EXECUTORS.Count) { return "Pipeline executing" }
    $name = $STAGE_NAMES[$idx]
    $exec = $STAGE_EXECUTORS[$idx]
    return "Stage $S/6: $name | Executor: $exec"
}

# ============================================================
# Stage Completion Detection
# ============================================================

function Test-Stage1Complete {
    if (-not (Test-Path $DESIGN_DIR)) { return $false, "Design dir missing: $DESIGN_DIR" }
    $designs = Get-ChildItem $DESIGN_DIR -Filter "design_*.md" -ErrorAction SilentlyContinue
    if (-not $designs -or $designs.Count -eq 0) { return $false, "No design_*.md found" }
    $latest = $designs | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    $content = Get-Content $latest.FullName -Raw -Encoding UTF8 -ErrorAction SilentlyContinue
    if ($content -notmatch 'pipeline_stage:\s*complete') {
        return $false, "Design doc missing: pipeline_stage: complete"
    }
    if ($content -notmatch 'finance_confirmed:\s*true') {
        return $false, "Design doc missing: finance_confirmed: true"
    }
    return $true, $latest.FullName
}

function Test-Stage2Complete {
    $reports = @(Get-ChildItem $AUDIT_DIR -Filter "*审查*" -ErrorAction SilentlyContinue) +
               @(Get-ChildItem $AUDIT_DIR -Filter "*审计*" -ErrorAction SilentlyContinue)
    if ($reports.Count -lt 2) {
        return $false, "Need 2+ review reports (found $($reports.Count))"
    }
    $gatePass = $false
    foreach ($r in $reports) {
        $c = Get-Content $r.FullName -Raw -Encoding UTF8 -ErrorAction SilentlyContinue
        if ($c -match 'gate.*PASS|Gate.*PASS|PASS.*通过') { $gatePass = $true; break }
    }
    if (-not $gatePass) { return $false, "No gate:PASS found in review reports" }
    return $true, ($reports | ForEach-Object { $_.Name }) -join ", "
}

function Test-Stage3Complete {
    $gitOk = $null -ne (Get-Command git -ErrorAction SilentlyContinue)
    if (-not $gitOk) { return $false, "git not available" }
    $oldEAP = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $oldOutputEncoding = [Console]::OutputEncoding
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    try {
        $unstaged  = git -c core.quotepath=false diff --name-only 2>&1 | Where-Object { $_ -notmatch 'warning:|LF will be replaced|CRLF' }
        $staged    = git -c core.quotepath=false diff --cached --name-only 2>&1 | Where-Object { $_ -notmatch 'warning:|LF will be replaced|CRLF' }
        $untracked = git -c core.quotepath=false ls-files --others --exclude-standard 2>&1 | Where-Object { $_ -notmatch 'warning:|LF will be replaced|CRLF' }
        $codeFiles = @($unstaged) + @($staged) + @($untracked) | Where-Object { $_ -match '^代码文件[\\/]' }
        if ($codeFiles.Count -eq 0) {
            $lastMsg = git log -1 --format="%s" 2>&1
            return $false, "No changes in 代码文件/ (last commit: $lastMsg)"
        }
        return $true, ($codeFiles -join ", ")
    } catch {
        return $false, "git error: $_"
    } finally {
        $ErrorActionPreference = $oldEAP
        [Console]::OutputEncoding = $oldOutputEncoding
    }
}

function Test-Stage4Complete {
    $checks = @("变更影响", "测试报告", "回归", "红线")
    $missing = @()
    foreach ($c in $checks) {
        $found = Get-ChildItem $AUDIT_DIR -Filter "*$c*" -ErrorAction SilentlyContinue
        if (-not $found) { $missing += $c }
    }
    if ($missing.Count -gt 0) { return $false, "Missing reports: $($missing -join ', ')" }
    return $true, "All 4 verification reports present"
}

function Test-Stage5Complete {
    $deploy = (Get-ChildItem $AUDIT_DIR -Filter "*部署*" -ErrorAction SilentlyContinue) +
              (Get-ChildItem $AUDIT_DIR -Filter "*发布*" -ErrorAction SilentlyContinue) +
              (Get-ChildItem $AUDIT_DIR -Filter "*灰度*" -ErrorAction SilentlyContinue)
    $rollback = Get-ChildItem $AUDIT_DIR -Filter "*回滚*" -ErrorAction SilentlyContinue
    $missing = @()
    if ($deploy.Count -eq 0) { $missing += "deploy_record" }
    if ($rollback.Count -eq 0) { $missing += "rollback_plan" }
    if ($missing.Count -gt 0) { return $false, "Missing: $($missing -join ', ')" }
    return $true, "Deploy record + rollback plan ready"
}

function Test-Stage6Complete {
    $evalReports = Get-ChildItem $BASE -Filter "*后评估*" -Recurse -ErrorAction SilentlyContinue
    if ($evalReports.Count -eq 0) { return $false, "No post-evaluation report found" }
    return $true, $evalReports[0].FullName
}

function Test-StageComplete($S) {
    switch ($S) {
        1 { return Test-Stage1Complete }
        2 { return Test-Stage2Complete }
        3 { return Test-Stage3Complete }
        4 { return Test-Stage4Complete }
        5 { return Test-Stage5Complete }
        6 { return Test-Stage6Complete }
        default { return $false, "Invalid stage: $S" }
    }
}

# ============================================================
# Gate Checks
# ============================================================

# Gate 1: 设计闸 — 设计文档 + 腰子全团强制咨询(§6.0) + 新安+旧影审查
# finance_confirmed:true 表示腰子已完成 山猫→玉夜→流金→青山 全团咨询并签字
function Test-Gate1($Token) {
    $pass, $info = Test-Stage1Complete
    if (-not $pass) {
        $Token.gate_1 = "FAIL"
        $Token.attempts += 1
        return $Token, $info
    }
    $pass2, $info2 = Test-Stage2Complete
    if (-not $pass2) {
        $Token.gate_1 = "PENDING_REVIEW"
        return $Token, "Design OK, waiting for review: $info2"
    }
    $Token.gate_1 = "PASS"
    return $Token, "Gate1 PASS"
}

function Test-Gate2($Token) {
    $pass, $info = Test-Stage3Complete
    if (-not $pass) {
        $Token.gate_2 = "FAIL"
        $Token.attempts += 1
        return $Token, $info
    }
    $pass2, $info2 = Test-Stage4Complete
    if (-not $pass2) {
        $Token.gate_2 = "FAIL"
        $Token.attempts += 1
        return $Token, "Code exists but verification missing: $info2"
    }
    $Token.gate_2 = "PASS"
    return $Token, "Gate2 PASS"
}

function Test-Gate3($Token) {
    if ($Token.gate_1 -ne "PASS" -or $Token.gate_2 -ne "PASS") {
        $Token.gate_3 = "FAIL"
        return $Token, "Prerequisite gates not passed (G1=$($Token.gate_1), G2=$($Token.gate_2))"
    }
    $pass, $info = Test-Stage5Complete
    if (-not $pass) {
        $Token.gate_3 = "FAIL"
        $Token.attempts += 1
        return $Token, $info
    }
    $Token.gate_3 = "PASS"
    return $Token, "Gate3 PASS"
}

# ============================================================
# next_action Computation
# ============================================================

function Get-NextAction($Token) {
    if (-not $Token.active) { return "none" }
    if ($Token.attempts -ge $Token.max_attempts) { return "stop_l3" }

    switch ($Token.stage) {
        1 {
            if ($Token.gate_1 -eq "FAIL") { return "retry" }
            return "invoke_role"
        }
        2 {
            if ($Token.gate_1 -eq "PASS") { return "advance" }
            if ($Token.gate_1 -eq "FAIL") { return "retry" }
            return "invoke_role"
        }
        3 {
            if ($Token.gate_2 -eq "FAIL") { return "retry" }
            return "invoke_role"
        }
        4 {
            if ($Token.gate_2 -eq "PASS") { return "advance" }
            if ($Token.gate_2 -eq "FAIL") { return "retry" }
            return "invoke_role"
        }
        5 {
            if ($Token.gate_3 -eq "FAIL") { return "retry" }
            return "invoke_role"
        }
        6 { return "invoke_role" }
        default { return "none" }
    }
}

# ============================================================
# Operation: -Status
# ============================================================

function Invoke-Status {
    $token = Read-Token
    if (-not $token) {
        @{ active = $false; stage = 0; next_action = "none"; loop_context = "" } | ConvertTo-Json -Compress | Write-Output
        exit 0
    }
    $token = Migrate-Schema $token
    $token.updated = Get-UTCTimestamp

    if ($token.active -and $token.stage -ge 1 -and $token.stage -le 6) {
        $token.stage_name = $STAGE_NAMES[$token.stage - 1]
        $token.loop_context = Get-LoopContext $token.stage
    }

    # Stale pipeline detection (>30min idle = L3 escalation)
    if ($token.active -and $token.updated) {
        try {
            $lastUpdate = [DateTime]::Parse($token.updated)
            if (((Get-Date).ToUniversalTime() - $lastUpdate).TotalMinutes -gt 30) {
                $token.l3_triggered = $true
                $token.l3_reason = "Pipeline stalled: >30min since last update ($($token.updated))"
            }
        } catch { }
    }

    if ($token.l3_triggered) {
        $token.next_action = "stop_l3"
    } else {
        $token.next_action = Get-NextAction $token
    }

    # Stage 6 completion check
    if ($token.stage -eq 6 -and $token.gate_1 -eq "PASS" -and $token.gate_2 -eq "PASS" -and $token.gate_3 -eq "PASS") {
        $pass, $info = Test-Stage6Complete
        if ($pass) { $token.next_action = "done" }
    }

    Write-Token $token
    @{
        schema_version = $token.schema_version
        active    = $token.active
        task      = $token.task
        stage     = $token.stage
        stage_name = $token.stage_name
        executor  = $token.executor
        next_action = $token.next_action
        gate_1    = $token.gate_1
        gate_2    = $token.gate_2
        gate_3    = $token.gate_3
        attempts  = $token.attempts
        max_attempts = $token.max_attempts
        l3_triggered = $token.l3_triggered
        l3_reason = $token.l3_reason
        files_scope = if ($token.files_scope) { @($token.files_scope) } else { @() }
        loop_context = $token.loop_context
        stage_history = $token.stage_history
        started   = $token.started
        updated   = $token.updated
    } | ConvertTo-Json -Compress -Depth 3 | Write-Output
    exit 0
}

# ============================================================
# Operation: -Start
# ============================================================

function Invoke-Start {
    if (-not $Task) { Write-EngineError "-Start requires -Task" }
    $existing = Read-Token
    if ($existing -and $existing.active) {
        Write-EngineError "Active pipeline exists" "task=$($existing.task), stage=$($existing.stage)"
    }
    $now = Get-UTCTimestamp
    $token = @{
        schema_version = "1.0"
        active    = $true
        task      = $Task
        stage     = 1
        executor  = $STAGE_EXECUTORS[0]
        stage_name = $STAGE_NAMES[0]
        next_action = "invoke_role"
        gate_1    = "PENDING"
        gate_2    = "PENDING"
        gate_3    = "PENDING"
        attempts  = 0
        max_attempts = 3
        l3_triggered = $false
        l3_reason = ""
        files_scope = @($Scope)
        loop_context = Get-LoopContext 1
        stage_history = @(@{stage=1; executor=$STAGE_EXECUTORS[0]; entered=$now; gate="PENDING"; output=""})
        started   = $now
        updated   = $now
    }
    Write-Token $token
    Write-Host "[Engine] Pipeline started - Stage 1/6" -ForegroundColor Green
    Write-Host "  Task: $Task" -ForegroundColor White
    exit 0
}

# ============================================================
# Operation: -Validate
# ============================================================

function Invoke-Validate {
    $token = Read-Token
    if (-not $token -or -not $token.active) { Write-EngineError "No active pipeline" }
    $token = Migrate-Schema $token
    $now = Get-UTCTimestamp
    $token.updated = $now
    $s = $token.stage

    $pass, $info = Test-StageComplete $s
    Write-Host "[Engine] Validate Stage $s : $info" -ForegroundColor Cyan

    if (-not $pass) {
        $token.attempts += 1
        if ($token.attempts -ge $token.max_attempts) {
            $token.l3_triggered = $true
            $token.l3_reason = "Stage $s validation failed $($token.attempts) times: $info"
        }
        Write-Token $token
        Write-History $token
        Write-Host "[Engine] Validate FAIL (attempt $($token.attempts)/$($token.max_attempts))" -ForegroundColor Red
        exit 1
    }

    # Update stage history
    $entry = @{stage=$s; executor=$token.executor; gate="PASS"; output=$OutputPath; validated=$now}
    $newHistory = @()
    foreach ($h in $token.stage_history) {
        if ([int]$h.stage -ne $s) { $newHistory += $h }
    }
    $newHistory += $entry
    $token.stage_history = $newHistory

    # Run gate check for transitions
    $gateColor = "Green"
    if ($s -eq 1 -or $s -eq 2) {
        $token, $gateInfo = Test-Gate1 $token
        if ($token.gate_1 -ne "PASS") { $gateColor = "Yellow" }
        Write-Host "[Engine] Gate1: $gateInfo" -ForegroundColor $gateColor
    }
    if ($s -eq 3 -or $s -eq 4) {
        $token, $gateInfo = Test-Gate2 $token
        if ($token.gate_2 -ne "PASS") { $gateColor = "Yellow" }
        Write-Host "[Engine] Gate2: $gateInfo" -ForegroundColor $gateColor
    }
    if ($s -eq 5) {
        $token, $gateInfo = Test-Gate3 $token
        if ($token.gate_3 -ne "PASS") { $gateColor = "Yellow" }
        Write-Host "[Engine] Gate3: $gateInfo" -ForegroundColor $gateColor
    }

    Write-Token $token
    Write-History $token
    Write-Host "[Engine] Validate PASS" -ForegroundColor Green
    exit 0
}

# ============================================================
# Operation: -Advance
# ============================================================

function Invoke-Advance {
    $token = Read-Token
    if (-not $token -or -not $token.active) { Write-EngineError "No active pipeline" }
    $token = Migrate-Schema $token
    $now = Get-UTCTimestamp
    $cs = $token.stage

    if ($cs -ge 6) {
        if ($token.gate_1 -eq "PASS" -and $token.gate_2 -eq "PASS" -and $token.gate_3 -eq "PASS") {
            Write-Host "[Engine] All stages complete. Use -Complete to finish." -ForegroundColor Green
            exit 0
        }
        Write-EngineError "Already at final stage (6/6)" "G1=$($token.gate_1) G2=$($token.gate_2) G3=$($token.gate_3)"
    }

    # Determine which gate is needed
    $gateName = switch ($cs) {
        { $_ -in @(1,2) } { "gate_1" }
        { $_ -in @(3,4) } { "gate_2" }
        5 { "gate_3" }
        default { $null }
    }
    if ($gateName) {
        $gateVal = $token.$gateName
        if ($gateVal -ne "PASS") {
            if (-not $Force) {
                Write-EngineError "Gate not passed ($gateName=$gateVal). Use -Force to bypass." "stage=$cs"
            }
            Write-Host "[Engine] WARNING: Gate $gateName bypassed with -Force" -ForegroundColor Yellow
        }
    }

    $ns = $cs + 1
    $token.stage = $ns
    $token.executor = $STAGE_EXECUTORS[$ns - 1]
    $token.stage_name = $STAGE_NAMES[$ns - 1]
    $token.attempts = 0
    $token.l3_triggered = $false
    $token.l3_reason = ""
    $token.loop_context = Get-LoopContext $ns
    $token.updated = $now
    if ($Scope.Count -gt 0) { $token.files_scope = @($Scope) }
    $token.stage_history += @{stage=$ns; executor=$STAGE_EXECUTORS[$ns-1]; entered=$now; gate="PENDING"; output=""}

    Write-Token $token
    Write-History $token
    Write-Host "[Engine] Advanced to Stage $ns/6" -ForegroundColor Green
    exit 0
}

# ============================================================
# Operation: -Retry
# ============================================================

function Invoke-Retry {
    $token = Read-Token
    if (-not $token -or -not $token.active) { Write-EngineError "No active pipeline" }
    $token = Migrate-Schema $token
    $now = Get-UTCTimestamp

    $token.attempts += 1
    $token.updated = $now

    if ($token.attempts -ge $token.max_attempts) {
        $token.l3_triggered = $true
        $token.l3_reason = "Stage $($token.stage) max retries reached ($($token.attempts)/$($token.max_attempts))"
        Write-Token $token
        Write-History $token
        Write-Host "[Engine] L3 escalation: max retries reached" -ForegroundColor Red
        exit 1
    }

    Write-Token $token
    Write-History $token
    Write-Host "[Engine] Retry Stage $($token.stage): attempt $($token.attempts)/$($token.max_attempts)" -ForegroundColor Yellow
    Write-Host "  Executor: $($token.executor) - fix issues and re-submit" -ForegroundColor Gray
    exit 0
}

# ============================================================
# Operation: -Complete
# ============================================================

function Invoke-Complete {
    $token = Read-Token
    if (-not $token -or -not $token.active) {
        Write-Host "[Engine] No active pipeline to complete." -ForegroundColor Gray
        exit 0
    }
    $token = Migrate-Schema $token

    if (-not (Test-Path $HISTORY_DIR)) { New-Item -ItemType Directory -Path $HISTORY_DIR -Force | Out-Null }
    $ts = Get-Date -Format "yyyyMMdd_HHmmss"
    $archiveName = "pipeline_${ts}_completed.json"
    $token | Add-Member -MemberType NoteProperty -Name "completed" -Value (Get-UTCTimestamp) -Force
    $token.active = $false
    $token | ConvertTo-Json -Depth 4 | Set-Content "$HISTORY_DIR\$archiveName" -Encoding UTF8

    # Reset to inactive
    $default = @{
        schema_version = "1.0"
        active    = $false
        task      = ""
        executor  = ""
        stage     = 0
        stage_name = ""
        next_action = "none"
        gate_1    = "PENDING"
        gate_2    = "PENDING"
        gate_3    = "PENDING"
        attempts  = 0
        max_attempts = 3
        l3_triggered = $false
        l3_reason = ""
        files_scope = @()
        loop_context = ""
        stage_history = @()
        started   = Get-UTCTimestamp
        updated   = Get-UTCTimestamp
    }
    $default | ConvertTo-Json -Depth 3 | Set-Content $TOKEN_FILE -Encoding UTF8

    Write-Host "[Engine] Pipeline completed and archived: $archiveName" -ForegroundColor Green
    Write-Host "  Task: $($token.task)" -ForegroundColor White
    Write-Host "  Stages: $($token.stage_history.Count)" -ForegroundColor Gray
    exit 0
}

# ============================================================
# Dispatch
# ============================================================

$chosen = @($Status, $Start, $Validate, $Advance, $Retry, $Complete | Where-Object { $_ }).Count
if ($chosen -eq 0) {
    Write-Host "Pipeline Engine v1.0" -ForegroundColor Cyan
    Write-Host "Usage:" -ForegroundColor White
    Write-Host "  -Start -Task 'desc'   Initialize new pipeline"
    Write-Host "  -Status               Get current state (JSON)"
    Write-Host "  -Validate [-OutputPath '..']  Validate stage completion"
    Write-Host "  -Advance [-Force]     Advance to next stage"
    Write-Host "  -Retry                Retry current stage"
    Write-Host "  -Complete             Archive and reset"
    exit 0
}

if ($chosen -gt 1) { Write-EngineError "Only one operation at a time" "Multiple switches set" }

if ($Status)    { Invoke-Status }
if ($Start)     { Invoke-Start }
if ($Validate)  { Invoke-Validate }
if ($Advance)   { Invoke-Advance }
if ($Retry)     { Invoke-Retry }
if ($Complete)  { Invoke-Complete }
