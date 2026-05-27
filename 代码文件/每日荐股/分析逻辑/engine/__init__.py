#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""铁律量化 · 评分引擎 — 全局配置 + 数据常量"""
import json, math, os, sys
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
DATA_FILE = os.path.join(ROOT, '代码文件', '数据', 'data_full.json')
OUTPUT_FILE = os.path.join(ROOT, '代码文件', '数据', 'data_scored.json')
FINAL_FILE = os.path.join(ROOT, '代码文件', '数据', 'data_final.json')
THEME_WHITELIST_FILE = os.path.join(ROOT, '每日荐股', '配置', 'industry_whitelist.json')
HISTORY_FILE = os.path.join(ROOT, '代码文件', '数据', 'score_history.jsonl')

# ============ 特殊股票豁免 ============
# 对国家战略级/高研发投入股票放宽否决阈值
SPECIAL_STOCK_EXEMPTIONS = {
    "688981": {  # 中芯国际 — 晶圆代工龙头，国家战略
        "exempt_abs_pe": True,      # 豁免绝对PE否决
        "exempt_cond_pe": True,     # 豁免条件PE否决
        "exempt_ma_death": True,    # 豁免MA死叉否决
    },
    "688041": {  # 海光信息 — CPU/DCU国产替代
        "exempt_cond_pe": True,     # 豁免条件PE否决（C2阈值80太高）
    },
    "688256": {  # 寒武纪 — AI芯片独角兽
        "exempt_abs_pe": True,      # 豁免绝对PE否决
        "exempt_cond_pe": True,     # 豁免条件PE否决
    },
    "688012": {  # 中微公司 — 半导体刻蚀/薄膜设备
        "abs_pe_threshold": 200,    # 绝对PE阈值提高至200
        "cond_pe_threshold": 150,   # 条件PE阈值提高至150
    },
    "603986": {  # 兆易创新 — NOR Flash/MCU
        "abs_pe_threshold": 150,    # 绝对PE阈值提高至150
        "cond_pe_threshold": 150,   # 条件PE阈值提高至150
    },
    "688008": {  # 澜起科技 — 内存接口芯片
        "cond_pe_threshold": 150,   # 条件PE阈值提高至150
    },
    "002371": {  # 北方华创 — 半导体设备龙头
        "cond_pe_threshold": 120,   # 条件PE阈值提高至120
    },
    "300661": {  # 圣邦股份 — 模拟芯片
        "cond_pe_threshold": 150,   # 条件PE阈值提高至150
    },
    "300604": {  # 长川科技 — 半导体测试设备
        "cond_pe_threshold": 120,   # 条件PE阈值提高至120
    },
    "688072": {  # 拓荆科技 — CVD薄膜沉积设备
        "cond_pe_threshold": 150,   # 条件PE阈值提高至150
    },
    "688120": {  # 华海清科 — CMP抛光设备
        "cond_pe_threshold": 150,   # 条件PE阈值提高至150
    },
    "300782": {  # 卓胜微 — 射频前端芯片龙头
        "exempt_abs_eps": True,     # 豁免EPS<=0否决（季度性波动）
    },
    "600703": {  # 三安光电 — 化合物半导体
        "exempt_abs_eps": True,     # 豁免EPS<=0否决
    },
    "688521": {  # 芯原股份 — 芯片设计服务
        "exempt_abs_eps": True,     # 豁免EPS<=0否决（高研发投入）
    },
    "688561": {  # 奇安信 — 网络安全龙头
        "exempt_abs_eps": True,     # 豁免EPS<=0否决
    },
    "300418": {  # 昆仑万维 — AI应用
        "exempt_abs_eps": True,     # 豁免EPS<=0否决
    },
}

