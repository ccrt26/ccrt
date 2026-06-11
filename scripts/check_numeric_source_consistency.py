#!/usr/bin/env python3
"""
P0-B: 数值来源一致性闸门 — 检查日报关键数字与权威数据源的一致性。

检查维度:
  1. 行情: close, change_pct, volume
  2. 四档资金: super_large_net, large_net, medium_net, small_net, main_force_net
  3. 融资日期/余额
  4. 板块相位

用法:
  python3 scripts/check_numeric_source_consistency.py --code 600114 --name 东睦股份 --date 20260602
  python3 scripts/check_numeric_source_consistency.py --all --date 20260602
  python3 scripts/check_numeric_source_consistency.py --code 600114 --name 东睦股份 --date 20260602 --json

退出码:
  0 = PASS (所有检查通过)
  1 = 脚本异常
  2 = 任一 BLOCK
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = PROJECT_ROOT / "重点股票" / "股票报告"
KLINE_DIR = PROJECT_ROOT / "代码文件" / "数据" / "kline_cache"
FUND_FLOW_DIR = PROJECT_ROOT / "代码文件" / "数据" / "fund_flow_cache"
MARGIN_DIR = PROJECT_ROOT / "代码文件" / "数据" / "tushare" / "margin_detail"
DATA_SCORED_PATH = PROJECT_ROOT / "代码文件" / "数据" / "data_scored.json"
PIGEON_CONFIG = PROJECT_ROOT / "代码文件" / "信鸽信息采集" / "pigeon_config.json"

# ============================================================
# 辅助函数
# ============================================================

def load_json(path):
    """加载 JSON 文件，自动处理 BOM"""
    with open(path, "r", encoding="utf-8-sig") as f:
        return json.load(f)


def load_text(path):
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="ignore")


def parse_date(date_str: str) -> date:
    """解析日期，支持 20260602 和 2026-06-02"""
    d = date_str.replace("-", "")
    if len(d) != 8:
        raise ValueError(f"日期格式非法: {date_str}")
    return datetime.strptime(d, "%Y%m%d").date()


def norm_date(date_str: str, out_format="MMDDYYYY") -> str:
    """标准化日期格式。输入支持 20260602 或 2026-06-02"""
    d = date_str.replace("-", "")
    if out_format == "YYYYMMDD":
        return d
    elif out_format == "YYYY-MM-DD":
        return f"{d[:4]}-{d[4:6]}-{d[6:8]}"
    return d


def normalize_amount(amount_str: str) -> float:
    """规范化金额字符串为数字（万元）。
    支持格式: "+13649万" "-2905万" "1.36亿" "10743.23" 等
    """
    if amount_str is None:
        return None
    if isinstance(amount_str, (int, float)):
        return float(amount_str)

    s = str(amount_str).strip().replace(",", "").replace("+", "")

    if "亿" in s:
        # "1.36亿" -> 13600万
        try:
            num = float(s.replace("亿", ""))
            return round(num * 10000, 2)
        except ValueError:
            return None
    elif "万" in s:
        # "+13649万" -> 13649
        try:
            return float(s.replace("万", ""))
        except ValueError:
            return None
    else:
        try:
            return float(s)
        except ValueError:
            return None


# ============================================================
# 权威源加载
# ============================================================

def load_kline(code: str, trade_date: date) -> tuple:
    """加载 kline_cache，返回 (row_dict, file_path) 或 (None, path)"""
    path = KLINE_DIR / f"{code}.json"
    if not path.exists():
        return None, str(path)
    try:
        rows = load_json(path)
    except Exception:
        return None, str(path)

    date_str = trade_date.strftime("%Y-%m-%d")
    for row in rows:
        if row.get("date") == date_str:
            return row, str(path)
    return None, str(path)


def load_fund_flow(code: str, trade_date: date) -> tuple:
    """加载 fund_flow_cache，兜底 data_full.json.FundFlows。
    返回 (row_dict, file_path) 或 (None, path)"""
    # 1. Try fund_flow_cache
    path = FUND_FLOW_DIR / f"{code}.json"
    date_str = trade_date.strftime("%Y%m%d")
    if path.exists():
        try:
            rows = load_json(path)
            for row in rows:
                if str(row.get("date", "")) == date_str:
                    return row, str(path)
        except Exception:
            pass

    # 2. Fallback to data_full.json.FundFlows
    df_path = PROJECT_ROOT / "代码文件" / "数据" / "data_full.json"
    if df_path.exists():
        try:
            dfull = load_json(df_path)
            flows = dfull.get("FundFlows", {}).get(code, [])
            if flows:
                for row in flows:
                    d = str(row.get("trade_date") or row.get("date", "")).replace("-", "")
                    if d == date_str:
                        def to_f(v): return round(float(v or 0), 2)
                        mapped = {
                            "date": date_str,
                            "super_large_net": round(to_f(row.get("buy_elg_amount", 0)) - to_f(row.get("sell_elg_amount", 0)), 2),
                            "large_net": round(to_f(row.get("buy_lg_amount", 0)) - to_f(row.get("sell_lg_amount", 0)), 2),
                            "medium_net": round(to_f(row.get("buy_md_amount", 0)) - to_f(row.get("sell_md_amount", 0)), 2),
                            "small_net": round(to_f(row.get("buy_sm_amount", 0)) - to_f(row.get("sell_sm_amount", 0)), 2),
                            "main_force_net": round(to_f(row.get("net_mf_amount", 0)), 2),
                            "_source": str(df_path),
                        }
                        return mapped, str(df_path)
        except Exception:
            pass

    return None, str(path)


def load_margin_latest(code: str) -> tuple:
    """加载 margin_detail，返回 (latest_row, file_path) 或 (None, path)"""
    path = MARGIN_DIR / f"{code}.json"
    if not path.exists():
        return None, str(path)
    try:
        rows = load_json(path)
    except Exception:
        return None, str(path)
    if not rows:
        return None, str(path)
    return rows[0], str(path)


def load_sector_phase(code: str) -> tuple:
    """从 data_scored.json 加载板块相位。
    返回 ({'phase':..., 'industry':...}, file_path) 或 (None, path)"""
    if not DATA_SCORED_PATH.exists():
        return None, str(DATA_SCORED_PATH)
    try:
        d = load_json(DATA_SCORED_PATH)
    except Exception:
        return None, str(DATA_SCORED_PATH)

    code_str = str(code)
    for bucket in ["Recommendations", "AllStocks", "VetoedStocks"]:
        items = d.get(bucket, [])
        if not isinstance(items, list):
            continue
        for item in items:
            c = str(item.get("Code", item.get("code", "")))
            if c == code_str:
                phase = item.get("SectorPhase", item.get("sector_phase", ""))
                industry = item.get("Industry", item.get("industry", ""))
                return {"phase": phase, "industry": industry}, str(DATA_SCORED_PATH)
    return None, str(DATA_SCORED_PATH)


# ============================================================
# 股票池
# ============================================================

def get_stock_pool() -> list:
    """从 pigeon_config.json 获取股票池。失败返回空列表。"""
    if not PIGEON_CONFIG.exists():
        return []
    try:
        cfg = load_json(PIGEON_CONFIG)
    except Exception:
        return []
    stocks = cfg.get("target_stocks", []) or cfg.get("stocks", [])
    result = []
    for s in stocks:
        code = str(s.get("code") or s.get("Code", ""))
        name = s.get("name") or s.get("Name", "")
        if code and name:
            result.append((code, name))
    return result


def get_stock_pool_from_reports() -> list:
    """从 重点股票/股票报告/ 子目录解析"""
    stocks = []
    if not REPORT_DIR.exists():
        return stocks
    for subdir in sorted(REPORT_DIR.iterdir()):
        if not subdir.is_dir():
            continue
        m = re.match(r'(.+)\((\d{6})\)', subdir.name)
        if m:
            stocks.append((m.group(2), m.group(1)))
    return stocks


# ============================================================
# 报告加载
# ============================================================

def find_report_file(code: str, name: str, date_compact: str, ext: str) -> Path:
    report_subdir = REPORT_DIR / f"{name}({code})"
    return report_subdir / f"{name}({code})日报_{date_compact}{ext}"


def extract_md_text_date(date_str: str) -> str:
    """将数字日期转为 MD 中常见的文字如 '6月2日'"""
    d = date_str.replace("-", "")
    month = int(d[4:6])
    day = int(d[6:8])
    return f"{month}月{day}日"


# ============================================================
# MD 文本解析
# ============================================================

def extract_md_close(md_text: str, date_compact: str) -> float:
    """从MD行情表中提取当日收盘价。
    支持 ** 粗体标记环绕：
      | 2026-06-02 | **35.96** | **38.79** | **38.79** | **35.59** | **36.2万手** |
    close 是日期后的第2个数值列（第1个是开盘）。
    """
    import re
    # 先剥离 ** 再解析（大幅简化表格匹配）
    clean = md_text.replace("**", "")

    date_dashed = f"{date_compact[:4]}-{date_compact[4:6]}-{date_compact[6:8]}"
    date_cn = extract_md_text_date(date_compact)

    for dtext in [date_dashed, date_cn]:
        # 6列表格: | 日期 | 开盘 | 收盘 | 最高 | 最低 | 成交量 |
        pat = rf'\|?\s*{re.escape(dtext)}\s*\|\s*([\d.]+)\s*\|\s*([\d.]+)\s*\|'
        m = re.search(pat, clean)
        if m:
            return float(m.group(2))  # close

    return None


def extract_md_change_pct(md_text: str, date_compact: str) -> float:
    """从MD文本中提取涨跌幅百分比，自动检测正负方向。

    支持格式:
      "6月2日下跌2.56%" → -2.56
      "6月2日上涨10.0%" → 10.0
      "当日下跌3.71%"  → -3.71
    """
    date_text = extract_md_text_date(date_compact)

    # Strategy 1: match direction keyword adjacent to the number
    # e.g. "6月2日下跌2.6%", "6月2日上涨10.0%"
    pat_adjacent = rf'{re.escape(date_text)}.*?(下跌|上涨|跌|涨)[约]?\s*([\d.]+)%'
    m = re.search(pat_adjacent, md_text)
    if m:
        val = float(m.group(2))
        if m.group(1) in ("下跌", "跌"):
            val = -val
        return val

    # Strategy 2: table format with change_pct column
    pat_table = rf'{re.escape(date_text)}\s*\|[^|]+\|[^|]+\|[^|]+\|[^|]+\|[^|]*\|\s*([\d.]+)%'
    m = re.search(pat_table, md_text)
    if m:
        val = float(m.group(1))
        # Table values might be negative already, just return as-is
        return val

    # Strategy 3: generic "当日下跌X%" or "当日上涨X%"
    pat_generic = r'(?:当日|今日|今天)\s*(下跌|上涨|跌|涨)\s*([\d.]+)%'
    m = re.search(pat_generic, md_text)
    if m:
        val = float(m.group(2))
        if m.group(1) in ("下跌", "跌"):
            val = -val
        return val

    # Strategy 4: any % mention near the date text (last resort)
    pat_fallback = rf'{re.escape(date_text)}.*?([\d.]+)%'
    m = re.search(pat_fallback, md_text)
    if m:
        val = float(m.group(1))
        # Check context for negative indicators
        ctx_start = max(0, m.start() - 30)
        ctx = md_text[ctx_start:m.end()]
        if '下跌' in ctx or '跌' in ctx:
            val = -val
        return val

    return None


def extract_md_volume(md_text: str, date_compact: str) -> float:
    """从MD行情表提取当日成交量（万手）。
    只从目标日期行情表行提取。
    表格格式: | 2026-06-04 | ... | 26.4万手 |
    优先级: YYYY-MM-DD 行 > M月D日 行
    禁止从正文叙述fallback提取。"""
    date_dashed = f"{date_compact[:4]}-{date_compact[4:6]}-{date_compact[6:8]}"

    # 1. 精确匹配 YYYY-MM-DD 行情表行
    pat = rf'\|?\s*{re.escape(date_dashed)}\s*\|[^|]*\|[^|]*\|[^|]*\|[^|]*\|\s*([\d.]+)万手'
    m = re.search(pat, md_text)
    if m:
        return float(m.group(1))

    # 2. 兼容 M月D日 格式行
    date_text = extract_md_text_date(date_compact)
    pat2 = rf'{re.escape(date_text)}\s*\|[^|]*\|[^|]*\|[^|]*\|[^|]*\|\s*([\d.]+)万手'
    m = re.search(pat2, md_text)
    if m:
        return float(m.group(1))

    return None


def extract_md_fund_flow(md_text: str) -> dict:
    """从MD资金表中提取各资金类型数值（万元）。
    支持 ** 粗体标记：| **超大单** | **+13649万** | — |
    也支持无粗体：| 超大单 | +13649万 | — |
    """
    result = {}
    # 先剥离 **
    clean = md_text.replace("**", "")
    lines = clean.split('\n')
    in_table = False
    valid_names = ('超大单', '大单', '中单', '小单', '主力合计', '中单/中小单')
    name_map = {
        '超大单': 'super_large_net',
        '大单': 'large_net',
        '中单': 'medium_net',
        '中单/中小单': 'medium_net',
        '小单': 'small_net',
        '主力合计': 'main_force_net',
    }

    for line in lines:
        if '资金类型' in line and '净额' in line:
            in_table = True
            continue
        if in_table:
            if not line.strip().startswith('|') or '---' in line:
                continue
            parts = [p.strip() for p in line.split('|') if p.strip()]
            if len(parts) >= 2 and parts[0] in valid_names:
                amount = normalize_amount(parts[1])
                if amount is not None:
                    key = name_map.get(parts[0])
                    if key:
                        result[key] = amount

    return result


def extract_md_margin_date(md_text: str) -> str:
    """从MD中提取融资最新日期。格式: "最新日期20260527" 或 "最新日期:20260527" """
    m = re.search(r'最新日期[：:]*(\d{8})', md_text)
    if m:
        return m.group(1)
    m = re.search(r'融资.*?(\d{8})', md_text)
    if m:
        return m.group(1)
    return None


def extract_md_sector_phase(md_text: str) -> str:
    """从MD中提取板块相位值（纯文本，去粗体和后缀）。
    支持格式:
      - 当前相位：**衰退期**（data_scored最新数据）
      - 机械设备板块，当前相位：**衰退期**
      - 板块相位：主升期
      - 相位: 主升调整
    返回值仅含相位文本如 "衰退期" "主升期" 等。
    """
    # 先剥离 ** 再匹配
    clean = md_text.replace("**", "")
    phase_kw = r'(见底期|启动期|主升期|高潮期|退潮期|主升调整|衰退期|潜伏期|震荡期|筑底期|主跌期|反弹期|调整期)'
    patterns = [
        rf'相位[：:]\s*{phase_kw}',
        rf'板块相位[：:]*\s*{phase_kw}',
        rf'当前相位[：:]\s*{phase_kw}',
        rf'处于[：:]*\s*{phase_kw}',
    ]
    for pat in patterns:
        m = re.search(pat, clean)
        if m:
            return m.group(1)
    return None


# ============================================================
# 单一字段检查函数
# ============================================================

def make_check(field: str, source_path: str, expected, sidecar_val, md_val,
               result: str, issue: str) -> dict:
    return {
        "field": field,
        "source_path": source_path,
        "expected": expected,
        "sidecar_value": sidecar_val,
        "md_value": md_val,
        "result": result,
        "issue": issue,
    }


def check_close(sidecar, md_text, kline_row, kline_path, date_compact) -> dict:
    """检查收盘价"""
    field = "delta.close"
    expected = kline_row.get("close") if kline_row else None
    sidecar_val = (sidecar or {}).get("delta", {}).get("close") if sidecar else None
    md_val = extract_md_close(md_text, date_compact) if md_text else None

    if expected is None:
        return make_check(field, kline_path, None, sidecar_val, md_val, "WARN",
                          "kline_cache 无当日行情数据" if kline_path else f"kline_cache 文件不存在: {kline_path}")
    if sidecar_val is None:
        return make_check(field, kline_path, expected, None, md_val, "BLOCK",
                          f"sidecar 缺 delta.close (权威源={expected})")

    errs = []
    if abs(sidecar_val - expected) > 0.001:
        errs.append(f"sidecar={sidecar_val} ≠ 权威源={expected}")
    # ⛔ MD 存在但无法解析 close + 权威源有值 → BLOCK
    if md_text and expected is not None and md_val is None:
        errs.append(f"MD 存在但无法解析 close (权威源={expected})")
    if md_val is not None and abs(md_val - expected) > 0.001:
        errs.append(f"MD={md_val} ≠ 权威源={expected}")
    if md_val is not None and sidecar_val is not None and abs(md_val - sidecar_val) > 0.001:
        errs.append(f"MD={md_val} ≠ sidecar={sidecar_val}")

    if errs:
        return make_check(field, kline_path, expected, sidecar_val, md_val, "BLOCK", "; ".join(errs))
    return make_check(field, kline_path, expected, sidecar_val, md_val, "PASS", "")


def check_change_pct(sidecar, md_text, kline_row, kline_path, date_compact) -> dict:
    """检查涨跌幅"""
    field = "delta.change_pct"
    # kline may have change_pct, pct_chg, or we can compute
    expected = None
    for src_f in ["change_pct", "pct_chg", "changePercent"]:
        if kline_row and src_f in kline_row:
            expected = float(kline_row[src_f])
            break

    sidecar_val = (sidecar or {}).get("delta", {}).get("change_pct") if sidecar else None
    md_val = extract_md_change_pct(md_text, date_compact) if md_text else None

    if expected is None and kline_row:
        # Try to compute from close
        return make_check(field, kline_path, None, sidecar_val, md_val, "WARN",
                          "kline_cache 无 change_pct/pct_chg 字段，跳过数值校验")
    if expected is None:
        return make_check(field, kline_path, None, sidecar_val, md_val, "WARN",
                          "kline_cache 无当日数据" if kline_path else f"kline_cache 不存在: {kline_path}")

    errs = []
    # 权威源有值但 sidecar 缺字段 → BLOCK
    if sidecar_val is None:
        errs.append(f"sidecar 缺 delta.change_pct (权威源={expected}%)")
    elif abs(sidecar_val - expected) > 0.05:
        errs.append(f"sidecar={sidecar_val}% ≠ 权威源={expected}%")
    # ⛔ MD 存在但无法解析 change_pct + 权威源有值 → BLOCK
    if md_text and expected is not None and md_val is None:
        errs.append(f"MD 存在但无法解析 change_pct (权威源={expected}%)")
    if md_val is not None and abs(md_val - expected) > 0.05:
        errs.append(f"MD={md_val}% ≠ 权威源={expected}%")
    if sidecar_val is not None and md_val is not None and abs(md_val - sidecar_val) > 0.05:
        errs.append(f"MD={md_val}% ≠ sidecar={sidecar_val}%")

    if errs:
        return make_check(field, kline_path, expected, sidecar_val, md_val, "BLOCK", "; ".join(errs))
    return make_check(field, kline_path, expected, sidecar_val, md_val, "PASS", "")


def check_volume(sidecar, md_text, kline_row, kline_path, date_compact) -> dict:
    """检查成交量（万手）。
    sidecar 单位: 万手 (36.2)
    kline_cache 单位: 股 (36248943)
    转换: 万手 = 股 / 1000000.0
    """
    field = "delta.volume_wan_shou"
    expected_raw = kline_row.get("volume") if kline_row else None
    sidecar_val = (sidecar or {}).get("delta", {}).get("volume_wan_shou") if sidecar else None
    md_val = extract_md_volume(md_text, date_compact) if md_text else None

    if expected_raw is None:
        return make_check(field, kline_path, None, sidecar_val, md_val, "WARN",
                          "kline_cache 无当日成交量")

    # Convert kline 股 to 万手: 1万手 = 1,000,000股
    expected_wan_shou = round(expected_raw / 1000000.0, 1)

    errs = []
    # ⛔ sidecar 缺 volume_wan_shou 且权威源有值 → BLOCK
    if sidecar_val is None:
        errs.append(f"sidecar 缺 delta.volume_wan_shou (权威源={expected_wan_shou}万手)")
    else:
        diff = abs(sidecar_val - expected_wan_shou)
        if diff > 1.0:
            errs.append(f"sidecar volume_wan_shou={sidecar_val} ≠ 权威源(折算)={expected_wan_shou} 万手 (差{diff:.1f})")
        elif diff > 0.0:
            errs.append(f"WARN: sidecar={sidecar_val} vs 权威源={expected_wan_shou} 万手 (差{diff:.1f})")

    # ⛔ MD 存在但无法解析成交量 + 权威源有值 → BLOCK
    if md_text and expected_wan_shou is not None and md_val is None:
        errs.append(f"MD 存在但无法解析成交量 (权威源={expected_wan_shou}万手)")

    if md_val is not None:
        diff_md = abs(md_val - expected_wan_shou)
        if diff_md > 1.0:
            errs.append(f"MD volume={md_val} ≠ 权威源(折算)={expected_wan_shou} 万手")
        elif diff_md > 0.0 and sidecar_val is not None:
            pass  # small diff is OK given rounding

    if sidecar_val is not None and md_val is not None and abs(sidecar_val - md_val) > 1.0:
        errs.append(f"MD={md_val}万手 ≠ sidecar={sidecar_val}万手")

    if errs:
        # sidecar 缺失直接 BLOCK，不为 WARN
        has_block = any("≠" in e and "WARN" not in e for e in errs) or any("缺 " in e for e in errs)
        result = "BLOCK" if has_block else "WARN"
        issue = "; ".join(errs)
        return make_check(field, kline_path, expected_wan_shou, sidecar_val, md_val, result, issue)
    return make_check(field, kline_path, expected_wan_shou, sidecar_val, md_val, "PASS", "")


def check_fund_flow_field(key, display_name, sidecar, md_fund_flow, ff_row, ff_path) -> dict:
    """检查单个资金字段"""
    field = f"fund_flow.{key}"
    sidecar_raw = (sidecar or {}).get("fund_flow_4level", {}).get(key) if sidecar else None
    sidecar_val = normalize_amount(sidecar_raw) if sidecar_raw else None

    expected_raw = ff_row.get(key) if ff_row else None
    expected = float(expected_raw) if expected_raw is not None else None

    md_val = (md_fund_flow or {}).get(key)

    if expected is None:
        return make_check(field, ff_path, None, sidecar_val, md_val, "WARN",
                          "权威源无此资金字段" if ff_path else f"fund_flow_cache 不存在: {ff_path}")

    errs = []
    if sidecar_val is None:
        errs.append(f"sidecar 缺 fund_flow.{key} (权威源={expected}万)")
    elif abs(sidecar_val - expected) > 1.0:
        errs.append(f"sidecar {display_name}={sidecar_val}万 ≠ 权威源={expected}万 (差{abs(sidecar_val-expected):.0f}万)")
    # ⛔ MD 存在（且解析到资金表部分字段）但缺此字段 + 权威源有值 → BLOCK
    if md_fund_flow and expected is not None and (key not in md_fund_flow):
        errs.append(f"MD 资金表存在但缺 {display_name} (权威源={expected}万)")
    if md_val is not None and abs(md_val - expected) > 1.0:
        errs.append(f"MD {display_name}={md_val}万 ≠ 权威源={expected}万")
    if sidecar_val is not None and md_val is not None and abs(sidecar_val - md_val) > 1.0:
        errs.append(f"MD {display_name}={md_val}万 ≠ sidecar={sidecar_val}万")

    if errs:
        return make_check(field, ff_path, expected, sidecar_val, md_val, "BLOCK", "; ".join(errs))
    return make_check(field, ff_path, expected, sidecar_val, md_val, "PASS", "")


def _check_source_snapshot_exception(sidecar, md_date_str, expected_date, date_compact):
    """检查 source_snapshot_exception 的 7 个条件。
    全部满足 → True (发布后数据更新)
    任一不满足 → False (仍为 BLOCK)

    条件3 使用 date_compact（YYYYMMDD）而非 sidecar.trade_date 校验。
    条件4 要求 lag_days 严格为 int。
    """
    if not sidecar:
        return False, "sidecar 不存在，无法检查 source_snapshot"

    # 条件1: report_generated_at 存在且合法 ISO
    rg = sidecar.get("report_generated_at")
    if not rg:
        return False, "条件1不满足: 无 report_generated_at"
    try:
        _ = datetime.fromisoformat(rg)
    except (ValueError, TypeError):
        return False, "条件1不满足: report_generated_at 不是合法 ISO 时间"

    # 条件2: source_snapshot.margin 存在
    ss_margin = (sidecar.get("source_snapshot") or {}).get("margin")
    if not ss_margin:
        return False, "条件2不满足: 无 source_snapshot.margin"

    s_latest = ss_margin.get("latest_trade_date")
    if not s_latest:
        return False, "条件2不满足: source_snapshot.margin.latest_trade_date 不存在"

    # 条件3: report_trade_date == date_compact（YYYYMMDD）
    s_report_td = ss_margin.get("report_trade_date")
    if not s_report_td or str(s_report_td) != str(date_compact).replace("-", ""):
        return False, f"条件3不满足: report_trade_date={s_report_td} ≠ date_compact={date_compact}"

    # 条件4: lag_days 严格 int，且 == report_trade_date - latest_trade_date
    s_lag = ss_margin.get("lag_days")
    if not isinstance(s_lag, int):
        return False, f"条件4不满足: lag_days={s_lag} 不是 int 类型 (type={type(s_lag).__name__})"
    from datetime import datetime as dt_lag
    try:
        l_d = dt_lag.strptime(str(s_latest), "%Y%m%d").date()
        r_d = dt_lag.strptime(str(s_report_td), "%Y%m%d").date()
        expected_lag = (r_d - l_d).days
    except (ValueError, TypeError):
        return False, "条件4不满足: 日期格式无法计算 lag_days"
    if s_lag != max(0, expected_lag):
        return False, f"条件4不满足: lag_days={s_lag} ≠ 计算值={max(0, expected_lag)}"

    # 条件5: declared_in 含 degraded_items
    declared = str(ss_margin.get("declared_in", ""))
    if "degraded_items" not in declared:
        return False, f"条件5不满足: declared_in={declared} 未包含 degraded_items"

    # 条件6: MD 融资日期 == snapshot latest_trade_date
    if md_date_str and str(md_date_str) != str(s_latest):
        return False, f"条件6不满足: MD融资日期={md_date_str} ≠ snapshot latest_trade_date={s_latest}"

    # 条件7: 当前 margin_detail[0].trade_date > snapshot latest_trade_date
    if str(expected_date) <= str(s_latest):
        return False, f"条件7不满足: 当前margin_detail最新={expected_date} 未超过 snapshot最新={s_latest}"

    return True, f"发布后数据更新: 报告生成后 margin_detail 从 {s_latest} 更新至 {expected_date}"


def check_margin(sidecar, md_text, margin_row, margin_path, date_compact) -> dict:
    """检查融资最新日期。融资余额可选检查。
    含 source_snapshot_exception 分支（第5.5-C）。"""
    field = "margin.latest_date"
    if not margin_row:
        return make_check(field, margin_path, None, None, None, "WARN",
                          "margin_detail 文件不存在或无数据")
    expected_date = margin_row.get("trade_date", "")

    # Try to find margin date in MD text
    md_date_str = extract_md_margin_date(md_text) if md_text else None

    if not md_date_str:
        return make_check(field, margin_path, expected_date, None, None, "PASS",
                          "MD 未明确提及融资日期，跳过")

    if md_date_str != expected_date:
        # 仅在日期不一致时进入 source_snapshot_exception 分支
        exc_pass, exc_msg = _check_source_snapshot_exception(sidecar, md_date_str, expected_date, date_compact)
        if exc_pass:
            return make_check(field, margin_path, expected_date, None, md_date_str, "WARN",
                              exc_msg)
        return make_check(field, margin_path, expected_date, None, md_date_str, "BLOCK",
                          f"MD 声明融资最新日期={md_date_str} ≠ 权威源最新={expected_date}" +
                          (f"；source_snapshot_exception 失败: {exc_msg}" if not exc_pass else ""))
    return make_check(field, margin_path, expected_date, None, md_date_str, "PASS", "")


def check_sector_phase(sidecar, md_text, sector_data, sector_path) -> dict:
    """检查板块相位"""
    field = "sector_phase.phase"
    sidecar_phase = (sidecar or {}).get("sector_phase", {}).get("phase") if sidecar else None
    md_phase = extract_md_sector_phase(md_text) if md_text else None

    expected_phase = sector_data.get("phase") if sector_data else None

    if expected_phase is None:
        return make_check(field, sector_path, None, sidecar_phase, md_phase, "WARN",
                          "data_scored 无该股票相位信息")

    errs = []
    if not sidecar_phase:
        errs.append(f"sidecar 缺 sector_phase.phase (data_scored='{expected_phase}')")
    elif sidecar_phase != expected_phase:
        errs.append(f"sidecar phase='{sidecar_phase}' ≠ data_scored='{expected_phase}'")
    # ⛔ MD 存在但无法解析板块相位 + 权威源有值 → BLOCK
    if md_text and expected_phase is not None and not md_phase:
        errs.append(f"MD 存在但无法解析板块相位 (data_scored='{expected_phase}')")
    if md_phase and md_phase != expected_phase:
        errs.append(f"MD phase='{md_phase}' ≠ data_scored='{expected_phase}'")
    if sidecar_phase and md_phase and sidecar_phase != md_phase:
        errs.append(f"MD='{md_phase}' ≠ sidecar='{sidecar_phase}'")

    if errs:
        return make_check(field, sector_path, expected_phase, sidecar_phase, md_phase, "BLOCK", "; ".join(errs))
    return make_check(field, sector_path, expected_phase, sidecar_phase, md_phase, "PASS", "")


# ============================================================
# E. Kline L2 数值一致性（仅注册检查，不阻断）
# ============================================================

def check_kline_l2_numeric() -> dict:
    """检查 kline_l2 在 numeric_field_mapping.json 中的注册状态。
    返回 SKIP/WARN，Phase 2 前不 BLOCK。"""
    field = "kline_l2.numeric"
    MAPPING_PATH = PROJECT_ROOT / "00_项目地基" / "04_一致性闸门" / "numeric_field_mapping.json"
    mapping_path = Path(str(MAPPING_PATH))

    if not mapping_path.exists():
        return make_check(field, str(mapping_path), None, None, None, "WARN",
                          "numeric_field_mapping.json 不存在")

    try:
        import json as _json
        with open(mapping_path, "r", encoding="utf-8-sig") as f:
            mapping = _json.load(f)
        kl2 = mapping.get("mappings", {}).get("kline_l2", {})
    except Exception as e:
        return make_check(field, str(mapping_path), None, None, None, "WARN",
                          f"numeric_field_mapping.json 解析失败: {e}")

    enabled = kl2.get("enabled", False)
    phase = kl2.get("phase", 0)

    if not enabled or phase < 2:
        return make_check(field, f"kline_l2 enabled={enabled} phase={phase}",
                          None, None, None, "PASS",
                          f"kline_l2: SKIP (enabled={enabled}, phase={phase}) — Phase 2 前跳过 L2 数值检查")
    else:
        return make_check(field, f"kline_l2 enabled={enabled} phase={phase}",
                          None, None, None, "PASS",
                          f"kline_l2: registered (enabled={enabled}, phase={phase}) — 数值检查已就绪")


# ============================================================
# 核心检查逻辑
# ============================================================

def check_one(code: str, name: str, trade_date_str: str) -> dict:
    """检查单只股票。返回包含 checks 列表的结果字典。"""
    result = {
        "stock_code": code,
        "stock_name": name,
        "trade_date": trade_date_str,
        "result": "PASS",
        "checks": [],
    }

    date_compact = trade_date_str.replace("-", "")
    try:
        td = parse_date(trade_date_str)
    except ValueError as e:
        result["result"] = "BLOCK"
        result["checks"].append(make_check("general", "", None, None, None, "BLOCK",
                                            f"日期格式错误: {e}"))
        return result

    # 加载报告文件
    sidecar_path = find_report_file(code, name, date_compact, ".json")
    md_path = find_report_file(code, name, date_compact, ".md")

    # 缺陷5：文件缺失显式 BLOCK
    file_missing = False
    if not sidecar_path.exists():
        file_missing = True
        result["result"] = "BLOCK"
        result["checks"].append(make_check("general", str(sidecar_path), None, None, None,
                                            "BLOCK", f"日报 sidecar 文件不存在: {sidecar_path}"))
    if not md_path.exists():
        file_missing = True
        result["result"] = "BLOCK"
        result["checks"].append(make_check("general", str(md_path), None, None, None,
                                            "BLOCK", f"日报 MD 文件不存在: {md_path}"))

    sidecar = None
    md_text = None

    if sidecar_path.exists():
        try:
            sidecar = load_json(sidecar_path)
        except Exception as e:
            result["result"] = "BLOCK"
            result["checks"].append(make_check("general", str(sidecar_path), None, None, None,
                                                "BLOCK", f"sidecar JSON解析失败: {e}"))
    if md_path.exists():
        md_text = load_text(md_path)

    # 加载权威数据
    kline_row, kline_path = load_kline(code, td)
    ff_row, ff_path = load_fund_flow(code, td)
    margin_row, margin_path = load_margin_latest(code)
    sector_data, sector_path = load_sector_phase(code)
    md_fund_flow = extract_md_fund_flow(md_text) if md_text else {}

    # ---- A: 行情字段 ----
    chk = check_close(sidecar, md_text, kline_row, kline_path, date_compact)
    result["checks"].append(chk)
    if chk["result"] == "BLOCK": result["result"] = "BLOCK"

    chk = check_change_pct(sidecar, md_text, kline_row, kline_path, date_compact)
    result["checks"].append(chk)
    if chk["result"] == "BLOCK": result["result"] = "BLOCK"

    chk = check_volume(sidecar, md_text, kline_row, kline_path, date_compact)
    result["checks"].append(chk)
    if chk["result"] == "BLOCK": result["result"] = "BLOCK"

    # ---- B: 四档资金 ----
    if ff_row or (sidecar and sidecar.get("fund_flow_4level")):
        fund_fields = [
            ("super_large_net", "超大单"),
            ("large_net", "大单"),
            ("medium_net", "中单"),
            ("small_net", "小单"),
            ("main_force_net", "主力合计"),
        ]
        for key, display in fund_fields:
            chk = check_fund_flow_field(key, display, sidecar, md_fund_flow, ff_row, ff_path)
            result["checks"].append(chk)
            if chk["result"] == "BLOCK": result["result"] = "BLOCK"
    else:
        result["checks"].append(make_check("fund_flow", ff_path, None, None, None, "WARN",
                                            "四档资金数据不可用"))

    # ---- C: 融资 ----
    chk = check_margin(sidecar, md_text, margin_row, margin_path, date_compact)
    result["checks"].append(chk)
    if chk["result"] == "BLOCK": result["result"] = "BLOCK"

    # ---- D: 板块相位 ----
    chk = check_sector_phase(sidecar, md_text, sector_data, sector_path)
    result["checks"].append(chk)
    if chk["result"] == "BLOCK": result["result"] = "BLOCK"

    # ---- E: Kline L2 数值一致性（Phase 2 前不阻断） ----
    chk = check_kline_l2_numeric()
    result["checks"].append(chk)
    # L2 检查不升级为 BLOCK（Phase 2 前不阻断当日报告）
    if chk["result"] == "BLOCK":
        chk["result"] = "WARN"

    return result


# ============================================================
# 输出格式化
# ============================================================

def format_text_result(result: dict) -> str:
    """可读文本输出"""
    lines = []
    lines.append(f"{'='*60}")
    lines.append(f" {result['stock_name']}({result['stock_code']}) | {result['trade_date']}")
    lines.append(f"{'='*60}")
    lines.append(f"  总结果: {result['result']}")
    lines.append("")

    for chk in result.get("checks", []):
        status_icon = {"PASS": "✅", "WARN": "⚠️", "BLOCK": "❌"}.get(chk["result"], "❓")
        lines.append(f"  {status_icon} {chk['field']}: {chk['result']}")
        if chk.get("expected") is not None or chk.get("sidecar_value") is not None:
            exp_str = str(chk["expected"])[:30] if chk["expected"] is not None else "N/A"
            sc_str = str(chk["sidecar_value"])[:30] if chk["sidecar_value"] is not None else "N/A"
            md_str = str(chk["md_value"])[:30] if chk["md_value"] is not None else "N/A"
            lines.append(f"     预期={exp_str} | sidecar={sc_str} | MD={md_str}")
        if chk.get("issue"):
            lines.append(f"     问题: {chk['issue']}")
        if chk.get("source_path"):
            lines.append(f"     来源: {chk['source_path']}")

    pass_count = sum(1 for c in result["checks"] if c["result"] == "PASS")
    warn_count = sum(1 for c in result["checks"] if c["result"] == "WARN")
    block_count = sum(1 for c in result["checks"] if c["result"] == "BLOCK")
    total = len(result["checks"])
    lines.append(f"\n  明细: ✅PASS={pass_count} ⚠️WARN={warn_count} ❌BLOCK={block_count} / TOTAL={total}")

    return "\n".join(lines) + "\n"


# ============================================================
# Main
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="P0-B: 数值来源一致性闸门 — 检查日报数字与权威数据源一致性"
    )
    parser.add_argument("--code", help="股票代码")
    parser.add_argument("--name", help="股票名称")
    parser.add_argument("--date", required=True, help="交易日期 YYYYMMDD 或 YYYY-MM-DD")
    parser.add_argument("--all", action="store_true", help="检查全部重点股票")
    parser.add_argument("--json", action="store_true", help="JSON 格式输出")
    args = parser.parse_args()

    # 获取股票池
    stocks = []
    if args.all:
        stocks = get_stock_pool()
        if not stocks:
            stocks = get_stock_pool_from_reports()
        if not stocks:
            print("ERROR: 无法获取股票池")
            return 1
    elif args.code and args.name:
        stocks = [(args.code, args.name)]
    else:
        parser.error("需要 --code --name 或 --all")

    results = []
    all_pass = True
    for code, name in stocks:
        res = check_one(code, name, args.date)
        results.append(res)
        if res["result"] == "BLOCK":
            all_pass = False

    # 输出
    if args.json:
        output = []
        for r in results:
            output.append(r)
        print(json.dumps(output, ensure_ascii=False, indent=2))

        if all_pass:
            print("\nNUMERIC_CONSISTENCY_ALL: PASS", file=sys.stderr)
        else:
            print("\nNUMERIC_CONSISTENCY_ALL: BLOCK", file=sys.stderr)
    else:
        for r in results:
            print(format_text_result(r))

        pass_count = sum(1 for r in results if r["result"] == "PASS")
        block_count = sum(1 for r in results if r["result"] == "BLOCK")
        print(f"{'='*60}")
        print(f"  PASS: {pass_count} | BLOCK: {block_count} | TOTAL: {len(results)}")
        print(f"{'='*60}")

    return 0 if all_pass else 2


if __name__ == "__main__":
    sys.exit(main())
