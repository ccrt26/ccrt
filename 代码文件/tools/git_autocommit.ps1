<#
.SYNOPSIS
  Git auto-commit shared module. Called at the end of each pipeline output stage.
.DESCRIPTION
  Wraps git add + commit with safety checks: path validation, E5 forbidden patterns,
  no-op when clean, consistent commit message format. Respects .gitignore.
.PARAMETER Module
  Source module name for commit message prefix: daily_pick/deep_analysis/daily_brief/post_eval/data_pipeline/pipeline_eng
.PARAMETER Paths
  One or more paths (relative to project root) to stage and commit.
.PARAMETER Message
  One-line change summary (max 72 chars).
.PARAMETER DryRun
  Show what would be committed without actually committing.
.PARAMETER SkipHook
  Skip pre-commit hook (emergency only, logged with warning).
.OUTPUTS
  JSON: {"success": bool, "commit_hash": "", "files_count": 0, "error": ""}
#>

param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("daily_pick", "deep_analysis", "daily_brief", "post_eval", "data_pipeline", "pipeline_eng", "engineering")]
    [string]$Module,

    [Parameter(Mandatory = $true)]
    [string[]]$Paths,

    [Parameter(Mandatory = $true)]
    [string]$Message,

    [switch]$DryRun,

    [switch]$SkipHook
)

$ErrorActionPreference = "Continue"
$script:ProjectRoot = $PSScriptRoot | Split-Path -Parent | Split-Path -Parent
$LogFile = Join-Path $script:ProjectRoot "临时报告\git_autocommit.log"
$LogDir = Split-Path $LogFile -Parent
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir -Force | Out-Null }

# E5 forbidden patterns (same as pre-commit hook)
$ForbiddenPatterns = @('\.env$', '\.env\.', 'credentials\.(json|txt|yml|yaml|env|conf)$',
    'secret\.(json|txt|yml|yaml)$', 'password', '(?:^|[\\/])token\.(json|txt|yml|yaml|env)$',
    '\.pem$', '\.key$', '\.pfx$', '\.p12$', 'private_key', 'privatekey',
    'id_rsa', 'id_ed25519', 'id_ecdsa', '\.htpasswd$', 'oauth',
    'service_account\.json$', 'settings\.local\.json$')

function Write-AutocommitLog {
    param([string]$Status, [string]$CommitHash, [int]$FileCount, [string]$ErrorMsg)
    $entry = [ordered]@{
        timestamp   = (Get-Date -Format "yyyy-MM-dd HH:mm:ss")
        module      = $Module
        status      = $Status
        commit_hash = $CommitHash
        files_count = $FileCount
        dry_run     = $DryRun.IsPresent
        skip_hook   = $SkipHook.IsPresent
        error       = $ErrorMsg
        message     = $Message
    }
    $entry | ConvertTo-Json -Compress | Out-File -FilePath $LogFile -Append -Encoding utf8
}

# Validate paths: no traversal, must be under project root
$resolvedRoot = (Resolve-Path $script:ProjectRoot).Path
foreach ($p in $Paths) {
    $full = Join-Path $script:ProjectRoot $p
    try {
        $resolved = (Resolve-Path $full -ErrorAction Stop).Path
        if (-not $resolved.StartsWith($resolvedRoot, [StringComparison]::OrdinalIgnoreCase)) {
            $err = "Path traversal blocked: $p"
            Write-AutocommitLog -Status "BLOCKED" -CommitHash "" -FileCount 0 -ErrorMsg $err
            Write-Output '{"success": false, "commit_hash": "", "files_count": 0, "error": "' + $err + '"}'
            exit 1
        }
    } catch {
        $err = "Path not found: $p"
        Write-AutocommitLog -Status "SKIPPED" -CommitHash "" -FileCount 0 -ErrorMsg $err
        Write-Output '{"success": false, "commit_hash": "", "files_count": 0, "error": "' + $err + '"}'
        exit 1
    }
}

# Check for E5 forbidden files in staged paths
Push-Location $script:ProjectRoot
try {
    $allStaged = @()
    foreach ($p in $Paths) {
        $statusOutput = git -c core.quotepath=false status --short -- $p 2>$null
        if ($statusOutput) {
            $allStaged += $statusOutput -split "`n" | ForEach-Object { $_.Trim() } | Where-Object { $_ -ne "" }
        }
    }

    if ($allStaged.Count -eq 0) {
        Write-AutocommitLog -Status "CLEAN" -CommitHash "" -FileCount 0 -ErrorMsg ""
        Write-Output '{"success": true, "commit_hash": "", "files_count": 0, "error": ""}'
        exit 0
    }

    # E5 check on files about to be staged
    foreach ($line in $allStaged) {
        $filePath = $line -replace '^[MADRC ?][MADRC ]?\s+', ''
        foreach ($pat in $ForbiddenPatterns) {
            if (($filePath -replace '\\', '/') -match $pat) {
                $err = "E5 BLOCKED: forbidden file pattern in $filePath"
                Write-AutocommitLog -Status "BLOCKED" -CommitHash "" -FileCount 0 -ErrorMsg $err
                Write-Output '{"success": false, "commit_hash": "", "files_count": 0, "error": "' + $err + '"}'
                Pop-Location
                exit 1
            }
        }
    }

    if ($DryRun) {
        Write-Host "[DRY-RUN] Would commit $($allStaged.Count) files from module: $Module"
        Write-Host "[DRY-RUN] Message: auto: $Module — $Message [$(Get-Date -Format 'yyyyMMdd')]"
        foreach ($line in $allStaged) { Write-Host "  $line" }
        Write-AutocommitLog -Status "DRYRUN" -CommitHash "" -FileCount $allStaged.Count -ErrorMsg ""
        Write-Output '{"success": true, "commit_hash": "", "files_count": ' + $allStaged.Count + ', "error": ""}'
        Pop-Location
        exit 0
    }

    # Stage
    foreach ($p in $Paths) {
        git add -- $p 2>$null
    }

    # Commit
    $commitMsg = "auto: $Module — $Message [$(Get-Date -Format 'yyyyMMdd')]"
    if ($SkipHook) {
        Write-AutocommitLog -Status "WARNING" -CommitHash "" -FileCount 0 -ErrorMsg "SkipHook used"
    }

    $gitArgs = @('commit', '-m', $commitMsg)
    if ($SkipHook) { $gitArgs += '--no-verify' }

    $stderr = @()
    $commitResult = & git $gitArgs 2>&1 | ForEach-Object {
        if ($_ -is [System.Management.Automation.ErrorRecord]) {
            $stderr += $_.Exception.Message
            $_.Exception.Message
        } else {
            $_
        }
    }
    if ($LASTEXITCODE -ne 0) {
        $err = ($stderr -join '; ') -replace '"', "'"
        if (-not $err) { $err = ($commitResult -join '; ') -replace '"', "'" }
        Write-AutocommitLog -Status "FAILED" -CommitHash "" -FileCount 0 -ErrorMsg $err
        Write-Output '{"success": false, "commit_hash": "", "files_count": 0, "error": "' + $err + '"}'
        Pop-Location
        exit 1
    }

    $hash = (git log -1 --format="%h" 2>$null).Trim()
    Write-AutocommitLog -Status "COMMITTED" -CommitHash $hash -FileCount $allStaged.Count -ErrorMsg ""
    Write-Output '{"success": true, "commit_hash": "' + $hash + '", "files_count": ' + $allStaged.Count + ', "error": ""}'
} finally {
    Pop-Location
}
