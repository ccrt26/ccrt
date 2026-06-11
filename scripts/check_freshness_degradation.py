#!/usr/bin/env python3
"""
P0-C: 日期新鲜度与降级路径闸门 — 检查日报数据日期与数据契约新鲜度规则的一致性。

检查维度:
  A. K线 — trade_date 当日记录必须存在
  B. 四档资金 — fund_flow 日期与 trade_date 一致
  C. 融资 — 允许 T+1 延迟，需声明
  D. 板块相位 — 来源可追溯
  E. Baseline — 有效期内
  F. Eval_hooks — 日期不早于 trade_date/next_trade_date

用法:
  python3 scripts/check_freshness_degradation.py --code 600114 --name 东睦股份 --date 20260602
  python3 scripts/check_freshness_degradation.py --all --date 20260602
  python3 scripts/check_freshness_degradation.py --code 600114 --name 东睦股份 --date 20260602 --json

退出码:
  0 = PASS (所有检查通过)
  1 = 脚本异常
  2 = 任一 BLOCK

G. (仅在 --tier l2/all 时) Kline L2 新鲜度 — Phase 2 前 SKIP/WARN 不阻断
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, date, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = PROJECT_ROOT / "重点股票" / "股票报告"
KLINE_DIR = PROJECT_ROOT / "代码文件" / "数据" / "kline_cache"
FUND_FLOW_DIR = PROJECT_ROOT / "代码文件" / "数据" / "fund_flow_cache"
MARGIN_DIR = PROJECT_ROOT / "代码文件" / "数据" / "tushare" / "margin_detail"
DATA_SCORED_PATH = PROJECT_ROOT / "代码文件" / "数据" / "data_scored.json"
REGISTRY_PATH = PROJECT_ROOT / "00_项目地基" / "02_权威注册表" / "baseline_registry.json"
PIGEON_CONFIG = PROJECT_ROOT / "代码文件" / "信鸽信息采集" / "pigeon_config.json"


# ============================================================
# 辅助函数
# ============================================================

def load_json(path):
    with open(path, "r", encoding="utf-8-sig") as f:
        return json.load(f)


def load_text(path):
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="ignore")


def parse_date_flex(date_str):
    """灵活解析日期。支持: YYYYMMDD, YYYY-MM-DD, M/D, M月D日 等。
    返回 (date, "YYYYMMDD") 或 (None, None)"""
    if not date_str:
        return None, None
    s = str(date_str).strip()
    # YYYY-MM-DD
    m = re.match(r'^(\d{4})-(\d{1,2})-(\d{1,2})$', s)
    if m:
        d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        return d, d.strftime("%Y%m%d")
    # YYYYMMDD
    if re.match(r'^\d{8}$', s):
        d = datetime.strptime(s, "%Y%m%d").date()
        return d, s
    # M/D or M/D前 etc
    m = re.match(r'(\d{1,2})/(\d{1,2})', s)
    if m:
        # Infer year from context near trade_date - will use external year
        return ("M/D", f"{int(m.group(1)):02d}{int(m.group(2)):02d}")
    # M月D日
    m = re.search(r'(\d{1,2})月(\d{1,2})日', s)
    if m:
        return ("M/D", f"{int(m.group(1)):02d}{int(m.group(2)):02d}")
    return None, None


def date_compact_to_dashed(d):
    if len(d) == 8:
        return f"{d[:4]}-{d[4:6]}-{d[6:8]}"
    return d


def compact_date(date_str):
    """标准化为 8 位紧凑格式"""
    return date_str.replace("-", "")


def make_check(field, source_path, source_date, trade_date, allowed_lag,
               freshness, degraded, sidecar_claim, md_claim, result, issue):
    return {
        "field": field,
        "source_path": source_path,
        "source_date": source_date,
        "trade_date": trade_date,
        "allowed_lag": allowed_lag,
        "freshness": freshness,
        "degraded": degraded,
        "sidecar_claim": sidecar_claim,
        "md_claim": md_claim,
        "result": result,
        "issue": issue,
    }


# ============================================================
# 股票池
# ============================================================

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


# ============================================================
# 数据发现
# ============================================================

def find_report_file(code, name, date_compact, ext):
    subdir = REPORT_DIR / f"{name}({code})"
    return subdir / f"{name}({code})日报_{date_compact}{ext}"


# ============================================================
# A. K线新鲜度
# ============================================================

def check_kline_freshness(sidecar, md_text, kline_row, kline_path, td, trade_date_str):
    """K线必须有 trade_date 当日记录"""
    field = "kline.freshness"
    source_date = td.strftime("%Y%m%d") if kline_row else None
    has_data = kline_row is not None

    # Check sidecar claim
    sidecar_claim = None
    if sidecar:
        delta = sidecar.get("delta", {})
        if delta.get("close") is not None:
            sidecar_claim = "当日K线数据存在"

    # Check MD today's market table
    md_claim = None
    if md_text:
        # Look for trade_date in MD's kline table
        td_dashed = td.strftime("%Y-%m-%d")
        if td_dashed in md_text:
            md_claim = f"行情表含{td_dashed}"
        td_cn = f"{td.month}月{td.day}日"
        if td_cn in md_text:
            md_claim = md_claim or f"行情表含{td_cn}"

    if not has_data:
        return make_check(field, kline_path, source_date, trade_date_str, "T+0",
                          "stale", False, sidecar_claim, md_claim, "BLOCK",
                          f"K线源无{trade_date_str}当日数据, source_path={kline_path}")

    # Check if sidecar has delta.close but kline doesn't exist
    if sidecar_claim and not has_data:
        return make_check(field, kline_path, source_date, trade_date_str, "T+0",
                          "stale", False, sidecar_claim, md_claim, "BLOCK",
                          "sidecar 有当日K线数据但 kline_cache 无记录")

    return make_check(field, kline_path, source_date, trade_date_str, "T+0",
                      "当日", False, sidecar_claim, md_claim, "PASS", "")


# ============================================================
# G. Kline L2 新鲜度（仅 --tier l2/all 时）
# ============================================================

def check_kline_l2(trade_date_str, td, code):
    """检查 kline_l2 规则状态。enabled=false 或 phase=2 时 SKIP/WARN，不 BLOCK。"""
    field = "kline_l2.freshness"
    FRESHNESS_RULES_PATH = PROJECT_ROOT / "00_项目地基" / "04_一致性闸门" / "freshness_rules.json"

    if not FRESHNESS_RULES_PATH.exists():
        return make_check(field, str(FRESHNESS_RULES_PATH), None, trade_date_str,
                          "T+1", "规则文件缺失", False, None, None, "WARN",
                          "freshness_rules.json 不存在，无法检查 L2 规则")

    try:
        rules = load_json(FRESHNESS_RULES_PATH)
        kl2 = rules.get("rules", {}).get("kline_l2", {})
    except Exception as e:
        return make_check(field, str(FRESHNESS_RULES_PATH), None, trade_date_str,
                          "T+1", "规则解析失败", False, None, None, "WARN",
                          f"freshness_rules.json 解析失败: {e}")

    enabled = kl2.get("enabled", False)
    phase = kl2.get("phase", 0)

    if not enabled or phase < 2:
        return make_check(field, f"kline_l2 enabled={enabled} phase={phase}",
                          None, trade_date_str, "T+1",
                          "SKIP (Phase 2 前不检查)", False, None, None, "PASS",
                          f"kline_l2 enabled={enabled} phase={phase} — Phase 2 前跳过 L2 新鲜度检查")

    # Phase 2 已启用，检查 L2 DB 是否有当日数据
    L2_DB_PATH = PROJECT_ROOT / "代码文件" / "数据" / "l2_cache" / "l2_cache.db"
    if not L2_DB_PATH.exists():
        return make_check(field, str(L2_DB_PATH), None, trade_date_str,
                          "T+1", "L2 DB 不存在", False, None, None, "WARN",
                          "L2 SQLite 不存在，无法检查 L2 K 线新鲜度")

    try:
        conn = __import__("sqlite3").connect(str(L2_DB_PATH))
        td_dashed = td.strftime("%Y-%m-%d")
        row = conn.execute(
            "SELECT COUNT(*) FROM kline WHERE code=? AND trade_date=?",
            (code, td_dashed)
        ).fetchone()
        conn.close()
        has_l2_data = row and row[0] > 0
    except Exception as e:
        return make_check(field, str(L2_DB_PATH), None, trade_date_str,
                          "T+1", "L2 查询失败", False, None, None, "WARN",
                          f"L2 DB 查询失败: {e}")

    if has_l2_data:
        return make_check(field, str(L2_DB_PATH), td_dashed, trade_date_str,
                          "T+1", "L2 有当日记录", False, None, None, "PASS", "")
    else:
        return make_check(field, str(L2_DB_PATH), None, trade_date_str,
                          "T+1", "L2 无当日记录", False, None, None, "WARN",
                          f"L2 kline 无 {td_dashed} 记录，以 L1 为准")


# ============================================================
# B. 四档资金新鲜度
# ============================================================

def check_fund_flow_freshness(sidecar, md_text, ff_row, ff_path, td, trade_date_str, degraded_items):
    """检查资金数据日期是否与 trade_date 一致"""
    field = "fund_flow.freshness"
    source_date = ff_row.get("date", "") if ff_row else None
    has_data = ff_row is not None
    is_degraded = "fund_flow" in str(degraded_items) if degraded_items else False

    # Parse sidecar claim
    sidecar_claim = None
    if sidecar:
        ff = sidecar.get("fund_flow_4level", {})
        source_text = ff.get("source", "")
        freshness_text = ff.get("freshness", "")
        if source_text:
            sidecar_claim = f"source={source_text}, freshness={freshness_text}"
        else:
            sidecar_claim = f"freshness={freshness_text}" if freshness_text else None

    # Parse MD fund flow claim
    md_claim = None
    if md_text:
        # MD says "6/2 Tushare实时数据" or similar
        m = re.search(r'(?:6/\d+|当日|今日|实时|Tushare)', md_text)
        if m:
            md_claim = m.group(0)[:50]

    # 从 sidecar source 字段解析日期并与 trade_date 比对
    # 支持格式: 6/2, 6月2日, 20260602, 2026-06-02
    source_mismatch = False
    source_date_str = str(source_date) if source_date else ""
    trade_md = f"{td.month}/{td.day}"
    trade_ymd = td.strftime("%Y%m%d")

    if sidecar_claim:
        has_onsite_claim = any(word in sidecar_claim for word in ["当日", "实时"])
        # 检查 source 文本中是否包含 "当日/实时" 但与实际日期冲突
        if has_onsite_claim and source_date_str and source_date_str != trade_ymd:
            source_mismatch = True
        # 检查 source 文本中 M/D 格式日期是否与 trade_date 匹配
        elif trade_md in sidecar_claim:
            pass  # source 日期匹配
        # 检查 sidecar source 中是否有 YYYYMMDD 格式日期且匹配
        elif trade_ymd in sidecar_claim:
            pass  # source 日期匹配
        # 既不是当日声明、也没发现匹配日期 → 检查权威源日期
        elif not has_onsite_claim and source_date_str and source_date_str != trade_ymd:
            source_mismatch = True

    errs = []
    if not has_data and not is_degraded:
        errs.append("资金缓存无当日记录且未声明降级")
    elif not has_data and is_degraded:
        return make_check(field, ff_path, source_date, trade_date_str, "T+0",
                          "缺失", True, sidecar_claim, md_claim, "WARN",
                          "资金数据缺失，但已声明降级")

    if source_mismatch:
        errs.append(f"source日期={source_date} ≠ trade_date={trade_date_str}")

    if errs:
        return make_check(field, ff_path, source_date, trade_date_str, "T+0",
                          "stale", is_degraded, sidecar_claim, md_claim, "BLOCK", "; ".join(errs))

    freshness_text = "当日" if not source_mismatch and has_data else "stale"
    return make_check(field, ff_path, source_date, trade_date_str, "T+0",
                      freshness_text, is_degraded, sidecar_claim, md_claim, "PASS", "")


# ============================================================
# C. 融资新鲜度
# ============================================================

def check_margin_freshness(sidecar, md_text, margin_row, margin_path, td, trade_date_str, degraded_items):
    """融资允许 T+1，但需声明"""
    field = "margin.freshness"
    is_degraded = "margin" in str(degraded_items) if degraded_items else False

    if not margin_row:
        source_date = None
        return make_check(field, margin_path, source_date, trade_date_str, "T+1",
                          "缺失", is_degraded, None, None, "WARN",
                          "融资数据不存在或为空")

    source_date = margin_row.get("trade_date", "")
    source_d = datetime.strptime(source_date, "%Y%m%d").date() if source_date and len(str(source_date)) == 8 else None

    # Check MD claim
    md_claim = None
    if md_text:
        m = re.search(r'最新日期[：:]*(\d{8})', md_text)
        if m:
            md_date = m.group(1)
            md_claim = f"最新日期{md_date}"
        elif "融资T+1延迟" in md_text:
            md_claim = "声明T+1延迟"
        elif "融资" in md_text and ("T+1" in md_text or "最新" in md_text):
            pass  # will be captured above

    # Check sidecar degraded
    sidecar_claim = None
    if sidecar and is_degraded:
        sidecar_claim = f"声明降级: margin(T+1延迟)"

    # Check for "当日融资" or "实时融资" claim when data is not trade_date
    strong_claim = False
    if md_text:
        if re.search(r'当日融资|实时融资|融资当日', md_text):
            strong_claim = True
    if sidecar:
        pass  # sidecar doesn't usually claim "当日融资"

    if strong_claim and source_d and source_d < td:
        return make_check(field, margin_path, source_date, trade_date_str, "T+1",
                          "stale", is_degraded, sidecar_claim, md_claim, "BLOCK",
                          f"MD声称'当日融资'但最新数据日期={source_date} < trade_date={trade_date_str}")

    # If degraded (T+1) properly declared, it's fine
    if is_degraded and source_d:
        lag = (td - source_d).days
        if lag <= 1:
            return make_check(field, margin_path, source_date, trade_date_str, "T+1",
                              f"T+{lag}", True, sidecar_claim, md_claim, "PASS", "")
        else:
            return make_check(field, margin_path, source_date, trade_date_str, "T+1",
                              f"T+{lag}", True, sidecar_claim, md_claim, "WARN",
                              f"融资延迟{lag}天已声明")

    if source_d:
        lag = (td - source_d).days
        # ⛔ 融资超允许延迟(2天)且未声明降级、MD也未提最新日期 → BLOCK
        if lag > 2 and not is_degraded:
            has_md_date = False
            if md_text:
                if re.search(r'最新日期|T\+1|延迟|融资.*\d{8}', md_text):
                    has_md_date = True
            if not has_md_date:
                return make_check(field, margin_path, source_date, trade_date_str, "T+1",
                                  f"T+{lag}", is_degraded, sidecar_claim, md_claim, "BLOCK",
                                  f"融资延迟{lag}天但未声明降级或最新日期")
        return make_check(field, margin_path, source_date, trade_date_str, "T+1",
                          f"T+{lag}" if lag > 0 else "当日", is_degraded, sidecar_claim, md_claim, "PASS", "")

    return make_check(field, margin_path, source_date, trade_date_str, "T+1",
                      "未知", is_degraded, sidecar_claim, md_claim, "WARN", "融资日期格式无法识别")


# ============================================================
# D. 板块相位新鲜度
# ============================================================

def check_sector_freshness(sidecar, md_text, sector_data, sector_path, td, trade_date_str):
    """板块相位需来源可追溯"""
    field = "sector_phase.freshness"
    has_sector_data = sector_data is not None
    sidecar_phase = sidecar.get("sector_phase", {}).get("phase") if sidecar else None

    md_claim = None
    if md_text:
        md_phase = extract_md_sector_phase(md_text)
        if md_phase:
            md_claim = f"相位={md_phase}"
        if "data_scored最新数据" in md_text:
            md_claim = (md_claim or "") + " data_scored"

    sidecar_claim = sidecar_phase

    if not has_sector_data:
        if sidecar_phase:
            return make_check(field, sector_path, None, trade_date_str, "N/A",
                              "无来源", False, sidecar_claim, md_claim, "WARN",
                              "data_scored 无该股票相位，但报告有相位判断")
        return make_check(field, sector_path, None, trade_date_str, "N/A",
                          "无来源", False, sidecar_claim, md_claim, "PASS",
                          "data_scored 无该股票相位，报告也未使用")

    # Check if sidecar phase is "待确认" or similar
    if sidecar_phase in ("待确认", "待更新", ""):
        return make_check(field, sector_path, trade_date_str, trade_date_str, "N/A",
                          "待确认", False, sidecar_claim, md_claim, "WARN",
                          f"sidecar 板块相位为'{sidecar_phase}'，未确定")

    return make_check(field, sector_path, trade_date_str, trade_date_str, "N/A",
                      "data_scored", False, sidecar_claim, md_claim, "PASS", "")


def extract_md_sector_phase(md_text):
    clean = md_text.replace("**", "")
    phase_kw = r'(见底期|启动期|主升期|高潮期|退潮期|主升调整|衰退期|潜伏期|震荡期|筑底期|主跌期|反弹期|调整期)'
    patterns = [
        rf'相位[：:]\s*{phase_kw}',
        rf'当前相位[：:]\s*{phase_kw}',
        rf'板块相位[：:]*\s*{phase_kw}',
    ]
    for pat in patterns:
        m = re.search(pat, clean)
        if m:
            return m.group(1)
    return None


# ============================================================
# E. Baseline 有效期
# ============================================================

def check_baseline_freshness(registry, code, td, trade_date_str):
    """检查 baseline 是否在有效期内"""
    field = "baseline.validity"
    matched = []
    for entry in registry.get("entries", []):
        if entry.get("stock_code") != code:
            continue
        bdate_s = entry.get("baseline_date", "")
        vuntil_s = entry.get("valid_until", "")
        try:
            bd = datetime.strptime(bdate_s, "%Y-%m-%d").date() if bdate_s else None
            vu = datetime.strptime(vuntil_s, "%Y-%m-%d").date() if vuntil_s else None
        except ValueError:
            continue
        if bd and bd > td:
            continue
        if vu and vu < td:
            continue
        matched.append(entry)

    if len(matched) == 0:
        return make_check(field, str(REGISTRY_PATH), None, trade_date_str, "N/A",
                          "无有效基线", False, None, None, "BLOCK",
                          f"注册表中 {trade_date_str} 无有效基线")
    if len(matched) > 1:
        ids = [e["baseline_id"] for e in matched]
        return make_check(field, str(REGISTRY_PATH), None, trade_date_str, "N/A",
                          "多基线冲突", False, None, None, "BLOCK",
                          f"注册表中有 {len(matched)} 条有效基线: {ids}")

    bl = matched[0]
    return make_check(field, str(REGISTRY_PATH), bl["baseline_date"], trade_date_str,
                      f"直到{bl['valid_until']}", f"基线{bl['baseline_id']}", False,
                      None, None, "PASS", "")


# ============================================================
# F. Eval_hooks 日期
# ============================================================

def check_eval_hooks_dates(sidecar, td, next_trade_date_str, trade_date_str):
    """检查 eval_hooks 中的日期不早于 trade_date/next_trade_date"""
    field = "eval_hooks.dates"
    if not sidecar:
        return make_check(field, "sidecar", None, trade_date_str, "N/A",
                          "未知", False, None, None, "PASS", "sidecar 不存在")

    eh = sidecar.get("eval_hooks", {})
    if not eh:
        return make_check(field, "sidecar.eval_hooks", None, trade_date_str, "N/A",
                          "无eval_hooks", False, None, None, "PASS", "")

    # Parse t1_verify and t5_verify
    t1_raw = eh.get("t1_verify", "")
    t5_raw = eh.get("t5_verify", "")

    # Extract M/D dates from the text
    def extract_md_date(text):
        if not isinstance(text, str):
            return None
        m = re.search(r'(\d{1,2})/(\d{1,2})', text)
        if m:
            month = int(m.group(1))
            day = int(m.group(2))
            # Use trade_date year to construct date
            year = td.year
            return date(year, month, day)
        m = re.search(r'(\d{1,2})月(\d{1,2})日', text)
        if m:
            return date(td.year, int(m.group(1)), int(m.group(2)))
        m = re.search(r'(\d{8})', text)
        if m:
            d = datetime.strptime(m.group(1), "%Y%m%d").date()
            return d
        m = re.search(r'(\d{4}-\d{2}-\d{2})', text)
        if m:
            d = datetime.strptime(m.group(1), "%Y-%m-%d").date()
            return d
        return None

    t1_date = extract_md_date(t1_raw) if t1_raw else None
    t5_date = extract_md_date(t5_raw) if t5_raw else None

    # Determine next_trade_date
    ntd = None
    if next_trade_date_str:
        ntd = parse_date_flex(next_trade_date_str)[0]

    errs = []

    # T+1 date must be >= next_trade_date (or >= trade_date if no next_trade_date)
    if t1_date:
        if t1_date < td:
            errs.append(f"t1_verify日期 {t1_date} 早于 trade_date {td}")
        elif ntd and t1_date < ntd:
            errs.append(f"t1_verify日期 {t1_date} 早于 next_trade_date {ntd}，应不早于{ntd}")

    if t5_date:
        if t5_date <= td:
            errs.append(f"t5_verify日期 {t5_date} 不晚于 trade_date {td}")
        elif ntd and t5_date < ntd:
            errs.append(f"t5_verify日期 {t5_date} 早于 next_trade_date {ntd}")

    if not t1_date and t1_raw:
        errs.append("t1_verify 存在但日期格式无法解析")
    if not t5_date and t5_raw:
        errs.append("t5_verify 存在但日期格式无法解析")

    if errs:
        has_block = any("不晚于" in e or "早于" in e for e in errs)
        return make_check(field, "sidecar.eval_hooks", str(t1_date or t5_date or ""),
                          trade_date_str, "T+1≥trade_date",
                          "日期异常", False, str(t1_raw)[:60], str(t5_raw)[:60],
                          "BLOCK" if has_block else "WARN", "; ".join(errs))

    t1_str = t1_date.strftime("%m/%d") if t1_date else "N/A"
    t5_str = t5_date.strftime("%m/%d") if t5_date else "N/A"
    return make_check(field, "sidecar.eval_hooks", f"t1={t1_str} t5={t5_str}",
                      trade_date_str, "N/A", "合理", False,
                      str(t1_raw)[:60], str(t5_raw)[:60], "PASS", "")


# ============================================================
# 核心检查逻辑
# ============================================================

def check_one(code, name, trade_date_str, registry, tier="l1"):
    result = {
        "stock_code": code,
        "stock_name": name,
        "trade_date": trade_date_str,
        "result": "PASS",
        "checks": [],
    }

    date_compact = trade_date_str.replace("-", "")
    try:
        td = datetime.strptime(date_compact, "%Y%m%d").date()
    except ValueError as e:
        return add_general_block(result, f"日期格式错误: {e}")

    # 加载报告
    sidecar_path = find_report_file(code, name, date_compact, ".json")
    md_path = find_report_file(code, name, date_compact, ".md")

    if not sidecar_path.exists():
        return add_general_block(result, f"sidecar 不存在: {sidecar_path}")
    if not md_path.exists():
        return add_general_block(result, f"MD 不存在: {md_path}")

    try:
        sidecar = load_json(sidecar_path)
    except Exception as e:
        return add_general_block(result, f"sidecar JSON解析失败: {e}")
    md_text = load_text(md_path)

    degraded_items = sidecar.get("degraded_items") or []
    next_trade_date_str = sidecar.get("next_trade_date", "")

    # A. K线新鲜度 — 优先kline_cache, 兜底data_full.json
    kline_row = None
    kline_path = str(KLINE_DIR / f"{code}.json")
    td_dashed = td.strftime("%Y-%m-%d")
    if (KLINE_DIR / f"{code}.json").exists():
        try:
            for row in load_json(KLINE_DIR / f"{code}.json"):
                if row.get("date") == td_dashed:
                    kline_row = row
                    break
        except Exception:
            pass
    if not kline_row:
        # Fallback to data_full.json
        data_full_path = PROJECT_ROOT / "代码文件" / "数据" / "data_full.json"
        if data_full_path.exists():
            try:
                dfull = load_json(data_full_path)
                for s in dfull.get("Stocks", []) or []:
                    c = str(s.get("Code") or s.get("code") or "")
                    if c != code:
                        continue
                    kdates = s.get("KDate") or []
                    if td_dashed in kdates:
                        idx = kdates.index(td_dashed)
                        kline_row = {
                            "date": td_dashed,
                            "open": s.get("KOpen", [None] * len(kdates))[idx] if idx < len(s.get("KOpen", [])) else None,
                            "high": s.get("KHigh", [None] * len(kdates))[idx] if idx < len(s.get("KHigh", [])) else None,
                            "low": s.get("KLow", [None] * len(kdates))[idx] if idx < len(s.get("KLow", [])) else None,
                            "close": s.get("KClose", [None] * len(kdates))[idx] if idx < len(s.get("KClose", [])) else None,
                            "volume": s.get("KVolume", [None] * len(kdates))[idx] if idx < len(s.get("KVolume", [])) else None,
                            "change_pct": s.get("ChangePct"),
                            "_source": str(data_full_path),
                        }
                        kline_path = str(data_full_path)
                        break
            except Exception:
                pass

    chk = check_kline_freshness(sidecar, md_text, kline_row, kline_path, td, trade_date_str)
    result["checks"].append(chk)
    if chk["result"] == "BLOCK": result["result"] = "BLOCK"

    # B. 四档资金新鲜度
    ff_row = None
    ff_path = str(FUND_FLOW_DIR / f"{code}.json")
    td_ymd = td.strftime("%Y%m%d")
    td_md = f"{td.month}/{td.day}"
    if (FUND_FLOW_DIR / f"{code}.json").exists():
        try:
            for row in load_json(FUND_FLOW_DIR / f"{code}.json"):
                if str(row.get("date", "")) == td_ymd:
                    ff_row = row
                    break
        except Exception:
            pass
    if not ff_row:
        # Fallback to data_full.json.FundFlows
        data_full_path = PROJECT_ROOT / "代码文件" / "数据" / "data_full.json"
        if data_full_path.exists():
            try:
                dfull = load_json(data_full_path)
                flows = dfull.get("FundFlows", {}).get(code, [])
                if flows:
                    for row in flows:
                        d = str(row.get("trade_date") or row.get("date", "")).replace("-", "")
                        if d == td_ymd:
                            def to_f(v): return round(float(v or 0), 2)
                            ff_row = {
                                "date": td_ymd,
                                "super_large_net": round(to_f(row.get("buy_elg_amount", 0)) - to_f(row.get("sell_elg_amount", 0)), 2),
                                "large_net": round(to_f(row.get("buy_lg_amount", 0)) - to_f(row.get("sell_lg_amount", 0)), 2),
                                "medium_net": round(to_f(row.get("buy_md_amount", 0)) - to_f(row.get("sell_md_amount", 0)), 2),
                                "small_net": round(to_f(row.get("buy_sm_amount", 0)) - to_f(row.get("sell_sm_amount", 0)), 2),
                                "main_force_net": round(to_f(row.get("net_mf_amount", 0)), 2),
                                "_source": str(data_full_path),
                            }
                            ff_path = str(data_full_path)
                            break
            except Exception:
                pass

    chk = check_fund_flow_freshness(sidecar, md_text, ff_row, ff_path, td, trade_date_str, degraded_items)
    result["checks"].append(chk)
    if chk["result"] == "BLOCK": result["result"] = "BLOCK"

    # C. 融资新鲜度
    margin_row = None
    margin_path = str(MARGIN_DIR / f"{code}.json")
    if (MARGIN_DIR / f"{code}.json").exists():
        try:
            rows = load_json(MARGIN_DIR / f"{code}.json")
            if rows:
                margin_row = rows[0]
        except Exception:
            pass

    chk = check_margin_freshness(sidecar, md_text, margin_row, margin_path, td, trade_date_str, degraded_items)
    result["checks"].append(chk)
    if chk["result"] == "BLOCK": result["result"] = "BLOCK"

    # D. 板块相位
    sector_data = None
    sector_path = str(DATA_SCORED_PATH)
    if DATA_SCORED_PATH.exists():
        try:
            d = load_json(DATA_SCORED_PATH)
            code_str = str(code)
            for bucket in ["Recommendations", "AllStocks", "VetoedStocks"]:
                for item in d.get(bucket, []):
                    if str(item.get("Code", "")) == code_str:
                        sector_data = item
                        break
        except Exception:
            pass

    chk = check_sector_freshness(sidecar, md_text, sector_data, sector_path, td, trade_date_str)
    result["checks"].append(chk)
    if chk["result"] == "BLOCK": result["result"] = "BLOCK"

    # E. Baseline 有效期
    chk = check_baseline_freshness(registry, code, td, trade_date_str)
    result["checks"].append(chk)
    if chk["result"] == "BLOCK": result["result"] = "BLOCK"

    # F. Eval_hooks 日期
    chk = check_eval_hooks_dates(sidecar, td, next_trade_date_str, trade_date_str)
    result["checks"].append(chk)
    if chk["result"] == "BLOCK": result["result"] = "BLOCK"

    # G. Kline L2 新鲜度（仅 --tier l2/all 时）
    if tier in ("l2", "all"):
        chk = check_kline_l2(trade_date_str, td, code)
        result["checks"].append(chk)
        # L2 检查不升级为 BLOCK（Phase 2 前不阻断当日报告）
        if chk["result"] == "BLOCK":
            chk["result"] = "WARN"

    return result


def add_general_block(result, issue):
    result["result"] = "BLOCK"
    result["checks"].append(make_check("general", "", None, result["trade_date"],
                                        None, "error", False, None, None, "BLOCK", issue))
    return result


# ============================================================
# 输出格式化
# ============================================================

def format_text_result(result):
    lines = []
    lines.append(f"{'='*60}")
    lines.append(f" {result['stock_name']}({result['stock_code']}) | {result['trade_date']}")
    lines.append(f"{'='*60}")
    lines.append(f"  总结果: {result['result']}")
    lines.append("")

    for chk in result.get("checks", []):
        icon = {"PASS": "✅", "WARN": "⚠️", "BLOCK": "❌"}.get(chk["result"], "❓")
        lines.append(f"  {icon} {chk['field']}: {chk['result']}")
        sc = chk.get("source_date") or "N/A"
        td = chk.get("trade_date") or "N/A"
        lines.append(f"     来源日期={sc} | trade_date={td} | lag={chk.get('allowed_lag','N/A')} | freshness={chk.get('freshness','N/A')} | degraded={chk.get('degraded','N/A')}")
        if chk.get("sidecar_claim") or chk.get("md_claim"):
            lines.append(f"     sidecar声明={chk['sidecar_claim'] or 'N/A'} | MD声明={chk['md_claim'] or 'N/A'}")
        if chk.get("issue"):
            lines.append(f"     问题: {chk['issue']}")

    pass_c = sum(1 for c in result["checks"] if c["result"] == "PASS")
    warn_c = sum(1 for c in result["checks"] if c["result"] == "WARN")
    block_c = sum(1 for c in result["checks"] if c["result"] == "BLOCK")
    lines.append(f"\n  明细: ✅PASS={pass_c} ⚠️WARN={warn_c} ❌BLOCK={block_c} / TOTAL={len(result['checks'])}")
    return "\n".join(lines) + "\n"


# ============================================================
# Main
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="P0-C: 日期新鲜度与降级路径闸门"
    )
    parser.add_argument("--code", help="股票代码")
    parser.add_argument("--name", help="股票名称")
    parser.add_argument("--date", required=True, help="交易日期 YYYYMMDD 或 YYYY-MM-DD")
    parser.add_argument("--all", action="store_true", help="检查全部重点股票")
    parser.add_argument("--json", action="store_true", help="JSON 格式输出")
    parser.add_argument("--tier", choices=["l1", "l2", "all"], default="l1",
                        help="检查层级: l1(默认)仅L1, l2仅L2, all=L1+L2。Phase 2 前 L2 检查不 BLOCK")
    args = parser.parse_args()

    # 加载注册表
    if not REGISTRY_PATH.exists():
        print(f"ERROR: 注册表文件不存在: {REGISTRY_PATH}")
        print("请先运行 python3 scripts/check_baseline_authority.py --rebuild-registry")
        return 1
    registry = load_json(REGISTRY_PATH)

    # 股票池
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
        res = check_one(code, name, args.date, registry, tier=args.tier)
        results.append(res)
        if res["result"] == "BLOCK":
            all_pass = False

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        for r in results:
            print(format_text_result(r))
        pass_c = sum(1 for r in results if r["result"] == "PASS")
        block_c = sum(1 for r in results if r["result"] == "BLOCK")
        print(f"{'='*60}")
        print(f"  PASS: {pass_c} | BLOCK: {block_c} | TOTAL: {len(results)}")
        print(f"{'='*60}")

    return 0 if all_pass else 2


if __name__ == "__main__":
    sys.exit(main())
