#!/usr/bin/env python3
"""精确拆分 stock_data_fetcher.psm1 (生产模块, 1087行) → modules/ 目录"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "stock_data_fetcher_legacy.psm1")
DST = os.path.join(HERE, "modules")
os.makedirs(DST, exist_ok=True)

with open(SRC, "r", encoding="utf-8-sig") as f:
    all_lines = f.read().split("\n")

def get(start, end):
    block = list(all_lines[start:end])
    while block and not block[-1].strip():
        block.pop()
    return block

# ── core.psm1: 基础设施（配置+限速器+缓存+同花顺降级） ──
# Lines 0-167: header + throttle + cache + Invoke-ThsFallback
mod = get(0, 167)
with open(os.path.join(DST, "core.ps1"), "w", encoding="utf-8-sig", newline="\n") as f:
    f.write("\n".join(mod))
print(f"core.ps1: {len(mod)} lines")

# ── quote.psm1: 行情+K线 ──
# Lines 168-393: Get-StockQuote + Get-StockQuoteBatch + Get-StockKLine
mod = []
mod.append('# 依赖: dot-source "$PSScriptRoot/core.ps1"')
mod.append("")
mod.extend(get(167, 392))
with open(os.path.join(DST, "quote.ps1"), "w", encoding="utf-8-sig", newline="\n") as f:
    f.write("\n".join(mod))
print(f"quote.ps1: {len(mod)} lines")

# ── financial.psm1: 财务数据 ──
# Lines 393-439: Get-StockFinancial
mod = []
mod.append('# 依赖: dot-source "$PSScriptRoot/core.ps1"')
mod.append("")
mod.extend(get(392, 438))
with open(os.path.join(DST, "financial.ps1"), "w", encoding="utf-8-sig", newline="\n") as f:
    f.write("\n".join(mod))
print(f"financial.ps1: {len(mod)} lines")

# ── technical.psm1: 技术指标 ──
# Lines 439-604: Calc-MovingAverage → Calc-ATR
mod = []
mod.append('# 独立模块 — 纯计算函数，无外部依赖')
mod.append("")
mod.extend(get(438, 603))
with open(os.path.join(DST, "technical.ps1"), "w", encoding="utf-8-sig", newline="\n") as f:
    f.write("\n".join(mod))
print(f"technical.ps1: {len(mod)} lines")

# ── sector.psm1: 板块数据 ──
# Lines 604-695: Get-SectorData + Get-SectorConstituents
mod = []
mod.append('# 依赖: dot-source "$PSScriptRoot/core.ps1"')
mod.append("")
mod.extend(get(603, 694))
with open(os.path.join(DST, "sector.ps1"), "w", encoding="utf-8-sig", newline="\n") as f:
    f.write("\n".join(mod))
print(f"sector.ps1: {len(mod)} lines")

# ── fundflow.psm1: 资金流向+PE百分位 ──
# Lines 695-837: Get-StockFundFlow + Get-SectorFundFlow + Get-PEPercentile
mod = []
mod.append('# 依赖: dot-source "$PSScriptRoot/core.ps1"')
mod.append("")
mod.extend(get(694, 836))
with open(os.path.join(DST, "fundflow.ps1"), "w", encoding="utf-8-sig", newline="\n") as f:
    f.write("\n".join(mod))
print(f"fundflow.ps1: {len(mod)} lines")

# ── external.psm1: 北向+研报+融资融券 ──
# Lines 837-988: Get-NorthboundHold + Get-StockResearch + Get-MarginData
mod = []
mod.append('# 依赖: dot-source "$PSScriptRoot/core.ps1"')
mod.append("")
mod.extend(get(836, 987))
with open(os.path.join(DST, "external.ps1"), "w", encoding="utf-8-sig", newline="\n") as f:
    f.write("\n".join(mod))
print(f"external.ps1: {len(mod)} lines")

# ── test.psm1: 数据源自检 ──
# Lines 988-1087: Test-AllDataSources
mod = []
mod.append('# 依赖: dot-source all sibling modules')
mod.append("")
mod.extend(get(987, 1088))
with open(os.path.join(DST, "test.ps1"), "w", encoding="utf-8-sig", newline="\n") as f:
    f.write("\n".join(mod))
# Fix PDF helper path: $PSScriptRoot changed from scripts/ to scripts/modules/
test_path = os.path.join(DST, "test.ps1")
with open(test_path, "r", encoding="utf-8-sig", newline="\n") as f:
    tc = f.read()
tc = tc.replace('"..\\..\\监督机制\\ConvertTo-Pdf.ps1"', '"..\\..\\..\\监督机制\\ConvertTo-Pdf.ps1"')
with open(test_path, "w", encoding="utf-8-sig", newline="\n") as f:
    f.write(tc)
print(f"test.ps1: {len(mod)} lines")

# ── 模块包装器 (写入 stock_data_fetcher.psm1) ──
WRAPPER_PSM1 = os.path.join(HERE, "stock_data_fetcher.psm1")
wrapper_lines = [
    "# 铁律量化 - 股票数据获取模块",
    "# 数据源：腾讯行情[1], 新浪K线[2], 东方财富财务[3][6][7][9][10]",
    "# 原文件已拆分为 modules/ 目录，本文件保留作为兼容入口",
    "# 最后更新：2026-05-24",
    "",
    '# Dot-source sub-modules in dependency order (module scope)',
    '. "$PSScriptRoot/modules/core.ps1"',
    '. "$PSScriptRoot/modules/quote.ps1"',
    '. "$PSScriptRoot/modules/financial.ps1"',
    '. "$PSScriptRoot/modules/technical.ps1"',
    '. "$PSScriptRoot/modules/sector.ps1"',
    '. "$PSScriptRoot/modules/fundflow.ps1"',
    '. "$PSScriptRoot/modules/external.ps1"',
    '. "$PSScriptRoot/modules/test.ps1"',
    "",
    '# Export all functions for module consumers',
    'Export-ModuleMember -Function *',
]
with open(WRAPPER_PSM1, "w", encoding="utf-8-sig", newline="\n") as f:
    f.write("\n".join(wrapper_lines))
print(f"Wrapper written: {WRAPPER_PSM1}")

print("\nDone!")
