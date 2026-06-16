#!/usr/bin/env python3
"""generate_baseline.py — 从score_history+data_full+tushare生成重点股票周度深度基线JSON。

用法:
    python3 generate_baseline.py                          # 生成全量
    python3 generate_baseline.py --code 600114            # 单只
    python3 generate_baseline.py --date 2026-05-30        # 指定基线日期

基线路径: 重点股票/基线/{名称}({code})_baseline_{YYYYWW}.json
Code level: L1
"""
import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = str(Path(__file__).resolve().parent.parent.parent)
DATA_DIR = os.path.join(ROOT, "代码文件", "数据")
SCORE_FILE = os.path.join(DATA_DIR, "score_history.jsonl")
TUSHARE_DIR = os.path.join(DATA_DIR, "tushare")
BASELINE_DIR = os.path.join(ROOT, "重点股票", "基线")
HOLIDAY_FILE = os.path.join(ROOT, "每日荐股", "运营记录", "holidays_2026.csv")

SIGNAL_THRESHOLDS = [
    ("TECH_001", lambda r: (r.get("S_Tech") or 0) >= 8),
    ("TECH_007", lambda r: (r.get("S3_Volume") or 0) >= 2),
    ("MONEY_001", lambda r: (r.get("S_Money") or 0) >= 8),
    ("FUND_001", lambda r: (r.get("S_Fund") or 0) >= 6),
    ("FUND_002", lambda r: (r.get("S_Fund") or 0) >= 6 and (r.get("pe_ttm") or 50) < 30),
    ("RISK_003", lambda r: (r.get("S_Risk") or 0) <= 2),
]


