#!/usr/bin/env python3
"""精确拆分 v2 — 精确行号 + 交叉模块导入"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "scoring_engine_v2_legacy.py")
DST = os.path.join(HERE, "engine")
os.makedirs(DST, exist_ok=True)

with open(SRC, "r", encoding="utf-8-sig") as f:
    all_lines = f.read().split("\n")

def get(start, end):
    block = list(all_lines[start:end])
    while block and not block[-1].strip():
        block.pop()
    return block

def make_header(desc):
    return [
        "#!/usr/bin/env python3",
        "# -*- coding: utf-8 -*-",
        f'"""铁律量化 · 评分引擎 — {desc}"""',
        "import json, math, os, sys",
        "from datetime import date, datetime, timedelta",
        "from collections import Counter, defaultdict",
        "",
        "from . import (",
        "    ROOT, DATA_FILE, OUTPUT_FILE, THEME_WHITELIST_FILE, HISTORY_FILE,",
        "    SPECIAL_STOCK_EXEMPTIONS, EASTMONEY_TO_BROAD_INDUSTRY, BROAD_TO_EASTMONEY,",
        "    THEME_CLASSIFICATION, COMMODITY_TO_SECTOR, STABLE_VALUE_PE_RANGE,",
        "    PE_ABSOLUTE_THRESHOLD, PE_COND_THRESHOLD,",
        "    PE_COND_EXEMPT_SCORE, C3_EXEMPT_SCORE, C5_EXEMPT_SCORE, FIELD_SOURCE_MAP,",
        ")",
        "",
    ]

# ── __init__.py ──
init = [
    "#!/usr/bin/env python3",
    "# -*- coding: utf-8 -*-",
    '"""铁律量化 · 评分引擎 — 全局配置 + 数据常量"""',
    "import json, math, os, sys",
    "from datetime import date",
    "",
    "ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))",
    "DATA_FILE = os.path.join(ROOT, '代码文件', '数据', 'data_full.json')",
    "OUTPUT_FILE = os.path.join(ROOT, '代码文件', '数据', 'data_scored.json')",
    "THEME_WHITELIST_FILE = os.path.join(ROOT, '每日荐股', '配置', 'industry_whitelist.json')",
    "HISTORY_FILE = os.path.join(ROOT, '代码文件', '数据', 'score_history.jsonl')",
    "",
]
init.extend(get(28, 109))
init.append("")
init.extend(get(180, 245))  # THEME_CLASSIFICATION + COMMODITY_TO_SECTOR + _commodity_sector_map + STABLE_VALUE_PE_RANGE
init.append("")
init.extend(get(707, 740))
with open(os.path.join(DST, "__init__.py"), "w", encoding="utf-8-sig", newline="\n") as f:
    f.write("\n".join(init))
print(f"__init__.py: {len(init)} lines")

# ── technical.py ──
mod = make_header("技术指标计算 (MA/RSI/MACD/ATR/EMA)")
mod.extend(get(109, 180))
with open(os.path.join(DST, "technical.py"), "w", encoding="utf-8-sig", newline="\n") as f:
    f.write("\n".join(mod))
print(f"technical.py: {len(mod)} lines")

# ── theme.py ──
mod = make_header("题材三分类系统 + PE差异化估值")
mod.append("_commodity_sector_map = None  # lazy init in _score_cyclical_growth")
mod.append("")
mod.extend(get(245, 707))
with open(os.path.join(DST, "theme.py"), "w", encoding="utf-8-sig", newline="\n") as f:
    f.write("\n".join(mod))
print(f"theme.py: {len(mod)} lines")

# ── sector.py ──
mod = make_header("板块相位 + 动量 + 趋势")
mod.extend(get(854, 1246))
with open(os.path.join(DST, "sector.py"), "w", encoding="utf-8-sig", newline="\n") as f:
    f.write("\n".join(mod))
print(f"sector.py: {len(mod)} lines")

# ── veto.py (L2) ──
mod = make_header("否决体系 + 市场状态检测 [L2]")
mod.append("# L2 风控模块 — 每条规则引用红线条款编号，变更须经 流金 复核")
mod.append("# 交叉导入:")
mod.append("from .theme import classify_theme, check_theme_purity, load_industry_whitelist")
mod.append("from .technical import calc_ma")
mod.append("from .sector import should_exempt_by_sector")
mod.append("")
mod.extend(get(740, 854))
mod.append("")
mod.extend(get(1734, 1864))
with open(os.path.join(DST, "veto.py"), "w", encoding="utf-8-sig", newline="\n") as f:
    f.write("\n".join(mod))
print(f"veto.py: {len(mod)} lines")

# ── subscores.py ──
mod = make_header("技术面子项评分")
mod.extend(get(1584, 1734))
with open(os.path.join(DST, "subscores.py"), "w", encoding="utf-8-sig", newline="\n") as f:
    f.write("\n".join(mod))
print(f"subscores.py: {len(mod)} lines")

# ── scores.py ──
mod = make_header("四维评分计算 + 相位折扣")
mod.append("# 交叉导入:")
mod.append("from .theme import score_pe_by_theme")
mod.append("from .technical import calc_ma, calc_rsi, calc_macd, calc_atr")
mod.append("from .subscores import (_score_ma_system, _score_ma_converge, _score_volume_price,")
mod.append("    _score_bottom_support, _score_rsi, _score_macd,")
mod.append("    _score_breakout_confirmation, _score_trend_momentum)")
mod.append("")
mod.extend(get(1246, 1585))
with open(os.path.join(DST, "scores.py"), "w", encoding="utf-8-sig", newline="\n") as f:
    f.write("\n".join(mod))
# 边界修复: phase_mult 在数据不足分支中未初始化 (bug in legacy source)
scores_path = os.path.join(DST, "scores.py")
with open(scores_path, "r", encoding="utf-8-sig", newline="\n") as f:
    sc = f.read()
sc = sc.replace('tech_details = {}\n        s["VolumePercentile"]',
                 'tech_details = {}\n        phase_mult = 1.0\n        s["VolumePercentile"]')
with open(scores_path, "w", encoding="utf-8-sig", newline="\n") as f:
    f.write(sc)
print(f"scores.py: {len(mod)} lines")

# ── engine.py ──
mod = make_header("主入口 + 编排 + 历史记录")
mod.append("# 交叉导入:")
mod.append("from .veto import _get_v5_threshold, check_absolute_vetoes, check_conditional_vetoes, detect_market_state")
mod.append("from .scores import compute_scores")
mod.append("from .sector import compute_sector_phases, compute_sector_trend")
mod.append("")
mod.extend(get(1864, 2360))
with open(os.path.join(DST, "engine.py"), "w", encoding="utf-8-sig", newline="\n") as f:
    f.write("\n".join(mod))
print(f"engine.py: {len(mod)} lines")

print("\nDone!")
