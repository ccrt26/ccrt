#!/usr/bin/env python3
"""
P0-D: MD 与 JSON sidecar 一致性闸门 — 检查同一只股票同一交易日的 MD 与 sidecar JSON 是否一致。

检查范围:
  A. 报告身份字段 (stock_code/name/date/baseline_id)
  B. P0 明日决策卡 (9字段)
  C. 行情字段 (close/change_pct/volume)
  D. 四档资金 (5字段)
  E. 板块相位 (MD vs sidecar + sidecar 内部)
  F. 风控灯 (overall + machine_fields + 角色内)
  G. eval_hooks
  H. sidecar 内部镜像一致性

用法:
  python3 scripts/check_md_sidecar_consistency.py --code 600114 --name 东睦股份 --date 20260602
  python3 scripts/check_md_sidecar_consistency.py --all --date 20260602
  python3 scripts/check_md_sidecar_consistency.py --code 600114 --name 东睦股份 --date 20260602 --json

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
_REPORT_OVERRIDE = os.environ.get("REPORT_ROOT_OVERRIDE")
REPORT_DIR = Path(_REPORT_OVERRIDE) if _REPORT_OVERRIDE else PROJECT_ROOT / "重点股票" / "股票报告"
PIGEON_CONFIG = PROJECT_ROOT / "代码文件" / "信鸽信息采集" / "pigeon_config.json"


# ============================================================
# 辅助函数
# ============================================================

def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_text(path):
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="ignore")


def clean_md(text):
    """去除 MD 粗体标记和多余空格"""
    if not text:
        return text
    return text.replace("**", "").strip()


def normalize_amount(amount_str):
    """规范化金额字符串为数字（万元）"""
    if amount_str is None:
        return None
    if isinstance(amount_str, (int, float)):
        return float(amount_str)
    s = str(amount_str).strip().replace(",", "").replace("+", "").replace(" ", "")
    if "亿" in s:
        try:
            return round(float(s.replace("亿", "")) * 10000, 2)
        except ValueError:
            return None
    elif "万" in s:
        try:
            return float(s.replace("万", ""))
        except ValueError:
            return None
    elif "元" in s:
        try:
            return float(s.replace("元", ""))
        except ValueError:
            return None
    else:
        try:
            return float(s)
        except ValueError:
            return None


def extract_price(text):
    """从文本中提取第一个价格数字"""
    if not text:
        return None
    m = re.search(r'([\d.]+)', str(text))
    if m:
        return float(m.group(1))
    return None


def make_chk(field, md_val, sc_val, result, issue):
    return {"field": field, "result": result, "md_value": md_val, "sidecar_value": sc_val, "issue": issue}


def find_report_file(code, name, date_compact, ext):
    subdir = REPORT_DIR / f"{name}({code})"
    return subdir / f"{name}({code})日报_{date_compact}{ext}"


def get_stock_pool():
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


def get_stock_pool_from_reports():
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


def compact_date(date_str):
    return date_str.replace("-", "")


# ============================================================
# 动作方向判断
# ============================================================

def action_direction(text):
    """判断动作方向：buy/hold/sell/watch/neutral/unknown。
    返回: "buy" / "sell" / "hold" / "review" / "neutral" / "mixed"
    """
    t = clean_md(str(text)).lower()

    has_neg_hold = any(kw in t for kw in ["不买", "不追", "不建仓", "不追高", "不抄", "不买入", "不加仓", "不增持", "不建",
                                            "默认不买", "不操作", "不做", "不建议当前"])
    has_hold = any(kw in t for kw in ["观望", "暂停观察"])
    has_buy = any(kw in t for kw in ["买入", "加仓", "建仓", "增持", "试探", "可试探"])
    has_sell = any(kw in t for kw in ["卖出", "减仓", "清仓", "减仓"])
    has_review = any(kw in t for kw in ["重评", "重新评估", "reanalysis"])

    if (has_neg_hold or has_hold) and (has_buy or has_sell):
        return "mixed"
    if has_neg_hold: return "hold"
    if has_hold: return "hold"
    if has_buy: return "buy"
    if has_sell: return "sell"
    if has_review: return "review"
    return "neutral"


def extract_primary_action(text):
    """从 possibly conditional 文本中提取当前动作（主句 + 条件句前的部分）。
    例如 "默认不买，只有站回S1才考虑试探" → primary=hold, conditional=buy
    返回 "buy"/"sell"/"hold"/"review"/"neutral"（不含 mixed）
    """
    t = clean_md(str(text)).lower()

    # 条件标记：这些词后面的内容视为条件动作，不影响当前动作判定
    cond_markers = ["只有", "等", "若", "如果", "满足", "站回", "回踩", "缩量",
                     "触发后", "再考虑", "才考虑", "可评估", "等回踩", "当", "一旦", "确认后"]

    # 从条件标记处截断（取条件标记前的文本用于当前动作判定）
    pre_cond = t
    for m in cond_markers:
        idx = pre_cond.find(m)
        if idx >= 0:
            pre_cond = pre_cond[:idx]
            break

    # 在截断后的文本中判定方向
    has_neg_hold = any(kw in pre_cond for kw in ["不买", "不追", "不建仓", "不追高", "不抄", "不买入",
                                                   "不加仓", "不增持", "不建", "默认不买", "不操作", "不做",
                                                   "不建议当前"])
    has_hold = any(kw in pre_cond for kw in ["观望", "暂停观察"])
    has_buy = any(kw in pre_cond for kw in ["买入", "加仓", "建仓", "增持"])
    has_sell = any(kw in pre_cond for kw in ["卖出", "减仓", "清仓"])

    if has_neg_hold: return "hold"
    if has_hold: return "hold"
    if has_buy: return "buy"
    if has_sell: return "sell"
    # 截断后无明确词，回退到全文检测纯动作
    return action_direction(text)


def has_extra_position_claim(md_one_line, sc, md_p0):
    """检测 MD one_line 中是否有 sidecar/P0 表未反映的额外持仓/止损声明。
    例如 MD 写 "已试探仓持有,止损上移至37" 但 SC held_position_stop_loss=33.4
    返回 (has_issue, description)
    """
    if not md_one_line: return (False, "")
    t = clean_md(str(md_one_line)).lower()

    issues = []

    # 检测止损上移声明
    m = re.search(r'止损上移[至到]\s*([\d.]+)', t)
    if m:
        md_new_stop = float(m.group(1))
        # 与 SC P0 表中的 held_position_stop_loss 对比
        sc_held_raw = (sc or {}).get("p0_decision_card", {}).get("held_position_stop_loss", "")
        sc_held = extract_price(sc_held_raw)
        if sc_held and abs(md_new_stop - sc_held) > 0.01:
            issues.append(f"MD one_line 声明止损上移至{md_new_stop}元，但 sidecar 已持仓止损={sc_held}元")

    # 检测已持仓声明
    if re.search(r'已\S*仓', t):
        sc_cap = (sc or {}).get("p0_decision_card", {}).get("current_position_cap", "")
        if not sc_cap or sc_cap == "0%":
            issues.append(f"MD one_line 声称有持仓，但 sidecar 当前仓位上限={sc_cap or '空'}")

    if issues:
        return (True, "; ".join(issues))
    return (False, "")


def action_conflict(md_dir, sc_dir):
    """两个方向是否冲突。"""
    if md_dir == sc_dir:
        return False
    if md_dir == "mixed" or sc_dir == "mixed":
        return True
    if {"buy", "sell"} == {md_dir, sc_dir}:
        return True
    if md_dir == "buy" and sc_dir == "hold":
        return True
    if md_dir == "hold" and sc_dir == "buy":
        return True
    if md_dir == "sell" and sc_dir == "hold":
        return True
    if md_dir == "hold" and sc_dir == "sell":
        return True
    return False


# ============================================================
# MD 提取函数
# ============================================================

def extract_md_baseline_id(md_text):
    """从MD提取 baseline_id（头部的唯一一个）。
    如果 MD 中出现多个不同的 baseline_id，返回所有 ID 的列表。"""
    ids = re.findall(r'baseline_id[：:]\s*([^\s\|\)\]\*,\n]+)', md_text)
    ids = [i.strip() for i in ids if i.strip()]
    unique = list(set(ids))
    if len(unique) == 1:
        return unique[0]
    elif len(unique) > 1:
        # 返回特殊标志，调用方检测多个不同 ID
        return "__MULTIPLE__:" + "|".join(unique)
    return None


def extract_md_trade_date(md_text):
    """从 MD 头部提取交易日期。格式: **2026-06-02（周二）** """
    clean = md_text.replace("**", "")
    m = re.search(r'(\d{4}-\d{2}-\d{2})', clean[:200])
    if m:
        return m.group(1)
    return None


def extract_md_p0_table(md_text):
    """从P0决策卡表格提取字段"""
    results = {}
    clean = md_text.replace("**", "")
    # Find the P0 decision card section
    section_m = re.search(r'## 一、P0 明日决策卡(.+?)##', clean, re.S)
    if not section_m:
        return results
    section = section_m.group(1)

    # Mapping of MD label → key
    patterns = [
        (r'明日主动作[：:]*\s*(.+)', 't1_action'),
        (r'当前仓位上限[：:]*\s*([\d%]+)', 'current_position_cap'),
        (r'条件触发后仓位[：:]*\s*(.+)', 'triggered_position_cap'),
        (r'关键买点[：:]*\s*(.+)', 'key_buy_point'),
        (r'新仓止损[：:]*\s*(.+)', 'new_position_stop_loss'),
        (r'已持仓止损[：:]*\s*(.+)', 'held_position_stop_loss'),
        (r'禁止动作[：:]*\s*(.+)', 'forbidden_actions'),
        (r'置信度[：:]*\s*([高中低])', 'confidence_level'),
        (r'一句话结论[：:]*\s*(.+)', 'one_line_conclusion'),
    ]
    for pat, key in patterns:
        m = re.search(pat, section)
        if m:
            results[key] = m.group(1).strip()

    # Also try | 字段 | 内容 | table format
    if not results.get('t1_action'):
        m = re.search(r'\|\s*\*?明日主动作\*?\s*\|\s*(.+?)\s*\|', clean)
        if m: results['t1_action'] = m.group(1).strip()
    if not results.get('current_position_cap'):
        m = re.search(r'\|\s*\*?当前仓位上限\*?\s*\|\s*(.+?)\s*\|', clean)
        if m: results['current_position_cap'] = m.group(1).strip()
    if not results.get('new_position_stop_loss'):
        m = re.search(r'\|\s*\*?新仓止损\*?\s*\|\s*(.+?)\s*\|', clean)
        if m: results['new_position_stop_loss'] = m.group(1).strip()
    if not results.get('held_position_stop_loss'):
        m = re.search(r'\|\s*\*?已持仓止损\*?\s*\|\s*(.+?)\s*\|', clean)
        if m: results['held_position_stop_loss'] = m.group(1).strip()
    if not results.get('confidence_level'):
        m = re.search(r'\|\s*\*?置信度\*?\s*\|\s*(.*?)\s*\|', clean)
        if m:
            cm = re.search(r'[高中低]', m.group(1))
            if cm: results['confidence_level'] = cm.group(0)
    if not results.get('key_buy_point'):
        m = re.search(r'\|\s*\*?关键买点\*?\s*\|\s*(.+?)\s*\|', clean)
        if m: results['key_buy_point'] = m.group(1).strip()
    if not results.get('triggered_position_cap'):
        m = re.search(r'\|\s*\*?条件触发后仓位\*?\s*\|\s*(.+?)\s*\|', clean)
        if m: results['triggered_position_cap'] = m.group(1).strip()
    if not results.get('forbidden_actions'):
        m = re.search(r'\|\s*\*?禁止动作\*?\s*\|\s*(.+?)\s*\|', clean)
        if m: results['forbidden_actions'] = m.group(1).strip()

    return results


def extract_md_close(md_text, date_compact):
    """从MD行情表提取收盘价"""
    clean = md_text.replace("**", "")
    date_dashed = f"{date_compact[:4]}-{date_compact[4:6]}-{date_compact[6:8]}"
    pat = rf'\|?\s*{re.escape(date_dashed)}\s*\|\s*([\d.]+)\s*\|\s*([\d.]+)\s*\|'
    m = re.search(pat, clean)
    if m:
        return float(m.group(2))
    return None


def extract_md_change_pct(md_text, date_compact):
    """从MD提取涨跌幅"""
    month = int(date_compact[4:6])
    day = int(date_compact[6:8])
    date_cn = f"{month}月{day}日"
    clean = md_text.replace("**", "")
    pat = rf'{re.escape(date_cn)}.*?(下跌|上涨|跌|涨)\s*([\d.]+)%'
    m = re.search(pat, clean)
    if m:
        val = float(m.group(2))
        if m.group(1) in ("下跌", "跌"):
            val = -val
        return val
    # 样式2: 收86.32(+0.35%)
    m2 = re.search(r'收\s*[\d.]+\s*\(([+-]?\d+(?:\.\d+)?)%\)', clean)
    if m2:
        return float(m2.group(1))
    return None


def extract_md_volume(md_text, date_compact):
    """从MD行情表提取成交量（万手）"""
    clean = md_text.replace("**", "")
    date_dashed = f"{date_compact[:4]}-{date_compact[4:6]}-{date_compact[6:8]}"
    pat = rf'{re.escape(date_dashed)}[^|]*\|[^|]*\|[^|]*\|[^|]*\|[^|]*\|\s*([\d.]+)万手'
    m = re.search(pat, clean)
    if m:
        return float(m.group(1))
    return None


def extract_md_fund_flow(md_text):
    """从MD资金表提取资金数值"""
    result = {}
    clean = md_text.replace("**", "")
    lines = clean.split('\n')
    in_table = False
    name_map = {'超大单': 'super_large_net', '大单': 'large_net', '中单': 'medium_net',
                '中小单': 'medium_net', '中单/中小单': 'medium_net',
                '小单': 'small_net', '主力合计': 'main_force_net'}
    for line in lines:
        if '资金类型' in line and '净额' in line:
            in_table = True; continue
        if in_table:
            if not line.strip().startswith('|') or '---' in line:
                continue
            parts = [p.strip() for p in line.split('|') if p.strip()]
            if len(parts) >= 2 and parts[0] in name_map:
                amt = normalize_amount(parts[1])
                if amt is not None:
                    result[name_map[parts[0]]] = amt
    return result


def extract_md_sector_phase(md_text):
    """从MD大盘和板块提取板块相位"""
    clean = md_text.replace("**", "")
    phase_kw = r'(见底期|启动期|主升期|高潮期|退潮期|主升调整|衰退期|潜伏期|震荡期|筑底期|主跌期|反弹期|调整期)'
    pats = [rf'相位[：:]\s*{phase_kw}', rf'当前相位[：:]\s*{phase_kw}', rf'板块相位[：:]*\s*{phase_kw}']
    for pat in pats:
        m = re.search(pat, clean)
        if m: return m.group(1)
    return None


def extract_md_risk_light(md_text):
    """从MD风控段提取综合灯"""
    clean = md_text.replace("**", "")
    m = re.search(r'综合灯[：:]*\s*([^。\n；|]+)', clean)
    if m: return m.group(1)
    return None

def normalize_risk_light(value):
    text = str(value or "").replace("**", "").strip().lower()
    if not text:
        return ""
    if "🟢" in text or "绿" in text or "green" in text:
        return "green"
    if "🟡" in text or "黄" in text or "yellow" in text:
        return "yellow"
    if "🔴" in text or "红" in text or "red" in text:
        return "red"
    return text


def extract_md_forbidden_actions(md_text):
    """从MD提取禁止动作列表"""
    clean = md_text.replace("**", "")
    # Try "禁止动作" row
    m = re.search(r'禁止动作[：:]*\s*(.+?)(?:\n|$)', clean)
    if m:
        return [x.strip() for x in m.group(1).split('；') if x.strip()]
    # Try "不做清单" section
    m = re.search(r'不做清单[：:]*\s*(.+?)(?:\n)', clean)
    if m:
        return [x.strip() for x in m.group(1).split('；') if x.strip()]
    return []


def extract_md_eval_hooks(md_text):
    """从MD消息事件段提取T+1/T+5"""
    clean = md_text.replace("**", "")
    t1 = None; t5 = None
    m = re.search(r'T\+1\s*[\(（]([^)）]+)', clean)
    if m: t1 = m.group(1).strip()
    m = re.search(r'T\+5\s*[\(（]([^)）]+)', clean)
    if m: t5 = m.group(1).strip()
    if not t1:
        m = re.search(r'(?:验证点|验证|检查)[：:]*.*?(\d{1,2}/\d{1,2})', clean[:clean.find('T+5') if 'T+5' in clean else len(clean)])
    if not t5:
        m = re.search(r'T\+5[：:]*\s*(.+?)(?:\n|$)', clean)
        if m: t5 = m.group(1).strip()[:50]
    return t1, t5


def extract_md_one_line_conclusion(md_text):
    """从MD提取一句话结论"""
    clean = md_text.replace("**", "")
    # 明日一句话操作
    m = re.search(r'明日一句话操作[：:]\s*(.+?)(?:\n)', clean)
    if m: return m.group(1).strip()
    # 一句话结论
    m = re.search(r'一句话结论[：:]\s*(.+?)(?:\n)', clean)
    if m: return m.group(1).strip()
    return None


# ============================================================
# 核心检查
# ============================================================

def check_one(code, name, trade_date_str):
    result = {
        "stock_code": code, "stock_name": name, "trade_date": trade_date_str,
        "result": "PASS", "checks": []
    }
    dc = trade_date_str.replace("-", "")

    sidecar_path = find_report_file(code, name, dc, ".json")
    md_path = find_report_file(code, name, dc, ".md")

    if not sidecar_path.exists() or not md_path.exists():
        result["result"] = "BLOCK"
        result["checks"].append(make_chk("general", None, None, "BLOCK", "文件缺失"))
        return result

    sc = load_json(sidecar_path)
    md = load_text(md_path)

    def add(field, md_val, sc_val, result_val, issue):
        chk = make_chk(field, md_val, sc_val, result_val, issue)
        result["checks"].append(chk)
        if result_val == "BLOCK":
            result["result"] = "BLOCK"

    # === A. 报告身份 ===
    # A1 stock_code
    sc_code = sc.get("stock_code", "")
    add("stock_code", code, sc_code,
        "BLOCK" if code != sc_code else "PASS",
        "" if code == sc_code else f"路径代码={code} ≠ sidecar={sc_code}")

    # A2 stock_name
    sc_name = sc.get("stock_name", "")
    add("stock_name", name, sc_name,
        "BLOCK" if name != sc_name else "PASS",
        "" if name == sc_name else f"路径名称={name} ≠ sidecar={sc_name}")

    # A3 trade_date
    sc_date = sc.get("trade_date", "")
    md_date = extract_md_trade_date(md)
    td_err = []
    if sc_date and md_date:
        # Compare as compact
        if compact_date(sc_date) != compact_date(md_date):
            td_err.append(f"MD={md_date} ≠ sidecar={sc_date}")
    if td_err:
        add("trade_date", md_date, sc_date, "BLOCK", "; ".join(td_err))
    else:
        add("trade_date", md_date, sc_date, "PASS", "")

    # A4 baseline_id
    sc_bid = sc.get("baseline_id", "")
    md_bid_raw = extract_md_baseline_id(md)
    # 检查 MD 内部是否有多个不同的 baseline_id
    if md_bid_raw and md_bid_raw.startswith("__MULTIPLE__:"):
        ids = md_bid_raw.split(":", 1)[1]
        add("baseline_id", f"MD多ID:{ids}", sc_bid, "BLOCK",
            f"MD 内部出现多个不同 baseline_id: {ids}")
    else:
        md_bid = md_bid_raw
        if sc_bid and md_bid and sc_bid != md_bid:
            add("baseline_id", md_bid, sc_bid, "BLOCK", f"MD={md_bid} ≠ sidecar={sc_bid}")
        elif not sc_bid and md_bid:
            add("baseline_id", md_bid, None, "BLOCK", "sidecar 缺 baseline_id 但 MD 有")
        else:
            add("baseline_id", md_bid, sc_bid, "PASS", "")

    # === B. P0 决策卡 ===
    p0 = sc.get("p0_decision_card", {})
    md_p0 = extract_md_p0_table(md)

    # B1 t1_action
    sc_t1 = clean_md(str(p0.get("t1_action", "")))
    md_t1 = clean_md(str(md_p0.get("t1_action", "")))
    if md_t1 and sc_t1:
        md_dir = action_direction(md_t1)
        sc_dir = action_direction(sc_t1)
        if action_conflict(md_dir, sc_dir):
            add("p0.t1_action", md_t1, sc_t1, "BLOCK",
                f"动作方向冲突: MD={md_dir}({md_t1}) vs sidecar={sc_dir}({sc_t1})")
        else:
            add("p0.t1_action", md_t1, sc_t1, "PASS", "")
    else:
        add("p0.t1_action", md_t1, sc_t1,
            "BLOCK" if (md_t1 and not sc_t1) or (sc_t1 and not md_t1) else "PASS", "")

    # B2 current_position_cap
    sc_cap = p0.get("current_position_cap", "")
    md_cap = md_p0.get("current_position_cap", "")
    if sc_cap and md_cap:
        sc_pct = normalize_amount(sc_cap.replace("%", ""))
        md_pct = normalize_amount(md_cap.replace("%", ""))
        if sc_pct is not None and md_pct is not None and abs(sc_pct - md_pct) > 0.01:
            add("p0.current_position_cap", md_cap, sc_cap, "BLOCK",
                f"MD={md_cap} ≠ sidecar={sc_cap}")
        else:
            add("p0.current_position_cap", md_cap, sc_cap, "PASS", "")
    else:
        add("p0.current_position_cap", md_cap, sc_cap, "PASS", "")

    # B3 triggered_position_cap
    sc_trig = p0.get("triggered_position_cap", "")
    md_trig = md_p0.get("triggered_position_cap", "")
    if sc_trig and md_trig:
        sc_clean = clean_md(sc_trig)
        md_clean = clean_md(md_trig)
        if len(sc_clean) > 5 and len(md_clean) > 5:
            # Check key numbers/percentages
            sc_nums = set(re.findall(r'[\d.]+%?', sc_clean))
            md_nums = set(re.findall(r'[\d.]+%?', md_clean))
            overlap = sc_nums & md_nums
            if len(overlap) < min(len(sc_nums), len(md_nums)) * 0.3:
                add("p0.triggered_position_cap", md_trig, sc_trig, "WARN",
                    f"数字仅{len(overlap)}个重叠")
            else:
                add("p0.triggered_position_cap", md_trig, sc_trig, "PASS", "")
    else:
        add("p0.triggered_position_cap", md_trig, sc_trig, "PASS", "")

    # B4 key_buy_point
    sc_kbp = p0.get("key_buy_point", "")
    md_kbp = md_p0.get("key_buy_point", "")
    sc_bp = extract_price(sc_kbp)
    md_bp = extract_price(md_kbp)
    if sc_bp and md_bp and abs(sc_bp - md_bp) > 0.01:
        add("p0.key_buy_point", md_kbp, sc_kbp, "BLOCK",
            f"价格 MD={md_bp} ≠ sidecar={sc_bp}")
    else:
        add("p0.key_buy_point", md_kbp, sc_kbp, "PASS", "")

    # B5 new_position_stop_loss
    sc_sl = p0.get("new_position_stop_loss", "")
    md_sl = md_p0.get("new_position_stop_loss", "")
    sc_sl_p = extract_price(sc_sl)
    md_sl_p = extract_price(md_sl)
    if sc_sl_p and md_sl_p and abs(sc_sl_p - md_sl_p) > 0.01:
        add("p0.new_position_stop_loss", md_sl, sc_sl, "BLOCK",
            f"价格 MD={md_sl_p} ≠ sidecar={sc_sl_p}")
    else:
        add("p0.new_position_stop_loss", md_sl, sc_sl, "PASS", "")

    # B6 held_position_stop_loss
    sc_slh = p0.get("held_position_stop_loss", "")
    md_slh = md_p0.get("held_position_stop_loss", "")
    sc_slh_p = extract_price(sc_slh)
    md_slh_p = extract_price(md_slh)
    if sc_slh_p and md_slh_p and abs(sc_slh_p - md_slh_p) > 0.01:
        add("p0.held_position_stop_loss", md_slh, sc_slh, "BLOCK",
            f"价格 MD={md_slh_p} ≠ sidecar={sc_slh_p}")
    else:
        add("p0.held_position_stop_loss", md_slh, sc_slh, "PASS", "")

    # B7 forbidden_actions
    sc_fa = p0.get("forbidden_actions", [])
    md_fa_raw = extract_md_forbidden_actions(md)
    if isinstance(sc_fa, list) and sc_fa:
        missing = []
        for fa in sc_fa:
            fa_clean = clean_md(fa)
            found = any(fa_clean[:6] in clean_md(x) or clean_md(x)[:6] in fa_clean for x in md_fa_raw)
            if not found:
                missing.append(fa_clean)
        if missing:
            add("p0.forbidden_actions", "; ".join(md_fa_raw), "; ".join(sc_fa), "BLOCK",
                f"MD 缺禁止动作: {'; '.join(missing)}")
        else:
            add("p0.forbidden_actions", "; ".join(md_fa_raw), "; ".join(sc_fa), "PASS", "")
    else:
        add("p0.forbidden_actions", str(md_fa_raw), str(sc_fa), "PASS", "")

    # B8 confidence_level
    sc_conf = p0.get("confidence_level", "")
    md_conf = md_p0.get("confidence_level", "")
    # Normalize: extract just 高/中/低
    sc_conf_c = re.search(r'[高中低]', str(sc_conf))
    md_conf_c = re.search(r'[高中低]', str(md_conf))
    sc_conf_n = sc_conf_c.group(0) if sc_conf_c else None
    md_conf_n = md_conf_c.group(0) if md_conf_c else None
    if sc_conf_n and md_conf_n and sc_conf_n != md_conf_n:
        add("p0.confidence_level", md_conf, sc_conf, "BLOCK",
            f"MD={md_conf_n} ≠ sidecar={sc_conf_n}")
    else:
        add("p0.confidence_level", md_conf, sc_conf, "PASS", "")

    # B9 one_line_conclusion - action direction match (当前动作 only)
    sc_olc = p0.get("one_line_conclusion", "")
    md_olc = extract_md_one_line_conclusion(md)
    if sc_olc and md_olc:
        # 使用 extract_primary_action 只比较当前动作，条件动作（如"站回S1才..."）不计入冲突
        sc_prim = extract_primary_action(sc_olc)
        md_prim = extract_primary_action(md_olc)
        if action_conflict(md_prim, sc_prim):
            add("p0.one_line_conclusion", md_olc, sc_olc, "BLOCK",
                f"当前动作方向冲突: MD={md_prim}({md_olc[:25]}) vs sidecar={sc_prim}({sc_olc[:25]})")
        else:
            add("p0.one_line_conclusion", md_olc, sc_olc, "PASS", "")
        # 额外检测 MD one_line 中是否有 sidecar/P0 表未反映的持仓/止损声明
        has_extra, extra_issue = has_extra_position_claim(md_olc, sc, md_p0)
        if has_extra:
            add("p0.one_line_extra_claim", md_olc[:60], "(P0表/SC)", "BLOCK", extra_issue)
    else:
        add("p0.one_line_conclusion", md_olc, sc_olc, "PASS", "")

    # === C. 行情字段 ===
    delta = sc.get("delta", {})
    sc_close = delta.get("close")
    md_close = extract_md_close(md, dc)
    if sc_close and md_close and abs(float(sc_close) - md_close) > 0.001:
        add("delta.close", md_close, sc_close, "BLOCK", f"MD={md_close} ≠ sidecar={sc_close}")
    elif sc_close is not None and md_close is None:
        add("delta.close", "(MD行情表解析失败)", sc_close, "BLOCK",
            "sidecar 有 delta.close 但 MD 行情表无法解析")
    else:
        add("delta.close", md_close, sc_close, "PASS", "")

    sc_chg = delta.get("change_pct")
    md_chg = extract_md_change_pct(md, dc)
    if sc_chg and md_chg and abs(float(sc_chg) - md_chg) > 0.05:
        add("delta.change_pct", md_chg, sc_chg, "BLOCK",
            f"MD={md_chg}% ≠ sidecar={sc_chg}%")
    elif sc_chg is not None and md_chg is None:
        add("delta.change_pct", "(MD解析失败)", sc_chg, "BLOCK",
            "sidecar 有 change_pct 但 MD 无法解析")
    else:
        add("delta.change_pct", md_chg, sc_chg, "PASS", "")

    sc_vol = delta.get("volume_wan_shou")
    md_vol = extract_md_volume(md, dc)
    if sc_vol and md_vol and abs(float(sc_vol) - md_vol) > 1.0:
        add("delta.volume_wan_shou", md_vol, sc_vol, "BLOCK",
            f"MD={md_vol}万手 ≠ sidecar={sc_vol}万手")
    elif sc_vol is not None and md_vol is None:
        add("delta.volume_wan_shou", "(MD解析失败)", sc_vol, "BLOCK",
            "sidecar 有 volume_wan_shou 但 MD 无法解析")
    else:
        add("delta.volume_wan_shou", md_vol, sc_vol, "PASS", "")

    # === D. 四档资金 ===
    ff = sc.get("fund_flow_4level", {})
    md_ff = extract_md_fund_flow(md)
    fund_fields = [
        ("fund_flow.super_large_net", "super_large_net", "超大单"),
        ("fund_flow.large_net", "large_net", "大单"),
        ("fund_flow.medium_net", "medium_net", "中单"),
        ("fund_flow.small_net", "small_net", "小单"),
        ("fund_flow.main_force_net", "main_force_net", "主力合计"),
    ]
    for field, key, display in fund_fields:
        sc_val = normalize_amount(ff.get(key))
        md_val = md_ff.get(key)
        if sc_val is not None and md_val is not None:
            if abs(sc_val - md_val) > 1.0:
                add(field, md_val, sc_val, "BLOCK",
                    f"MD {display}={md_val}万 ≠ sidecar={sc_val}万")
            else:
                add(field, md_val, sc_val, "PASS", "")
        elif sc_val is not None and md_val is None:
            add(field, "(MD表中缺失)", sc_val, "BLOCK",
                f"MD 缺 {display} 但 sidecar 有={sc_val}万")
        else:
            add(field, md_val, sc_val, "PASS", "")

    # === E. 板块相位（三个独立检查，不能用 elif 吞掉问题） ===
    sc_phase = sc.get("sector_phase", {}).get("phase", "")
    md_phase = extract_md_sector_phase(md)
    ri = sc.get("role_interpretations", {})
    ri_shanmao_plain = ri.get("山猫_宏观", {}).get("板块相位", "") if ri else ""
    dd = ri.get("daily_discussion", {})
    ri_shanmao_dd = dd.get("山猫_大盘板块", {}).get("sector_phase", "") if dd else ""

    # E1: MD vs sidecar.sector_phase
    if not sc_phase:
        add("sector_phase.phase", md_phase, sc_phase, "BLOCK",
            "sidecar sector_phase.phase 为空")
    elif sc_phase and md_phase and sc_phase != md_phase:
        add("sector_phase.phase", md_phase, sc_phase, "BLOCK",
            f"MD='{md_phase}' ≠ sidecar='{sc_phase}'")
    else:
        add("sector_phase.phase", md_phase, sc_phase, "PASS", "")

    # E2: sidecar.sector_phase vs 山猫_宏观.板块相位
    if sc_phase and ri_shanmao_plain and sc_phase != ri_shanmao_plain:
        add("sector_phase.sc_vs_shanmao_macro", sc_phase, ri_shanmao_plain, "BLOCK",
            f"sidecar.sector_phase='{sc_phase}' ≠ 山猫_宏观='{ri_shanmao_plain}'")
    else:
        add("sector_phase.sc_vs_shanmao_macro", sc_phase, ri_shanmao_plain, "PASS", "")

    # E3: sidecar.sector_phase vs daily_discussion.山猫_大盘板块
    if sc_phase and ri_shanmao_dd and sc_phase != ri_shanmao_dd:
        add("sector_phase.sc_vs_shanmao_dd", sc_phase, ri_shanmao_dd, "BLOCK",
            f"sidecar.sector_phase='{sc_phase}' ≠ 大盘板块='{ri_shanmao_dd}'")
    else:
        add("sector_phase.sc_vs_shanmao_dd", sc_phase, ri_shanmao_dd, "PASS", "")

    # === F. 风控灯 ===
    sc_rl = sc.get("risk_light", {}).get("overall", "")
    mf_rl = sc.get("machine_fields", {}).get("risk_light", "")
    md_rl = extract_md_risk_light(md)
    ri_liujin_rl = ri.get("流金_风控", {}).get("综合灯", "") if ri else ""
    sc_rl_norm = normalize_risk_light(sc_rl)
    md_rl_norm = normalize_risk_light(md_rl)
    ri_liujin_rl_norm = normalize_risk_light(ri_liujin_rl)

    # F1: MD vs sidecar
    if md_rl and sc_rl and md_rl_norm != sc_rl_norm:
        add("risk_light.overall", md_rl, sc_rl, "BLOCK",
            f"MD='{md_rl}' ≠ sidecar='{sc_rl}'")
    else:
        add("risk_light.overall", md_rl, sc_rl, "PASS", "")

    # F2: sidecar vs 流金_风控.综合灯
    if sc_rl and ri_liujin_rl and sc_rl_norm != ri_liujin_rl_norm:
        add("risk_light.ri_liujin", sc_rl, ri_liujin_rl, "BLOCK",
            f"sidecar='{sc_rl}' ≠ 流金风控='{ri_liujin_rl}'")
    else:
        add("risk_light.ri_liujin", sc_rl, ri_liujin_rl, "PASS", "")

    # === G. eval_hooks 日期比较 ===
    eh = sc.get("eval_hooks", {})
    sc_t1_verify = eh.get("t1_verify", "")
    sc_t5_verify = eh.get("t5_verify", "")
    md_t1, md_t5 = extract_md_eval_hooks(md)

    def extract_date_from_text(text):
        if not isinstance(text, str): return None
        m = re.search(r'(\d{1,2})/(\d{1,2})', text)
        if m: return f"{int(m.group(1)):02d}/{int(m.group(2)):02d}"
        return None

    sc_t1_date = extract_date_from_text(sc_t1_verify)
    sc_t5_date = extract_date_from_text(sc_t5_verify)
    md_t1_date = extract_date_from_text(md_t1) if md_t1 else None
    md_t5_date = extract_date_from_text(md_t5) if md_t5 else None

    # G1: t1_verify 日期比较
    t1_issue = ""
    if sc_t1_date and md_t1_date and sc_t1_date != md_t1_date:
        t1_issue = f"MD T+1日期={md_t1_date} ≠ sidecar T+1日期={sc_t1_date}"
    add("eval_hooks.t1_verify",
        str(md_t1_date or md_t1 or "")[:60],
        str(sc_t1_date or sc_t1_verify or "")[:60],
        "BLOCK" if t1_issue else "PASS", t1_issue)

    # G2: t5_verify 日期比较
    t5_issue = ""
    if sc_t5_date and md_t5_date and sc_t5_date != md_t5_date:
        t5_issue = f"MD T+5日期={md_t5_date} ≠ sidecar T+5日期={sc_t5_date}"
    add("eval_hooks.t5_verify",
        str(md_t5_date or md_t5 or "")[:60],
        str(sc_t5_date or sc_t5_verify or "")[:60],
        "BLOCK" if t5_issue else "PASS", t5_issue)

    # === H. sidecar 内部镜像一致性 ===
    # H1 report_version
    sc_rv = sc.get("report_version", "")
    mf_rv = sc.get("machine_fields", {}).get("report_version", "")
    if sc_rv and mf_rv and sc_rv != mf_rv:
        add("mirror.report_version", f"mf={mf_rv}", f"top={sc_rv}", "BLOCK",
            f"top={sc_rv} ≠ machine={mf_rv}")
    else:
        add("mirror.report_version", f"mf={mf_rv}", f"top={sc_rv}", "PASS", "")

    # H2 stock_code
    mf_sc = sc.get("machine_fields", {}).get("stock_code", "")
    if sc_code and mf_sc and compact_date(sc_code) != compact_date(mf_sc):
        add("mirror.stock_code", f"mf={mf_sc}", f"top={sc_code}", "BLOCK",
            f"top={sc_code} ≠ machine={mf_sc}")
    else:
        add("mirror.stock_code", f"mf={mf_sc}", f"top={sc_code}", "PASS", "")

    # H3 trade_date
    mf_td = sc.get("machine_fields", {}).get("trade_date", "")
    if sc_date and mf_td and compact_date(sc_date) != compact_date(mf_td):
        add("mirror.trade_date", f"mf={mf_td}", f"top={sc_date}", "BLOCK",
            f"top={sc_date} ≠ machine={mf_td}")
    else:
        add("mirror.trade_date", f"mf={mf_td}", f"top={sc_date}", "PASS", "")

    # H4 action_change
    sc_ac = sc.get("action_change", "")
    p0_ac = p0.get("action_change", "")
    mf_ac = sc.get("machine_fields", {}).get("action_change", "")
    ac_vals = [v for v in [sc_ac, p0_ac, mf_ac] if v]
    if len(set(ac_vals)) > 1:
        add("mirror.action_change", str(ac_vals), str((sc_ac, p0_ac, mf_ac)), "BLOCK",
            f"不一致: top={sc_ac}, p0={p0_ac}, mf={mf_ac}")
    else:
        add("mirror.action_change", str(ac_vals), str((sc_ac, p0_ac, mf_ac)), "PASS", "")

    # H5 p0_action (t1_action vs mf.p0_action)
    if sc_t1 and mf_rl:
        pass
    mf_p0 = sc.get("machine_fields", {}).get("p0_action", "")
    if sc_t1 and mf_p0:
        t1_dir = action_direction(sc_t1)
        p0_dir = action_direction(mf_p0)
        if action_conflict(t1_dir, p0_dir):
            add("mirror.p0_action", f"mf={mf_p0}", f"t1={sc_t1}", "BLOCK",
                f"t1_action='{sc_t1}' ≠ machine='{mf_p0}'")
        else:
            add("mirror.p0_action", f"mf={mf_p0}", f"t1={sc_t1}", "PASS", "")
    else:
        add("mirror.p0_action", f"mf={mf_p0}", f"t1={sc_t1}", "PASS", "")

    # H6 confidence
    mf_conf = sc.get("machine_fields", {}).get("confidence", "")
    if sc_conf_n and mf_conf:
        mf_conf_n = re.search(r'[高中低]', str(mf_conf))
        mc = mf_conf_n.group(0) if mf_conf_n else ""
        if sc_conf_n != mc:
            add("mirror.confidence", f"mf={mc}", f"p0={sc_conf_n}", "BLOCK",
                f"p0='{sc_conf_n}' ≠ machine='{mc}'")
        else:
            add("mirror.confidence", f"mf={mc}", f"p0={sc_conf_n}", "PASS", "")
    else:
        add("mirror.confidence", f"mf={mf_conf}", f"p0={sc_conf_n}", "PASS", "")

    # H7 risk_light
    if sc_rl and mf_rl and sc_rl != mf_rl:
        add("mirror.risk_light", f"mf={mf_rl}", f"top={sc_rl}", "BLOCK",
            f"top.risk_light='{sc_rl}' ≠ machine='{mf_rl}'")
    else:
        add("mirror.risk_light", f"mf={mf_rl}", f"top={sc_rl}", "PASS", "")

    return result


# ============================================================
# 输出
# ============================================================

def format_text(result):
    lines = []
    lines.append(f"{'='*60}")
    lines.append(f" {result['stock_name']}({result['stock_code']}) | {result['trade_date']}")
    lines.append(f"{'='*60}")
    lines.append(f"  总结果: {result['result']}")
    lines.append("")

    seen_block = []
    seen_warn = []
    seen_pass = []
    for chk in result.get("checks", []):
        icon = {"PASS": "✅", "WARN": "⚠️", "BLOCK": "❌"}.get(chk["result"], "❓")
        line = f"  {icon} {chk['field']}: {chk['result']}"
        if chk.get("md_value") is not None or chk.get("sidecar_value") is not None:
            mv = str(chk["md_value"])[:40] if chk["md_value"] is not None else ""
            sv = str(chk["sidecar_value"])[:40] if chk["sidecar_value"] is not None else ""
            line += f"  MD={mv} | SC={sv}"
        if chk.get("issue"):
            line += f"\n      → {chk['issue']}"
        (seen_block if chk["result"] == "BLOCK" else seen_warn if chk["result"] == "WARN" else seen_pass).append(line)

    for l in seen_block + seen_warn + seen_pass:
        lines.append(l)

    pass_c = len(seen_pass)
    warn_c = len(seen_warn)
    block_c = len(seen_block)
    lines.append(f"\n  明细: ✅PASS={pass_c} ⚠️WARN={warn_c} ❌BLOCK={block_c} / TOTAL={len(result['checks'])}")
    return "\n".join(lines) + "\n"


# ============================================================
# Main
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="P0-D: MD 与 sidecar JSON 一致性闸门"
    )
    parser.add_argument("--code", help="股票代码")
    parser.add_argument("--name", help="股票名称")
    parser.add_argument("--date", required=True, help="交易日期 YYYYMMDD 或 YYYY-MM-DD")
    parser.add_argument("--all", action="store_true", help="检查全部重点股票")
    parser.add_argument("--json", action="store_true", help="JSON 格式输出")
    args = parser.parse_args()

    stocks = []
    if args.all:
        stocks = get_stock_pool()
        if not stocks:
            stocks = get_stock_pool_from_reports()
        if not stocks:
            print("ERROR: 无法获取股票池", file=sys.stderr)
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

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        for r in results:
            print(format_text(r))
        pass_c = sum(1 for r in results if r["result"] == "PASS")
        block_c = sum(1 for r in results if r["result"] == "BLOCK")
        print(f"{'='*60}")
        print(f"  PASS: {pass_c} | BLOCK: {block_c} | TOTAL: {len(results)}")
        print(f"{'='*60}")

    return 0 if all_pass else 2


if __name__ == "__main__":
    sys.exit(main())
