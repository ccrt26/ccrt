#!/usr/bin/env python3
"""精确拆分 stock_data_fetcher.ps1 → modules/ 目录"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "stock_data_fetcher.ps1")
DST = os.path.join(HERE, "modules")
LEGACY = os.path.join(HERE, "stock_data_fetcher_legacy.ps1")
os.makedirs(DST, exist_ok=True)

with open(SRC, "r", encoding="utf-8-sig") as f:
    all_lines = f.read().split("\n")

def get(start, end):
    """提取 [start, end) 行 (0-indexed)，去掉尾空行"""
    block = list(all_lines[start:end])
    while block and not block[-1].strip():
        block.pop()
    return block

# ── core.ps1: 基础设施（配置+限速器+缓存） ──
mod = get(0, 123)  # header + 配置 + Invoke-ThrottledApiCall + Save/Load-DataCache + Invoke-DataWithCache + Get-LastUsedSource
with open(os.path.join(DST, "core.ps1"), "w", encoding="utf-8") as f:
    f.write("\n".join(mod))
print(f"core.ps1: {len(mod)} lines")

# ── quote.ps1: 行情+K线+技术指标 ──
mod = []
mod.append('# 依赖: . "$PSScriptRoot/core.ps1"')
mod.append("")
mod.extend(get(124, 456))  # Get-StockQuote → Calc-Bollinger
with open(os.path.join(DST, "quote.ps1"), "w", encoding="utf-8") as f:
    f.write("\n".join(mod))
print(f"quote.ps1: {len(mod)} lines")

# ── sector.ps1: 板块行情+成分股 ──
mod = []
mod.append('# 依赖: . "$PSScriptRoot/core.ps1"')
mod.append("")
mod.extend(get(457, 538))  # Get-SectorData + Get-SectorConstituents
with open(os.path.join(DST, "sector.ps1"), "w", encoding="utf-8") as f:
    f.write("\n".join(mod))
print(f"sector.ps1: {len(mod)} lines")

# ── fundflow.ps1: 资金流向+PE百分位 ──
mod = []
mod.append('# 依赖: . "$PSScriptRoot/core.ps1"')
mod.append("")
mod.extend(get(539, 672))  # Get-StockFundFlow + Get-SectorFundFlow + Get-PEPercentile
with open(os.path.join(DST, "fundflow.ps1"), "w", encoding="utf-8") as f:
    f.write("\n".join(mod))
print(f"fundflow.ps1: {len(mod)} lines")

# ── external.ps1: 北向+研报+融资融券 ──
mod = []
mod.append('# 依赖: . "$PSScriptRoot/core.ps1"')
mod.append("")
mod.extend(get(673, 823))  # Get-NorthboundHold + Get-StockResearch + Get-MarginData
with open(os.path.join(DST, "external.ps1"), "w", encoding="utf-8") as f:
    f.write("\n".join(mod))
print(f"external.ps1: {len(mod)} lines")

# ── test.ps1: 数据源自检 ──
mod = []
mod.append('# 依赖: . "$PSScriptRoot/core.ps1"; . "$PSScriptRoot/quote.ps1"; . "$PSScriptRoot/sector.ps1"; . "$PSScriptRoot/fundflow.ps1"; . "$PSScriptRoot/external.ps1"')
mod.append("")
mod.extend(get(824, 913))  # Test-AllDataSources
with open(os.path.join(DST, "test.ps1"), "w", encoding="utf-8") as f:
    f.write("\n".join(mod))
print(f"test.ps1: {len(mod)} lines")

# ── 包装器 ──
wrapper_lines = [
    "# 铁律量化 - 股票数据获取模块 (入口包装)",
    "# 原文件已拆分为 modules/ 目录，本文件保留作为兼容入口",
    "# 最后更新：2026-05-24",
    "",
    '# Dot-source modules in dependency order',
    '. "$PSScriptRoot/modules/core.ps1"',
    '. "$PSScriptRoot/modules/quote.ps1"',
    '. "$PSScriptRoot/modules/sector.ps1"',
    '. "$PSScriptRoot/modules/fundflow.ps1"',
    '. "$PSScriptRoot/modules/external.ps1"',
    '. "$PSScriptRoot/modules/test.ps1"',
    "",
    '# 如果直接运行此脚本，执行数据源自检',
    'if ($MyInvocation.InvocationName -ne ".") {',
    '    Test-AllDataSources',
    '}',
]
if not os.path.exists(LEGACY):
    os.rename(SRC, LEGACY)
    with open(SRC, "w", encoding="utf-8") as f:
        f.write("\n".join(wrapper_lines))
    print(f"\nLegacy saved: {LEGACY}")
    print(f"Wrapper written: {SRC}")
else:
    print(f"\nLegacy already exists: {LEGACY}")

print("\nDone!")
