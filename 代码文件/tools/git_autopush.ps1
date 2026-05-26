<#
.SYNOPSIS
  Git auto-push — 推送到GitHub origin/master，直连→代理智能回退
.DESCRIPTION
  推送策略：
  1. 先尝试直连 git -c http.proxy= -c https.proxy= push
  2. 失败则回退到代理配置 git push（使用全局/本地代理设置）
  3. 推送完成后日志记录
.OUTPUTS
  JSON: {"success": bool, "commit_hash": "", "method": "direct|proxy", "error": ""}
#>

param(
    [switch]$DryRun
)

$ErrorActionPreference = "Continue"
$script:ProjectRoot = $PSScriptRoot | Split-Path -Parent | Split-Path -Parent
$LogFile = Join-Path $script:ProjectRoot "临时报告\git_autocommit.log"
$LogDir = Split-Path $LogFile -Parent
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir -Force | Out-Null }

function Write-PushLog {
    param([string]$Status, [string]$Method, [string]$ErrorMsg)
    $entry = [ordered]@{
        timestamp   = (Get-Date -Format "yyyy-MM-dd HH:mm:ss")
        action      = "PUSH"
        status      = $Status
        method      = $Method
        error       = $ErrorMsg
    }
    $entry | ConvertTo-Json -Compress | Out-File -FilePath $LogFile -Append -Encoding utf8
}

Push-Location $script:ProjectRoot

# 检查是否有未推送的提交
$branch = (git branch --show-current 2>$null).Trim()
if (-not $branch) {
    $err = "Not on any branch"
    Write-PushLog -Status "FAILED" -Method "" -ErrorMsg $err
    Write-Output '{"success": false, "commit_hash": "", "method": "", "error": "' + $err + '"}'
    Pop-Location
    exit 1
}

$ahead = (git rev-list --count origin/$branch..$branch 2>$null).Trim()
if ($ahead -eq "0" -or (-not $ahead)) {
    Write-PushLog -Status "UP_TO_DATE" -Method "" -ErrorMsg ""
    Write-Output '{"success": true, "commit_hash": "", "method": "none", "error": ""}'
    Pop-Location
    exit 0
}

if ($DryRun) {
    Write-Host "[DRY-RUN] Would push $ahead commits on branch: $branch"
    Write-Output '{"success": true, "commit_hash": "", "method": "dryrun", "error": ""}'
    Pop-Location
    exit 0
}

# Step 1: 直连尝试
Write-Host "[autopush] Trying direct connection (no proxy)..."
$directResult = & git -c http.proxy= -c https.proxy= push origin $branch 2>&1
if ($LASTEXITCODE -eq 0) {
    $hash = (git log -1 --format="%h" 2>$null).Trim()
    Write-Host "[autopush] Direct push OK — $hash"
    Write-PushLog -Status "PUSHED" -Method "direct" -ErrorMsg ""
    Write-Output '{"success": true, "commit_hash": "' + $hash + '", "method": "direct", "error": ""}'
    Pop-Location
    exit 0
}

# Step 2: 兜底 — 打印直连失败原因
$directError = ($directResult -join '; ') -replace '"', "'"
if ($directError.Length -gt 200) { $directError = $directError.Substring(0, 200) }
Write-Host "[autopush] Direct failed: $directError"

# Step 3: 代理回退
Write-Host "[autopush] Retrying with proxy config..."
Push-Location $script:ProjectRoot
$proxyResult = & git push origin $branch 2>&1
if ($LASTEXITCODE -eq 0) {
    $hash = (git log -1 --format="%h" 2>$null).Trim()
    Write-Host "[autopush] Proxy push OK — $hash"
    Write-PushLog -Status "PUSHED" -Method "proxy" -ErrorMsg ""
    Write-Output '{"success": true, "commit_hash": "' + $hash + '", "method": "proxy", "error": ""}'
    Pop-Location
    exit 0
}

$proxyError = ($proxyResult -join '; ') -replace '"', "'"
if ($proxyError.Length -gt 200) { $proxyError = $proxyError.Substring(0, 200) }
Write-PushLog -Status "FAILED" -Method "" -ErrorMsg $proxyError
Write-Output '{"success": false, "commit_hash": "", "method": "", "error": "' + $proxyError + '"}'
Pop-Location
exit 1