def load_holidays():
    holidays = set()
    if not os.path.exists(HOLIDAY_FILE):
        return holidays
    try:
        with open(HOLIDAY_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = [p.strip() for p in line.split(",")]
                if len(parts) >= 2 and parts[0] == "holiday":
                    holidays.add(parts[1])
    except OSError:
        pass
    return holidays


def next_friday(date_str):
    """Return the FOLLOWING Friday (if already Friday, go to next week)."""
    dt = datetime.strptime(date_str[:10], "%Y-%m-%d")
    dt += timedelta(days=1)  # always advance at least 1 day
    while dt.weekday() != 4:
        dt += timedelta(days=1)
    return dt.strftime("%Y-%m-%d")


def prev_trading_day_before_friday(date_str, holidays):
    """Return the last trading day before the next Friday. Guarantees > baseline_date."""
    bd = datetime.strptime(date_str[:10], "%Y-%m-%d")
    nf = datetime.strptime(next_friday(date_str), "%Y-%m-%d")
    target = nf - timedelta(days=1)
    while target.weekday() >= 5 or target.strftime("%Y-%m-%d") in holidays:
        target -= timedelta(days=1)
    # Ensure valid_until > baseline_date
    if target <= bd:
        target = bd + timedelta(days=1)
        while target.weekday() >= 5 or target.strftime("%Y-%m-%d") in holidays:
            target += timedelta(days=1)
    return target.strftime("%Y-%m-%d")


def get_week_number(date_str):
    dt = datetime.strptime(date_str[:10], "%Y-%m-%d")
    return f"{dt.year}W{dt.isocalendar()[1]:02d}"


def load_tushare_data(data_type, code):
    """Load tushare data for a specific stock."""
    fpath = os.path.join(TUSHARE_DIR, data_type, f"{code}.json")
    if not os.path.exists(fpath):
        return None
    try:
        with open(fpath, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def extract_pledge_info(code):
    """Extract latest pledge ratio from tushare."""
    data = load_tushare_data("pledge", code)
    if not data or not isinstance(data, list):
        return None, "unavailable", f"tushare/pledge/{code}.json 不存在或为空"
    active = [d for d in data if not d.get("is_release") or d.get("is_release") != "1"]
    if not active:
        return 0, "[3]-tushare", f"无活跃质押"
    total_pledge = sum(float(d.get("pledge_amount", 0) or 0) for d in active)
    return round(total_pledge / 10000, 2), "[3]-tushare", f"{len(active)}笔活跃质押"


def extract_unlock_info(code):
    """Extract upcoming share unlock info."""
    data = load_tushare_data("share_float", code)
    if not data or not isinstance(data, list):
        return None, "unavailable", f"tushare/share_float/{code}.json 不存在"
    today = datetime.now()
    upcoming = []
    for d in data:
        fd = d.get("float_date", "")
        if fd and fd >= today.strftime("%Y%m%d"):
            upcoming.append({
                "date": fd,
                "ratio": d.get("float_ratio", 0),
                "holder": d.get("holder_name", ""),
            })
    if upcoming:
        total_ratio = sum(u["ratio"] for u in upcoming)
        return round(total_ratio * 100, 2), "[3]-tushare", f"{len(upcoming)}笔待解禁, 合计{total_ratio*100:.1f}%"
    return 0, "[3]-tushare", "近期无解禁"


def extract_holder_info(code):
    """Extract latest holder number change."""
    data = load_tushare_data("holder_number", code)
    if not data or not isinstance(data, list) or len(data) < 2:
        return None, "unavailable", f"tushare/holder_number/{code}.json 不足2期"
    latest = data[0]
    prev = data[1]
    try:
        latest_num = float(latest.get("holder_num", 0) or 0)
        prev_num = float(prev.get("holder_num", 0) or 0)
        if prev_num > 0:
            change_pct = round((latest_num - prev_num) / prev_num * 100, 1)
            return change_pct, "[3]-tushare", f"股东人数变化{change_pct:+.1f}%"
    except (ValueError, TypeError):
        pass
    return None, "unavailable", "数据解析失败"


def extract_forecast_info(code):
    """Extract latest earnings forecast."""
    data = load_tushare_data("forecast", code)
    if not data or not isinstance(data, list):
        return None, "unavailable", f"tushare/forecast/{code}.json 不存在"
    latest = data[0]
    ftype = latest.get("type", "")
    return ftype, "[3]-tushare", f"业绩预告类型: {ftype}"


def extract_margin_info(code):
    """Extract latest margin detail trend."""
    data = load_tushare_data("margin_detail", code)
    if not data or not isinstance(data, list):
        return None, "unavailable", f"tushare/margin_detail/{code}.json 不存在"
    return f"{len(data)}条记录", "[12]-tushare", "融资融券数据可用"


def extract_northbound_info(code):
    """Extract latest northbound holding."""
    data = load_tushare_data("hk_hold", code)
    if not data or not isinstance(data, list):
        return None, "unavailable", f"tushare/hk_hold/{code}.json 不存在"
    latest = data[0]
    ratio = latest.get("ratio", None)
    return ratio, "[8]-tushare", f"北向持股比例: {ratio}%" if ratio else "北向数据可用"


def load_latest_scores():
    by_code = {}
    if not os.path.exists(SCORE_FILE):
        return by_code
    with open(SCORE_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            code = r.get("code", "")
            if code not in by_code or r.get("date", "") > by_code[code].get("date", ""):
                by_code[code] = r
    return by_code


def build_baseline(rec, holidays):
    code = rec.get("code", "")
    name = rec.get("name", code)
    date_str = rec.get("date", "")[:10]
    week = get_week_number(date_str)
    baseline_id = f"{code}_W{week}"
    friday = next_friday(date_str)
    valid_until = prev_trading_day_before_friday(date_str, holidays)

    signals = [sid for sid, rule in SIGNAL_THRESHOLDS if rule(rec)]
    price = rec.get("price", 0) or 0

    # Risk data from tushare
    pledge_val, pledge_src, pledge_note = extract_pledge_info(code)
    unlock_val, unlock_src, unlock_note = extract_unlock_info(code)
    holder_val, holder_src, holder_note = extract_holder_info(code)
    forecast_val, forecast_src, forecast_note = extract_forecast_info(code)
    margin_val, margin_src, margin_note = extract_margin_info(code)
    nb_val, nb_src, nb_note = extract_northbound_info(code)

    # Determine risk level
    risk_score = 0
    if pledge_val and isinstance(pledge_val, (int, float)) and pledge_val > 30:
        risk_score += 2
    if unlock_val and isinstance(unlock_val, (int, float)) and unlock_val > 5:
        risk_score += 2
    if holder_val and isinstance(holder_val, (int, float)) and holder_val > 20:
        risk_score += 1
    if forecast_val and forecast_val in ("略减", "预减", "首亏", "续亏"):
        risk_score += 3
    risk_level = "low" if risk_score <= 1 else "medium" if risk_score <= 3 else "high" if risk_score <= 5 else "critical"

    is_fri = datetime.strptime(date_str[:10], "%Y-%m-%d").weekday() == 4
    return {
        "baseline_id": baseline_id,
        "baseline_version": "v1",
        "baseline_status": "official" if is_fri else "provisional",
        "provisional_reason": ("" if is_fri else f"baseline_date={date_str[:10]}非周五，作为临时基线。正式基线待周五深度分析生成。"),
        "stock_code": code,
        "stock_name": name,
        "baseline_date": date_str,
        "valid_until": valid_until,
        "next_deep_analysis_date": friday,
        "generated_from": "score_history.jsonl + data_full.json + tushare",
        "approved_by": "腰子(待签)",
        "strategy_version": "v1.0",

        "core_thesis": (
            f"评分{rec.get('TotalScore','?')}分(T{rec.get('S_Tech','?')}/M{rec.get('S_Money','?')}"
            f"/F{rec.get('S_Fund','?')})，风险等级{risk_level}"
        ),

        "key_support_price": round(price * 0.90, 2) if price else None,
        "key_pressure_price": round(price * 1.10, 2) if price else None,
        "stop_loss_price": round(price * 0.88, 2) if price else None,
        "target_price": round(price * 1.15, 2) if price else None,

        "valuation_status": {
            "pe_ttm": rec.get("pe_ttm"),
            "pb": rec.get("pb"),
            "assessment": "undervalued" if (rec.get("pe_ttm") or 99) < 20 else ("overvalued" if (rec.get("pe_ttm") or 0) > 60 else "fair"),
        },

        "technical_status": {
            "trend": "up" if (rec.get("S_Tech", 0) or 0) >= 15 else ("down" if (rec.get("S_Tech", 0) or 0) <= 6 else "sideways"),
            "ma_status": "多头" if (rec.get("S1_MA") or 0) >= 4 else "纠缠",
            "macd_signal": "金叉" if (rec.get("S6_MACD") or 0) >= 1 else "偏弱",
            "volume_assessment": "放量" if (rec.get("S3_Volume") or 0) >= 3 else "正常",
        },

        "moneyflow_status": {
            "main_force_direction": "inflow" if (rec.get("S_Money") or 0) >= 12 else ("outflow" if (rec.get("S_Money") or 0) <= 5 else "neutral"),
            "northbound_trend": str(nb_val) if nb_val else nb_note,
            "margin_trend": str(margin_val) if margin_val else margin_note,
        },

        "risk_flags": {
            "pledge_ratio": pledge_val,
            "pledge_note": pledge_note,
            "pledge_source": pledge_src,
            "pledge_risk": "high" if (isinstance(pledge_val, (int, float)) and pledge_val > 30) else "low",
            "unlock_ratio": unlock_val,
            "unlock_note": unlock_note,
            "unlock_source": unlock_src,
            "unlock_risk": "high" if (isinstance(unlock_val, (int, float)) and unlock_val > 5) else "low",
            "holder_change_pct": holder_val,
            "holder_note": holder_note,
            "holder_source": holder_src,
            "forecast_type": forecast_val,
            "forecast_note": forecast_note,
            "forecast_source": forecast_src,
            "forecast_risk": "high" if (forecast_val and forecast_val in ("略减","预减","首亏","续亏")) else "low",
            "margin_status": margin_val,
            "margin_note": margin_note,
            "margin_source": margin_src,
            "northbound_ratio": nb_val,
            "northbound_note": nb_note,
            "northbound_source": nb_src,
            "overall_risk_level": risk_level,
        },

        "counter_evidence": [
            f"跌破支撑{round(price*0.90,2)}元，原判断减弱",
            f"主力资金连续3日净流出，原判断需重评",
            f"板块相位转入衰退期，降低置信度",
            "季报数据恶化触发估值重评",
            "触发质押/解禁风险升级",
        ],

        "trigger_signals": signals if signals else ["TECH_007"],

        "decision_impact": {
            "scoring_fields": ["S_Tech", "S_Money", "S_Fund", "TotalScore"],
            "veto_fields": ["veto_status"] if rec.get("veto_status") not in (None, "passed", "") else [],
            "downgrade_fields": ["S_Risk", "pledge_risk", "unlock_risk"],
            "position_fields": ["TotalScore", "risk_level"],
            "stop_loss_fields": ["key_support_price", "stop_loss_price"],
        },

        "data_snapshot": {
            "price": rec.get("price"),
            "change_pct": rec.get("change_pct"),
            "total_score": rec.get("TotalScore"),
            "S_Tech": rec.get("S_Tech"),
            "S_Money": rec.get("S_Money"),
            "S_Fund": rec.get("S_Fund"),
            "S_Risk": rec.get("S_Risk"),
        },

        "source_report_path": f"重点股票/股票报告/{name}({code})/",
        "data_sources": ["[1]", "[2]", "[3]", "[5]", "[8]", "[12]", "score_history", "tushare"],
    }


def main():
    parser = argparse.ArgumentParser(description="周度基线生成")
    parser.add_argument("--code", help="仅生成指定股票")
    parser.add_argument("--date", help="指定基线日期 YYYY-MM-DD")
    args = parser.parse_args()

    holidays = load_holidays()
    scores = load_latest_scores()
    if not scores:
        print("ERROR: score_history.jsonl 为空")
        sys.exit(1)

    os.makedirs(BASELINE_DIR, exist_ok=True)
    generated = 0

    for code, rec in sorted(scores.items()):
        if args.code and code != args.code:
            continue

        if args.date:
            rec = dict(rec)
            rec["date"] = args.date[:10]

        baseline = build_baseline(rec, holidays)
        week = get_week_number(rec.get("date", ""))
        fname = f"{rec.get('name', code)}({code})_baseline_{week}.json"
        fpath = os.path.join(BASELINE_DIR, fname)

        with open(fpath, "w", encoding="utf-8") as f:
            json.dump(baseline, f, ensure_ascii=False, indent=2)

        # Summary
        rf = baseline["risk_flags"]
        risk_ok = sum(1 for v in [rf.get("pledge_ratio"), rf.get("unlock_ratio"),
                                   rf.get("holder_change_pct"), rf.get("forecast_type")]
                       if v is not None and v != "unavailable")
        print(f"  {fname}: valid_until={baseline['valid_until']}, "
              f"risk={risk_ok}/4, signals={baseline['trigger_signals']}")
        generated += 1

    print(f"\n基线已生成: {generated} 只 → {BASELINE_DIR}/")


if __name__ == "__main__":
    main()
