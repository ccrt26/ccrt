. "$PSScriptRoot/../../lib/init_encoding.ps1"
# 铁律量化 - 股票数据获取模块
# 数据源：腾讯行情[1], 新浪K线[2], 东方财富财务[3][6][7][9][10]
# 原文件已拆分为 modules/ 目录，本文件保留作为兼容入口
# 最后更新：2026-05-24

# Dot-source sub-modules in dependency order (module scope)
. "$PSScriptRoot/modules/core.ps1"
. "$PSScriptRoot/modules/quote.ps1"
. "$PSScriptRoot/modules/financial.ps1"
. "$PSScriptRoot/modules/technical.ps1"
. "$PSScriptRoot/modules/sector.ps1"
. "$PSScriptRoot/modules/biying.ps1"
. "$PSScriptRoot/modules/fundflow.ps1"
. "$PSScriptRoot/modules/external.ps1"
. "$PSScriptRoot/modules/test.ps1"

# Export all functions for module consumers
Export-ModuleMember -Function *
