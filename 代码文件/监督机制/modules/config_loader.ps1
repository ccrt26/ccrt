# P2-1: 配置中心化 — 共享配置加载器
# 使用方式: . (Join-Path $PSScriptRoot "config_loader.ps1"); $cfg = Get-ProjectConfig
# 或指定脚本路径: $cfg = Get-ProjectConfig -StartDir $PSScriptRoot

function Get-ProjectConfig {
    param([string]$StartDir = $PSScriptRoot)

    # 上溯找项目根目录 (包含 代码文件/数据/project_config.json)
    $dir = $StartDir
    $maxDepth = 10
    $found = $false
    for ($i = 0; $i -lt $maxDepth; $i++) {
        $configPath = Join-Path $dir "代码文件\数据\project_config.json"
        if (Test-Path $configPath) {
            $found = $true
            break
        }
        $parent = Split-Path -Parent $dir
        if ($parent -eq $dir) { break }
        $dir = $parent
    }
    if (-not $found) {
        Write-Warning "Get-ProjectConfig: 未找到 project_config.json (从 $StartDir 上溯)"
        return $null
    }

    $cfg = Get-Content $configPath -Raw -Encoding UTF8 | ConvertFrom-Json
    # 注入实际根目录
    $cfg | Add-Member -MemberType NoteProperty -Name "_resolvedRoot" -Value $dir -Force

    # 展开所有路径为绝对路径
    $cfg._paths = @{}
    foreach ($prop in $cfg.paths.PSObject.Properties) {
        $cfg._paths[$prop.Name] = Join-Path $dir $prop.Value
    }
    foreach ($prop in $cfg.tiers.PSObject.Properties) {
        $cfg._paths[$prop.Name] = Join-Path $dir $prop.Value
    }

    return $cfg
}
