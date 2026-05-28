# Unified config loader — reads JSON configs from 代码文件/config/

$script:ConfigCache = @{}
$script:ConfigDir = $PSScriptRoot.Replace('\lib', '\config')

function Get-ProjectConfig {
    param(
        [Parameter(Mandatory=$true)]
        [ValidateSet("paths", "api_config", "thresholds")]
        [string]$Section
    )
. "$PSScriptRoot/../lib/init_encoding.ps1"
    if ($script:ConfigCache.ContainsKey($Section)) {
        return $script:ConfigCache[$Section]
    }
    $configFile = Join-Path $script:ConfigDir "$Section.json"
    if (-not (Test-Path $configFile)) {
        Write-Error "Config file not found: $configFile"
        return $null
    }
    $config = Get-Content $configFile -Encoding UTF8 -Raw | ConvertFrom-Json
    $script:ConfigCache[$Section] = $config
    return $config
}

function Get-ConfigPath {
    param([string]$Key)
    $paths = Get-ProjectConfig -Section "paths"
    if (-not $paths) { return $null }
    $root = (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
    $relPath = $paths.directories
    foreach ($part in $Key.Split('.')) {
        $relPath = $relPath.$part
        if (-not $relPath) { break }
    }
    if ($relPath -and ($relPath -is [string])) {
        return Join-Path $root $relPath
    }
    return $null
}