# ============ 东方财富细分行业 → 申万大类行业 映射 ============
EASTMONEY_TO_BROAD_INDUSTRY = {
    "工业金属": "有色金属", "铜": "有色金属", "铝": "有色金属",
    "铅锌": "有色金属", "钨": "有色金属", "钴": "有色金属",
    "镍": "有色金属", "锡": "有色金属",
    "磁性材料": "有色金属", "金属新材料": "有色金属", "其他金属新材料": "有色金属",
    "印制电路板": "电子", "元件": "电子", "被动元件": "电子",
    "光学元件": "电子", "电子化学品Ⅱ": "电子", "电子化学品Ⅲ": "电子",
    "消费电子": "电子", "消费电子零部件及组装": "电子",
    "氟化工": "基础化工", "膜材料": "基础化工",
    "塑料": "基础化工", "改性塑料": "基础化工", "其他化学纤维": "基础化工",
    "磨具磨料": "机械设备", "激光设备": "机械设备",
    "锂电专用设备": "电力设备", "燃料电池": "电力设备",
    "玻纤制造": "建筑材料", "玻璃玻纤": "建筑材料",
    "非金属材料Ⅱ": "建筑材料", "非金属材料Ⅲ": "建筑材料",
    "通信设备": "通信", "通信网络设备及器件": "通信",
}

# 反向映射: 大类行业 → 其包含的东方财富细分行业列表
BROAD_TO_EASTMONEY = {}
for em_name, broad_name in EASTMONEY_TO_BROAD_INDUSTRY.items():
    BROAD_TO_EASTMONEY.setdefault(broad_name, []).append(em_name)

# ============ v2.6 题材三分类系统 ============
# 白皮书 §十七-A: 题材三分类 — 强成长(PEG+PS) / 周期成长(PB+价格趋势) / 稳定价值(PE合理区间)

# 行业→题材分类映射（第一层：基于申万大类行业）
# 个股可通过 industry_whitelist.json 获得额外标签（多标签叠加）
THEME_CLASSIFICATION = {
    # === 强成长：远期空间定价，PE参考价值低，用PEG+PS ===
    "电子": "强成长",
    "计算机": "强成长",
    "通信": "强成长",
    "传媒": "强成长",
    "国防军工": "强成长",
    # === 周期成长：盈利周期波动，PB锚底+趋势判断 ===
    "有色金属": "周期成长",
    "基础化工": "周期成长",
    "钢铁": "周期成长",
    "煤炭": "周期成长",
    "石油石化": "周期成长",
    "建筑材料": "周期成长",
    "电力设备": "周期成长",
    "机械设备": "周期成长",
    "汽车": "周期成长",
    # === 稳定价值：PE在合理区间才有参考意义 ===
    "食品饮料": "稳定价值",
    "银行": "稳定价值",
    "非银金融": "稳定价值",
    "公用事业": "稳定价值",
    "交通运输": "稳定价值",
    "建筑装饰": "稳定价值",
    "房地产": "稳定价值",
    "医药生物": "稳定价值",
    "家用电器": "稳定价值",
    "纺织服饰": "稳定价值",
    "商贸零售": "稳定价值",
    "社会服务": "稳定价值",
    "环保": "稳定价值",
    "农林牧渔": "稳定价值",
    "轻工制造": "稳定价值",
}

# v2.7 TECH-05: 大宗商品→行业映射 (周期产品价格趋势)
COMMODITY_TO_SECTOR = {
    "CU": ["有色金属", "铜", "工业金属"],        # 铜
    "AL": ["有色金属", "铝"],                     # 铝
    "ZN": ["有色金属", "锌", "铅锌"],             # 锌
    "AU": ["有色金属", "黄金", "贵金属"],         # 黄金
    "AG": ["有色金属", "白银"],                   # 白银
    "SC": ["石油石化", "化工"],                   # 原油
    "RB": ["钢铁", "建筑材料"],                   # 螺纹钢
    "LC": ["有色金属", "电力设备", "新能源"],     # 碳酸锂
}
# 预处理: symbol→[(sector_keyword, trend_10d, trend_20d, change_pct)]
_commodity_sector_map = None  # lazy init in _score_cyclical_growth


# 稳定价值行业PE合理区间 (白皮书 §十七-D)
STABLE_VALUE_PE_RANGE = {
    "食品饮料": (20, 45), "银行": (4, 10), "非银金融": (8, 20),
    "公用事业": (10, 25), "交通运输": (10, 22), "建筑装饰": (6, 18),
    "房地产": (5, 15), "医药生物": (22, 50), "家用电器": (10, 22),
    "纺织服饰": (12, 28), "商贸零售": (12, 30), "社会服务": (15, 40),
    "环保": (10, 28), "农林牧渔": (12, 35), "轻工制造": (12, 30),
}

