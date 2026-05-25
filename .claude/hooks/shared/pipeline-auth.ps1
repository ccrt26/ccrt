# pipeline-auth.ps1 v1.0 - Code File Write Protection Shared Auth Module
# Code Level: L1 (Security Infrastructure)
# Single source of truth: pre-commit hook + write_protection hook both dot-source this module
# All protected paths, executor rules, gate checks, scope rules defined here once.

$script:ProtectedPaths = @(
    '^代码文件[\\/]',
    '^模拟交易[\\/]sim_orchestrator\.ps1$',
    '^模拟交易[\\/]交易引擎[\\/]',
    '^模拟交易[\\/]每日荐股赛道[\\/]交易引擎[\\/]',
    '^模拟交易[\\/]共享模块[\\/]',
    '^模拟交易[\\/]否决审查[\\/]',
    '^模拟交易[\\/]分析[\\/]',
    '^模拟交易[\\/]展示[\\/]',
    '^模拟交易[\\/]工具[\\/]'
)

# Valid executor values for code file write authorization (from pipeline engine STAGE_EXECUTORS)
$script:ValidExecutors = @(
    [System.Text.Encoding]::UTF8.GetString([byte[]](0xe7, 0xba, 0xa2, 0xe7, 0xbb, 0x93)),  # 红结
    [System.Text.Encoding]::UTF8.GetString([byte[]](0xe7, 0xba, 0xa2, 0xe6, 0x9e, 0xab))   # 红枫
)

function Test-PipelineAuthorization {
    param(
        [Parameter(Mandatory=$true)]
        [string]$FilePath,

        [Parameter(Mandatory=$true)]
        [string]$ProjectRoot,

        [Parameter(Mandatory=$false)]
        [string[]]$ExtraPatterns = @()
    )

    $normalizedFile = $FilePath -replace '\\', '/'

    # Step 1: Check if file is in any protected path
    $isProtected = $false
    $allPatterns = $script:ProtectedPaths + $ExtraPatterns
    foreach ($pat in $allPatterns) {
        if ($normalizedFile -match $pat) {
            $isProtected = $true
            break
        }
    }

    if (-not $isProtected) {
        return [PSCustomObject]@{Authorized=$true; Reason="Not a protected path"; Executor=""; Gate1=""; ScopeMatch=$true}
    }

    # Step 2: Check pipeline token existence
    $tokenPath = Join-Path $ProjectRoot ".claude\pipeline_active.json"
    if (-not (Test-Path $tokenPath)) {
        return [PSCustomObject]@{Authorized=$false; Reason="No pipeline token found. Code file changes require active pipeline."; Executor=""; Gate1=""; ScopeMatch=$false}
    }

    try {
        $token = Get-Content $tokenPath -Raw -Encoding UTF8 | ConvertFrom-Json
    } catch {
        return [PSCustomObject]@{Authorized=$false; Reason="Pipeline token corrupted: $_"; Executor=""; Gate1=""; ScopeMatch=$false}
    }

    # Step 3: F2 checks - active + executor + gate_1
    if (-not $token.active -or $token.active -ne $true) {
        return [PSCustomObject]@{Authorized=$false; Reason="Pipeline not active (active=$($token.active))"; Executor=""; Gate1=$($token.gate_1); ScopeMatch=$false}
    }

    $execOk = $false
    foreach ($valid in $script:ValidExecutors) {
        if ($token.executor -eq $valid) { $execOk = $true; break }
    }
    if (-not $execOk) {
        return [PSCustomObject]@{Authorized=$false; Reason="Invalid executor: $($token.executor)"; Executor=""; Gate1=$($token.gate_1); ScopeMatch=$false}
    }

    if ($token.gate_1 -ne "PASS") {
        return [PSCustomObject]@{Authorized=$false; Reason="Gate_1 not PASS (current: $($token.gate_1)). Design phase incomplete."; Executor=$($token.executor); Gate1=$($token.gate_1); ScopeMatch=$false}
    }

    # Step 4: F3 scope check
    $hasScopeField = $token.PSObject.Properties.Name -contains 'files_scope'
    if ($hasScopeField) {
        if ($token.files_scope.Count -gt 0) {
            $inScope = $false
            foreach ($scope in $token.files_scope) {
                $normalizedScope = ($scope -replace '\\', '/')
                if ($normalizedFile.StartsWith($normalizedScope, [StringComparison]::OrdinalIgnoreCase)) {
                    $inScope = $true
                    break
                }
            }
            if (-not $inScope) {
                return [PSCustomObject]@{Authorized=$false; Reason="File outside pipeline scope (declared: $($token.files_scope -join ', '))"; Executor=$($token.executor); Gate1="PASS"; ScopeMatch=$false}
            }
        } else {
            return [PSCustomObject]@{Authorized=$false; Reason="Pipeline files_scope is empty (declares no code files in scope)"; Executor=$($token.executor); Gate1="PASS"; ScopeMatch=$false}
        }
    }

    return [PSCustomObject]@{Authorized=$true; Reason="Pipeline authorized: executor valid, gate_1=PASS, scope OK"; Executor=$($token.executor); Gate1="PASS"; ScopeMatch=$true}
}
