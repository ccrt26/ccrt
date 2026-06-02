#!/usr/bin/env python3
"""backfill_returns.py — 后评估收益回填。

读取优先级: kline_cache/{code}.json → data_full.json KClose
交易日历: holidays_2026.csv (holiday+makeup)
基准收益: benchmark_data.py → index_kline/hs300.json → mark unavailable

用法:
    python3 backfill_returns.py                     # 回填所有缺失收益+signals
    python3 backfill_returns.py --date 20260531     # 仅回填指定日期
    python3 backfill_returns.py --dry-run           # 仅检查，不写入
    python3 backfill_returns.py --calendar-check --date 2026-05-22  # 日历自检

退出码: 0=正常 1=部分失败 2=数据不可用
Code level: L1
"""
import argparse
import csv
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = str(Path(__file__).resolve().parent.parent.parent)
DATA_DIR = os.path.join(ROOT, "代码文件", "数据")
SCORE_FILE = os.path.join(DATA_DIR, "score_history.jsonl")
DATA_FULL = os.path.join(DATA_DIR, "data_full.json")
KLINE_CACHE_DIR = os.path.join(DATA_DIR, "kline_cache")
HOLIDAY_FILE = os.path.join(ROOT, "每日荐股", "运营记录", "holidays_2026.csv")
RECORDS_DIR = os.path.join(ROOT, "每日荐股", "事后评估")
SUMMARY_FILE = os.path.join(RECORDS_DIR, "summary.csv")

sys.path.insert(0, DATA_DIR)
from benchmark_data import get_benchmark_return, get_sector_return

SIGNAL_RULES = [
    ("TECH_001", lambda r: (r.get("S_Tech") or 0) >= 15),
    ("TECH_007", lambda r: (r.get("S3_Volume") or 0) >= 3),
    ("MONEY_001", lambda r: (r.get("S_Money") or 0) >= 15),
    ("FUND_001", lambda r: (r.get("S_Fund") or 0) >= 10),
    ("FUND_002", lambda r: (r.get("S_Fund") or 0) >= 10 and (r.get("pe_ttm") or 50) < 30),
    ("RISK_003", lambda r: (r.get("S_Risk") or 0) <= 1),
]