# ============ 否决规则 ============
PE_ABSOLUTE_THRESHOLD = {
    # 科技/成长行业 — 高PE是常态，大幅提高阈值让综合评分说话
    "电子": 300, "计算机": 300, "通信": 250,
    "汽车": 150, "电力设备": 150, "机械设备": 150, "传媒": 150,
    # 消费/医药 — 适度放宽
    "食品饮料": 60, "医药生物": 80,
    # 金融 — 低PE行业，维持严格
    "银行": 15, "非银金融": 20,
}
PE_COND_THRESHOLD = 80  # 条件否决 PE>80
PE_COND_EXEMPT_SCORE = 85
C3_EXEMPT_SCORE = 70   # MA5<MA10 豁免线（短期回踩，v2.3放宽）
C5_EXEMPT_SCORE = 75   # MA10≤MA20 豁免线（高分豁免）

# ============ P1a 行业评分锚定参照 (2026-05-26) ============
# 申万一级行业基准分 (0-10)
# 来源：腰子-知识库/05-板块轮动与生命周期.md §十
INDUSTRY_BENCHMARK = {
    "食品饮料": 7.0, "电子": 6.5, "医药生物": 6.0,
    "电力设备": 6.0, "计算机": 5.5, "家用电器": 5.5,
    "汽车": 5.5, "通信": 5.5, "国防军工": 5.5,
    "有色金属": 5.0, "机械设备": 5.0, "基础化工": 5.0,
    "非银金融": 5.0, "美容护理": 5.0,
    "交通运输": 4.5, "公用事业": 4.5, "农林牧渔": 4.5,
    "轻工制造": 4.5, "纺织服饰": 4.5, "建筑材料": 4.5,
    "建筑装饰": 4.5, "传媒": 4.5,
    "钢铁": 4.0, "煤炭": 4.0, "石油石化": 4.0,
    "银行": 4.0, "房地产": 4.0, "商贸零售": 4.0,
    "社会服务": 4.0, "环保": 4.0,
    "综合": 3.5,
}

# 数据源标记映射表（红线规则 v1.4 §1.2）
FIELD_SOURCE_MAP = {
    "Price": "[1]", "ChangePct": "[1]", "Volume": "[2]",
    "TurnoverRate": "[1]", "PE": "[3]", "MktCap": "[1]",
    "EPS": "[3]", "MA5": "[5]", "MA10": "[5]", "MA20": "[5]",
    "RSI": "[5]", "VolRatio": "[5]", "VolumePercentile": "[5]",
    "FundMainNet": "[9]", "SectorPhase": "[7]", "SectorTrend": "[7]",
    # v2.6: 新增财务字段(三路径PE评分)
    "BPS": "[3]", "RevenueTTM": "[3]", "RevenueYOY": "[3]",
    "NetProfitYOY": "[3]", "GrossMargin": "[3]",
    # v2.8: 北向资金 + 融资融券 + 一致预期
    "NorthboundSharesRatio": "[8]", "NorthboundFreeRatio": "[8]",
    "NorthboundHoldMktCap": "[8]",
    "MarginRZYE": "[12]", "MarginRZJME": "[12]",
    "MarginRZYE_5dChange": "[12]",
    "ConsensusGrowth": "[11]", "ResearchReportCount": "[11]",
    "PE_TTM": "[5]", "PE_Source": "[5]",
    "PEG": "[5]", "PB": "[5]", "PS": "[5]",
    "CAR5": "[5]", "EPS_Growth": "[5]", "GrowthSource": "[5]",
    "ADX14": "[5]", "BB_Upper": "[5]", "BB_Lower": "[5]", "OBV": "[5]",
    "PhaseMultiplier": "[5]", "ThemePath": "[5]", "VetoStatus": "[5]",
    "DividendYield": "[3]",
}


def load_history(date_range=None):
    """统一加载 score_history.jsonl，返回 list[dict]
    date_range: (start_date, end_date) 可选，格式 "YYYY-MM-DD"
    """
    records = []
    if not os.path.exists(HISTORY_FILE):
        return records
    with open(HISTORY_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                if date_range:
                    d = rec.get("date", "")
                    if d < date_range[0] or d > date_range[1]:
                        continue
                records.append(rec)
            except json.JSONDecodeError:
                pass
    records.sort(key=lambda x: (x.get("date", ""), x.get("code", "")))
    return records