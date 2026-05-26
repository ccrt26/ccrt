. "$PSScriptRoot/../../lib/init_encoding.ps1"
# 铁律量化 - 股票数据获取模块 (脚本入口)
# 委托给 .psm1 模块处理
# 最后更新：2026-05-24

$modulePath = Join-Path $PSScriptRoot "stock_data_fetcher.psm1"
if (Test-Path $modulePath) {
    Import-Module $modulePath -Force -DisableNameChecking
    Write-Verbose "stock_data_fetcher module loaded" -Verbose:$false
} else {
    Write-Error "Module not found: $modulePath"
}