def load_holidays():
    """加载交易日历。返回 (holidays_set, makeup_days_set)。"""
    holidays = set()
    makeup = set()
    if not os.path.exists(HOLIDAY_FILE):
        print("WARN: holidays_2026.csv 不存在，仅判断周末")
        return holidays, makeup
    try:
        with open(HOLIDAY_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = [p.strip() for p in line.split(",")]
                if len(parts) >= 2:
                    if parts[0] == "holiday":
                        holidays.add(parts[1])
                    elif parts[0] == "makeup":
                        makeup.add(parts[1])
    except OSError:
        pass
    print(f"交易日历已加载: {len(holidays)} holidays, {len(makeup)} makeup days")
    return holidays, makeup


def is_trading_day(d, holidays, makeup):
    """判断是否为交易日。周末+节假日=非交易日，调休补班=交易日。"""
    date_str = d.strftime("%Y-%m-%d") if isinstance(d, datetime) else d
    if isinstance(d, datetime):
        d = d
    else:
        d = datetime.strptime(date_str[:10], "%Y-%m-%d")

    if date_str in makeup:
        return True
    if d.weekday() >= 5:
        return False
    if date_str in holidays:
        return False
    return True


def count_trading_days(from_date, to_date, holidays, makeup):
    """精确计算两个日期之间的交易日数（不含from，含to）。"""
    if isinstance(from_date, str):
        from_date = datetime.strptime(from_date[:10], "%Y-%m-%d")
    if isinstance(to_date, str):
        to_date = datetime.strptime(to_date[:10], "%Y-%m-%d")

    count = 0
    d = from_date + timedelta(days=1)
    while d <= to_date:
        if is_trading_day(d, holidays, makeup):
            count += 1
        d += timedelta(days=1)
    return count


def get_trading_day_offset(base_date, offset, holidays, makeup):
    """获取base_date之后第N个交易日的日期。"""
    if isinstance(base_date, str):
        base_date = datetime.strptime(base_date[:10], "%Y-%m-%d")
    count = 0
    d = base_date + timedelta(days=1)
    while count < offset:
        if is_trading_day(d, holidays, makeup):
            count += 1
            if count == offset:
                return d
        d += timedelta(days=1)
        if (d - base_date).days > offset + 30:
            return None
    return None


def calendar_check(date_str):
    """交易日历自检：输出指定日期的T+1/T+3/T+5实际交易日。"""
    holidays, makeup = load_holidays()
    dt = datetime.strptime(date_str[:10], "%Y-%m-%d")

    print(f"\n交易日历自检: {date_str}")
    print(f"  holidays_2026.csv: {'已加载' if holidays else '未加载'}")
    print(f"  是否为交易日: {is_trading_day(dt, holidays, makeup)}")

    for offset in [1, 3, 5]:
        tgt = get_trading_day_offset(dt, offset, holidays, makeup)
        if tgt:
            skip_info = ""
            d = dt + timedelta(days=1)
            skipped = []
            while d <= tgt:
                if not is_trading_day(d, holidays, makeup):
                    reason = "周末" if d.weekday() >= 5 else "节假日"
                    skipped.append(f"{d.strftime('%m-%d')}({reason})")
                d += timedelta(days=1)
            if skipped:
                skip_info = f" (跳过: {', '.join(skipped)})"
            print(f"  T+{offset}: {tgt.strftime('%Y-%m-%d')} ({tgt.strftime('%A')}){skip_info}")
        else:
            print(f"  T+{offset}: 数据不足")


def load_score_history():
    records = []
    if not os.path.exists(SCORE_FILE):
        return records
    with open(SCORE_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return records


def save_score_history(records):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(SCORE_FILE, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def load_kline_from_cache(code):
    """Priority 1: 读取 kline_cache/{code}.json。"""
    fpath = os.path.join(KLINE_CACHE_DIR, f"{code}.json")
    if not os.path.exists(fpath):
        return None
    try:
        with open(fpath, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list) and len(data) > 0 and isinstance(data[0], dict) and "date" in data[0]:
            return data
    except (json.JSONDecodeError, OSError):
        pass
    return None


def load_kclose_from_data_full(code):
    """Priority 2 (降级): 从 data_full.json 读取KClose数组。返回 (closes, dates_or_None)。"""
    if not os.path.exists(DATA_FULL):
        return None, None
    try:
        with open(DATA_FULL, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None, None

    stocks = raw.get("Stocks", [])
    for s in stocks:
        if s.get("Code") == code:
            return s.get("KClose", []), None
    return None, None


def get_price_on_date_from_cache(kline_data, target_date_str):
    """从kline_cache数据中查找指定日期的close。"""
    for bar in kline_data:
        if bar.get("date") == target_date_str:
            return bar.get("close")
    return None


def compute_returns(record, kline_data_or_kclose, holidays, makeup):
    """计算ret_t1/ret_t3/ret_t5。

    支持两种数据源:
    - kline_cache格式 (list[dict] with date/close): 按日期精确查找
    - data_full KClose (list[float]): 按交易日偏移计算
    """
    date_str = record.get("date", "")[:10]
    price = record.get("price", 0)
    if not price or price == 0:
        return {}

    score_dt = datetime.strptime(date_str, "%Y-%m-%d")
    results = {}

    # Determine if we have kline_cache (with dates) or raw KClose
    is_kline_cache = (isinstance(kline_data_or_kclose, list) and len(kline_data_or_kclose) > 0
                      and isinstance(kline_data_or_kclose[0], dict) and "date" in kline_data_or_kclose[0])

    for period, offset in [("ret_t1", 1), ("ret_t3", 3), ("ret_t5", 5)]:
        if record.get(period) is not None:
            continue

        if is_kline_cache:
            tgt_date = get_trading_day_offset(score_dt, offset, holidays, makeup)
            if tgt_date:
                future_close = get_price_on_date_from_cache(
                    kline_data_or_kclose, tgt_date.strftime("%Y-%m-%d"))
            else:
                future_close = None
        else:
            # Raw KClose: need trading day count
            kclose = kline_data_or_kclose
            if not isinstance(kclose, list):
                continue
            n_days = count_trading_days(score_dt, datetime.now(), holidays, makeup)
            score_idx = -(n_days + 1) if n_days >= 0 else -1
            target_idx = score_idx + offset
            if target_idx > -1 or abs(target_idx) > len(kclose):
                continue
            future_close = kclose[target_idx]

        if future_close and future_close > 0:
            results[period] = round((future_close - price) / price * 100, 2)

    # Compute benchmark-relative returns
    date_compact = date_str.replace("-", "")
    existing_t1 = results.get("ret_t1") or record.get("ret_t1")
    if record.get("ret_t1_vs_hs300") is None:
        hs300_ret, hs300_src = get_benchmark_return("hs300", date_compact)
        if hs300_ret is not None and existing_t1 is not None:
            results["ret_t1_vs_hs300"] = round(existing_t1 - hs300_ret, 2)

    return results


def backfill_signals(records):
    updated = 0
    for i, rec in enumerate(records):
        if rec.get("signals"):
            continue
        sigs = []
        for sig_id, rule in SIGNAL_RULES:
            if rule(rec):
                sigs.append(sig_id)
        records[i]["signals"] = sigs
        if sigs:
            updated += 1
    return updated


def update_summary(records):
    os.makedirs(RECORDS_DIR, exist_ok=True)

    by_date = {}
    for rec in records:
        date_str = rec.get("date", "")[:10]
        if not date_str:
            continue
        if date_str not in by_date:
            by_date[date_str] = []
        by_date[date_str].append(rec)

    rows = []
    for date_str in sorted(by_date.keys()):
        day_recs = by_date[date_str]
        total = len(day_recs)
        wins = sum(1 for r in day_recs if (r.get("ret_t1") or 0) > 0)
        losses = sum(1 for r in day_recs if (r.get("ret_t1") or 0) < 0)
        win_rate = round(wins / total * 100, 1) if total > 0 else 0

        t1_vals = [r["ret_t1"] for r in day_recs if r.get("ret_t1") is not None]
        t3_vals = [r["ret_t3"] for r in day_recs if r.get("ret_t3") is not None]
        t5_vals = [r["ret_t5"] for r in day_recs if r.get("ret_t5") is not None]

        avg_t1 = round(sum(t1_vals) / len(t1_vals), 2) if t1_vals else 0
        avg_t3 = round(sum(t3_vals) / len(t3_vals), 2) if t3_vals else 0
        avg_t5 = round(sum(t5_vals) / len(t5_vals), 2) if t5_vals else 0

        t1_cov = round(len(t1_vals) / total * 100, 1) if total > 0 else 0
        t3_cov = round(len(t3_vals) / total * 100, 1) if total > 0 else 0
        t5_cov = round(len(t5_vals) / total * 100, 1) if total > 0 else 0

        date_compact = date_str.replace("-", "")
        hs300_ret, hs300_src = get_benchmark_return("hs300", date_compact)
        if hs300_ret is not None:
            excess = round(avg_t1 - hs300_ret, 2)
            hs300_str = str(hs300_ret) if hs300_src == "[2]" else f"{hs300_ret}(fallback)"
        else:
            excess = "N/A"
            hs300_str = "unavailable"

        rows.append({
            "period": date_str, "start_date": date_str, "end_date": date_str,
            "total_recommendations": total, "wins": wins, "losses": losses,
            "win_rate": win_rate, "total_profit": 0, "total_loss": 0,
            "profit_loss_ratio": 0, "portfolio_return": avg_t1,
            "hs300_return": hs300_str, "excess_return": excess,
            "avg_ret_t1": avg_t1, "avg_ret_t3": avg_t3, "avg_ret_t5": avg_t5,
            "t1_coverage": t1_cov, "t3_coverage": t3_cov, "t5_coverage": t5_cov,
        })

    fieldnames = [
        "period", "start_date", "end_date", "total_recommendations",
        "wins", "losses", "win_rate", "total_profit", "total_loss",
        "profit_loss_ratio", "portfolio_return", "hs300_return", "excess_return",
        "avg_ret_t1", "avg_ret_t3", "avg_ret_t5",
        "t1_coverage", "t3_coverage", "t5_coverage",
        "tech_misjudge_rate", "money_misjudge_rate", "sector_misjudge_rate",
        "news_misjudge_rate", "veto_kill_rate", "exemption_win_rate",
        "recommended_win_rate", "vetoed_win_rate", "market_win_rate",
        "veto_effectiveness", "score_distinction",
    ]

    with open(SUMMARY_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return rows


def update_records(records):
    os.makedirs(RECORDS_DIR, exist_ok=True)
    fieldnames = [
        "eval_date", "report_date", "stock_code", "stock_name",
        "total_score", "rating", "market_stage",
        "buy_price", "sell_price", "return_pct", "profit",
        "ret_t1", "ret_t3", "ret_t5",
        "ret_t1_vs_hs300", "ret_t3_vs_hs300", "ret_t5_vs_hs300",
        "ret_t1_vs_sector", "ret_t3_vs_sector", "ret_t5_vs_sector",
        "benchmark_source", "misjudge_dim", "misjudge_subtype",
        "tech_expected", "money_expected", "sector_expected", "news_expected",
        "veto_type", "exemption_flag", "volume_ratio",
        "bellwether_code", "bellwether_return", "notes",
    ]
    existing = {}
    records_file = os.path.join(RECORDS_DIR, "records.csv")
    if os.path.exists(records_file):
        try:
            with open(records_file, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    key = (row.get("report_date", ""), row.get("stock_code", ""))
                    existing[key] = row
        except (csv.Error, OSError):
            pass

    for rec in records:
        date_str = rec.get("date", "")[:10]
        code = rec.get("code", "")
        key = (date_str, code)
        if key not in existing:
            existing[key] = {
                "eval_date": date_str, "report_date": date_str,
                "stock_code": code, "stock_name": rec.get("name", ""),
                "total_score": rec.get("TotalScore", ""),
                "rating": "推荐" if rec.get("TotalScore", 0) >= 60 else "",
                "ret_t1": rec.get("ret_t1"), "ret_t3": rec.get("ret_t3"),
                "ret_t5": rec.get("ret_t5"),
                "ret_t1_vs_hs300": rec.get("ret_t1_vs_hs300"),
                "benchmark_source": "unavailable",
            }
        else:
            for fld in ["ret_t1", "ret_t3", "ret_t5", "ret_t1_vs_hs300"]:
                if rec.get(fld) is not None:
                    existing[key][fld] = rec[fld]

    with open(records_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in existing.values():
            writer.writerow(row)
    return list(existing.values())


def main():
    parser = argparse.ArgumentParser(description="后评估收益回填")
    parser.add_argument("--date", help="仅回填指定日期 YYYYMMDD")
    parser.add_argument("--dry-run", action="store_true", help="仅检查，不写入")
    parser.add_argument("--signals-only", action="store_true", help="仅回填signals")
    parser.add_argument("--calendar-check", action="store_true", help="交易日历自检")
    args = parser.parse_args()

    if args.calendar_check:
        date_str = args.date or datetime.now().strftime("%Y%m%d")
        if len(date_str) == 8:
            date_str = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"
        calendar_check(date_str)
        return 0

    holidays, makeup = load_holidays()
    records = load_score_history()
    if not records:
        print("ERROR: score_history.jsonl 为空或不可读")
        sys.exit(2)

    use_kline_cache = os.path.isdir(KLINE_CACHE_DIR) and os.listdir(KLINE_CACHE_DIR)
    print(f"K线数据源: {'kline_cache/ (优先)' if use_kline_cache else 'data_full.json (降级)'}")

    if not args.signals_only:
        total_backfilled = 0
        t3_count = 0
        t5_count = 0
        cache_used = 0
        full_used = 0

        for i, rec in enumerate(records):
            if args.date:
                rec_date = rec.get("date", "").replace("-", "")
                if not rec_date.startswith(args.date):
                    continue

            code = rec.get("code", "")

            kline_data = load_kline_from_cache(code)
            if kline_data:
                cache_used += 1
                updates = compute_returns(rec, kline_data, holidays, makeup)
            else:
                kclose, _ = load_kclose_from_data_full(code)
                if kclose:
                    full_used += 1
                    updates = compute_returns(rec, kclose, holidays, makeup)
                else:
                    continue

            if updates:
                for k, v in updates.items():
                    records[i][k] = v
                total_backfilled += len(updates)
                if updates.get("ret_t3") is not None:
                    t3_count += 1
                if updates.get("ret_t5") is not None:
                    t5_count += 1

        print(f"数据源: kline_cache={cache_used}条, data_full降级={full_used}条")
        print(f"回填字段总数: {total_backfilled}")
        print(f"ret_t3 回填: {t3_count}条, ret_t5 回填: {t5_count}条")
    else:
        total_backfilled = 0

    sigs_updated = backfill_signals(records)
    print(f"signals 注入: {sigs_updated}条有信号")

    if not args.dry_run:
        save_score_history(records)
        update_records(records)
        summary_rows = update_summary(records)
        print(f"records.csv 已更新, summary.csv 已更新 ({len(summary_rows)} 行)")
    else:
        print("[dry-run] 未写入")

    return 0


if __name__ == "__main__":
    sys.exit(main())
