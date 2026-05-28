<#
.SYNOPSIS
  End-of-day safety net: commits ALL remaining uncommitted changes via git_autocommit.
.DESCRIPTION
  Detects any uncommitted changes (tracked modifications + staged files) and commits them
  under the "engineering" module. No-op when working tree is clean.
  Designed to be called at the end of daily_workflow.ps1 as a catch-all for any changes
  that were not explicitly committed by individual pipeline stages.
.PARAMETER Module
  Module name passed to git_autocommit. Default: "engineering".
.PARAMETER DryRun
  Show what would be committed without actually committing.
.OUTPUTS
  JSON from git_autocommit, or {"success": true, "commit_hash": "", "files_count": 0, "error": ""} when clean.
#>

param(
    [ValidateSet("daily_pick", "deep_analysis", "daily_brief", "post_eval", "data_pipeline", "pipeline_eng", "engineering")]
    [string]$Module = "engineering",
    [switch]$DryRun
)

$ErrorActionPreference = "Continue"
$script:ProjectRoot = $PSScriptRoot | Split-Path -Parent | Split-Path -Parent
$gitAuto = Join-Path $PSScriptRoot "git_autocommit.ps1"

if (-not (Test-Path $gitAuto)) {
    Write-Output '{"success": false, "commit_hash": "", "files_count": 0, "error": "git_autocommit.ps1 not found"}'
    exit 1
}

Push-Location $script:ProjectRoot
try {
    $statusOutput = git -c core.quotepath=false status --short 2>$null
    if (-not $statusOutput -or $statusOutput.Trim() -eq "") {
        Write-Output '{"success": true, "commit_hash": "", "files_count": 0, "error": ""}'
        exit 0
    }

    $splatArgs = @{
        Module  = $Module
        Paths   = @(".")
        Message = "daily sweep"
    }
    if ($DryRun) { $splatArgs['DryRun'] = $true }

    $result = & $gitAuto @splatArgs 2>&1
    Write-Output $result
} finally {
    Pop-Location
}
