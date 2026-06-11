#!/usr/bin/env python3
# ⚠️ SPLIT_PENDING (2026-05-29): 504行超500行红线，待情墨拆分评审。
#    建议: 模式处理(daily/deep/pigeon/health)/健康检查/故障告警分离为独立模块。
"""daily_orchestrator.py — 每日调度统一入口

三层架构中的L1计算层：交易日检测→数据就绪检查→信号文件→日志。
不依赖Claude Code，由crontab触发。所有确定性计算在此完成，
AI分析环节通过信号文件交由Claude Code处理。

用法:
    python3 代码文件/tools/daily_orchestrator.py --mode daily        # 日报模式(15:37)
    python3 代码文件/tools/daily_orchestrator.py --mode deep         # 深度分析模式(周五20:30)
    python3 代码文件/tools/daily_orchestrator.py --mode pigeon       # 信鸽采集模式(19:00)
    python3 代码文件/tools/daily_orchestrator.py --mode health       # 数据就绪检查

退出码:
    0 — 正常完成(含跳过/非交易日)
    1 — 数据未就绪(已超最大重试)
    2 — 脚本错误

Code level: L1
Design: 审计报告/架构设计/design_scheduling_separation_v1.0.md
"""
import argparse
import csv
import json
import os
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = str(Path(__file__).resolve().parent.parent.parent)
# Ensure 代码文件/数据 is in path for fault_events import
_DATA_DIR = os.path.join(ROOT, "代码文件", "数据")
if _DATA_DIR not in sys.path:
    sys.path.insert(0, _DATA_DIR)
TZ_SHANGHAI = timezone(timedelta(hours=8))
LOCK_DIR = os.path.join(ROOT, "每日荐股", "运营记录", ".locks")
LOG_DIR = os.path.join(ROOT, "每日荐股", "运营记录")
SIGNAL_DIR = os.path.join(ROOT, ".claude")
HOLIDAY_FILE = os.path.join(ROOT, "每日荐股", "运营记录", "holidays_2026.csv")

# Data readiness: sample stocks from pigeon_config (loaded dynamically)
DATA_CACHE_DIR = os.path.join(ROOT, "代码文件", "数据")
EVENTS_DB = os.path.join(ROOT, "重点股票", "消息面数据", "events_db.json")

MAX_RETRIES = 4
RETRY_DELAY = 900  # 15 minutes
LOCK_TIMEOUT = 3600  # 1 hour


def ensure_dirs():
    os.makedirs(LOCK_DIR, exist_ok=True)
    os.makedirs(LOG_DIR, exist_ok=True)
    os.makedirs(SIGNAL_DIR, exist_ok=True)


def log(msg, level="INFO"):
    timestamp = datetime.now(TZ_SHANGHAI).strftime("%Y-%m-%d %H:%M:%S")
    today = datetime.now(TZ_SHANGHAI).strftime("%Y%m%d")
    log_file = os.path.join(LOG_DIR, f"orchestrator_{today}.log")
    line = f"[{timestamp}][{level}] {msg}"
    print(line)
    try:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def acquire_lock(name):
    lock_file = os.path.join(LOCK_DIR, f"{name}.lock")
    if os.path.exists(lock_file):
        try:
            mtime = os.path.getmtime(lock_file)
            age = time.time() - mtime
            if age < LOCK_TIMEOUT:
                log(f"Lock exists (age={age:.0f}s), another instance running", "SKIP")
                return False
            log(f"Stale lock (age={age:.0f}s), removing", "WARN")
            os.remove(lock_file)
        except OSError:
            return False
    try:
        with open(lock_file, "w") as f:
            f.write(f"pid={os.getpid()}\ntimestamp={datetime.now(TZ_SHANGHAI).isoformat()}")
        return True
    except OSError:
        return False


def release_lock(name):
    lock_file = os.path.join(LOCK_DIR, f"{name}.lock")
    try:
        os.remove(lock_file)
    except OSError:
        pass


def is_trading_day(date_str=None):
    """Check if date_str (YYYYMMDD) is an A-share trading day."""
    if date_str is None:
        date_str = datetime.now(TZ_SHANGHAI).strftime("%Y%m%d")

    dt = datetime.strptime(date_str, "%Y%m%d")
    # Weekend check
    if dt.weekday() >= 5:
        log(f"{date_str} is weekend (day={dt.weekday()}), skip", "SKIP")
        return False

    # Holiday check
    if os.path.exists(HOLIDAY_FILE):
        try:
            with open(HOLIDAY_FILE, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    holiday_date = row.get("Date", "").strip()
                    if holiday_date == date_str:
                        reason = row.get("Reason", "未知")
                        log(f"{date_str} is holiday: {reason}, skip", "SKIP")
                        return False
        except (csv.Error, OSError) as e:
            log(f"Holiday file read error: {e}, assuming trading day", "WARN")
            return True
    return True


def check_data_readiness():
    """Check if closing data is available for sample stocks.

    Uses file-based freshness: checks if the data cache directory
    contains files modified today after 15:00 CST.
    Returns (ready: bool, detail: str).
    """
    now = datetime.now(TZ_SHANGHAI)
    today_str = now.strftime("%Y%m%d")

    # Check if market is closed yet
    if now.hour < 15 or (now.hour == 15 and now.minute < 5):
        return False, f"Market not yet closed (current: {now.strftime('%H:%M')})"

    # File-based check: look for data files modified today after 15:00
    if not os.path.isdir(DATA_CACHE_DIR):
        return False, f"Data cache dir not found: {DATA_CACHE_DIR}"

    cutoff = now.replace(hour=15, minute=0, second=0, microsecond=0).timestamp()
    fresh_count = 0
    checked_files = []

    for entry in sorted(os.listdir(DATA_CACHE_DIR)):
        fpath = os.path.join(DATA_CACHE_DIR, entry)
        if not os.path.isfile(fpath):
            continue
        if entry.startswith("."):
            continue
        mtime = os.path.getmtime(fpath)
        if mtime >= cutoff:
            fresh_count += 1
            checked_files.append(entry)
            if fresh_count >= 3:
                break

    if fresh_count >= 3:
        return True, f"{fresh_count} cache files updated today after 15:00"
    return False, f"Only {fresh_count} cache files updated today (need >=3)"



def _load_pigeon_stock_pool():
    """统一从pigeon_config.json读取股票池。返回 {ok, source, codes, name_map, error}"""
    result = {"ok": False, "source": "pigeon_config.json", "codes": [], "name_map": {}, "error": None}
    cfg_path = os.path.join(ROOT, "代码文件", "信鸽信息采集", "pigeon_config.json")
    if not os.path.exists(cfg_path):
        result["error"] = f"pigeon_config.json not found: {cfg_path}"
        return result
    try:
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        stocks = cfg.get("target_stocks", [])
        if not stocks:
            result["error"] = "target_stocks empty"
            return result
        codes = []
        name_map = {}
        for s in stocks:
            code = str(s.get("code") or "")
            name = s.get("name") or ""
            if code:
                codes.append(code)
                if name:
                    name_map[code] = name
        result["ok"] = True
        result["codes"] = codes
        result["name_map"] = name_map
        return result
    except Exception as e:
        result["error"] = str(e)
        return result


def check_v36_data_readiness(target_date=None):
    """v3.6日报数据就绪检查——按pigeon_config逐只检查。
    返回 (status: str, detail: dict)
    target_date: 目标交易日，支持 YYYYMMDD 或 YYYY-MM-DD，默认今天
    """
    if target_date is None:
        date_dash = datetime.now(TZ_SHANGHAI).strftime('%Y-%m-%d')
        date_compact = date_dash.replace('-', '')
    elif '-' in target_date:
        date_dash = target_date
        date_compact = target_date.replace('-', '')
    else:
        date_compact = target_date
        date_dash = f'{target_date[:4]}-{target_date[4:6]}-{target_date[6:8]}'

    # Check manifest for data collection completion timestamp
    manifest_path = os.path.join(DATA_CACHE_DIR, "tushare", "manifest.json")
    manifest_meta = {}
    manifest_degraded_override = None  # None=no override, False=no change, True=force degrade
    if os.path.exists(manifest_path):
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                mf = json.load(f)
            manifest_meta["exists"] = True
            # Support both updated and updated_at, prefer updated
            raw_ts = mf.get("updated") or mf.get("updated_at") or ""
            manifest_meta["updated"] = raw_ts
            if raw_ts:
                # Normalize to YYYYMMDD for comparison
                ts_str = str(raw_ts).replace("-", "")
                if "T" in ts_str:
                    ts_str = ts_str.split("T")[0]  # 20260603 before T
                elif " " in ts_str:
                    ts_str = ts_str.split(" ")[0]
                # Take first 8 digits
                mf_date = ts_str[:8] if len(ts_str) >= 8 else ts_str
                if mf_date < date_compact:
                    manifest_meta["degraded"] = True
                    manifest_meta["reason"] = f"manifest updated {mf_date} < target {date_compact}"
                    manifest_degraded_override = True
                else:
                    manifest_meta["degraded"] = False
            else:
                manifest_meta["degraded"] = True
                manifest_meta["reason"] = "manifest updated/updated_at 均为空"
                manifest_degraded_override = True
        except Exception as e:
            manifest_meta["exists"] = True
            manifest_meta["degraded"] = True
            manifest_meta["reason"] = f"manifest 解析失败: {e}"
            manifest_degraded_override = True
    else:
        manifest_meta["exists"] = False
        manifest_meta["degraded"] = True
        manifest_meta["reason"] = "manifest.json 不存在"
        manifest_degraded_override = True

    # Read stock pool from pigeon_config (single source of truth)
    pool_result = _load_pigeon_stock_pool()
    if not pool_result.get("ok"):
        return "BLOCK", {"stock_pool_source": "pigeon_config.json",
                          "stock_pool_status": "missing_or_empty",
                          "error": pool_result.get("error", "unknown"),
                          "manifest": manifest_meta}

    pool_codes = pool_result["codes"]

    kline_dir = os.path.join(DATA_CACHE_DIR, "kline_cache")
    fund_dir = os.path.join(DATA_CACHE_DIR, "fund_flow_cache")
    margin_dir = os.path.join(DATA_CACHE_DIR, "tushare", "margin_detail")

    kline_by_stock = {}
    fund_flow_by_stock = {}
    margin_by_stock = {}
    baseline_by_stock = {}
    sector_by_stock = {}

    # Preload data_full.json for K-line fallback
    data_full_stocks = {}
    data_full_path = os.path.join(DATA_CACHE_DIR, "data_full.json")
    try:
        with open(data_full_path, "r", encoding="utf-8-sig") as f:
            dfull = json.load(f)
        for s in dfull.get("Stocks", []) or []:
            c = str(s.get("Code") or s.get("code") or "")
            if c:
                data_full_stocks[c] = s
    except Exception:
        data_full_stocks = {}

    for code in pool_codes:
        # Kline — check kline_cache first, then fallback to data_full.json
        kf = os.path.join(kline_dir, f"{code}.json")
        kline_match = False
        kline_date = None
        if os.path.exists(kf):
            try:
                with open(kf, "r", encoding="utf-8") as f:
                    kd = json.load(f)
                if isinstance(kd, list) and kd:
                    latest = str(kd[-1].get('date', '')).replace("-", "")
                    if len(latest) >= 8:
                        kline_date = latest[:8]
                        kline_match = kline_date == date_compact
            except Exception:
                pass
        if not kline_match:
            # Fallback to data_full.json
            s = data_full_stocks.get(code) or {}
            kd_list = s.get("KDate") or []
            if kd_list:
                latest2 = str(kd_list[-1]).replace("-", "")
                if len(latest2) >= 8:
                    kline_date = latest2[:8]
                    kline_match = kline_date == date_compact
        kline_by_stock[code] = {'date': kline_date, 'match': kline_match}

        # Fund flow
        ff = os.path.join(fund_dir, f"{code}.json")
        if os.path.exists(ff):
            try:
                with open(ff, "r", encoding="utf-8") as f:
                    ff_data = json.load(f)
                fund_flow_by_stock[code] = {'exists': True, 'records': len(ff_data) if isinstance(ff_data, list) else 1}
            except Exception:
                fund_flow_by_stock[code] = {'exists': True, 'error': True}
        else:
            fund_flow_by_stock[code] = {'exists': False}

        # Margin
        mg = os.path.join(margin_dir, f"{code}.json")
        if code == "300736":
            margin_by_stock[code] = {'exists': False, 'missing_allowed': True}
        elif os.path.exists(mg):
            try:
                with open(mg, "r", encoding="utf-8") as f:
                    mg_data = json.load(f)
                margin_by_stock[code] = {'exists': True, 'records': len(mg_data) if isinstance(mg_data, list) else 1}
            except Exception:
                margin_by_stock[code] = {'exists': True, 'error': True}
        else:
            margin_by_stock[code] = {'exists': False}

        # Baseline — report_dir first, then 基线
        bl_found = False
        report_dir = os.path.join(ROOT, "重点股票", "股票报告")
        if os.path.isdir(report_dir):
            for d in os.listdir(report_dir):
                if code in d:
                    bl_dir = os.path.join(report_dir, d)
                    if os.path.isdir(bl_dir):
                        for fname in os.listdir(bl_dir):
                            if "baseline" in fname.lower() and fname.endswith(".json"):
                                bl_found = True
                                break
                if bl_found:
                    break
        if not bl_found:
            bl_dir2 = os.path.join(ROOT, "重点股票", "基线")
            if os.path.isdir(bl_dir2):
                for fname in os.listdir(bl_dir2):
                    if code in fname and "baseline" in fname.lower() and fname.endswith(".json"):
                        bl_found = True
                        break
        baseline_by_stock[code] = {'found': bl_found}

        # Sector
        scored_file = os.path.join(DATA_CACHE_DIR, "data_scored.json")
        sector_found = False
        if os.path.exists(scored_file):
            try:
                with open(scored_file, "r", encoding="utf-8-sig") as f:
                    scored = json.load(f)
                for bucket in ("AllStocks", "Recommendations", "VetoedStocks"):
                    for s in scored.get(bucket, []) or []:
                        if str(s.get("Code") or s.get("code")) == code:
                            if s.get("SectorPhase"):
                                sector_found = True
                            break
            except Exception:
                pass
        sector_by_stock[code] = {'found': sector_found}

    # Aggregate
    kline_ok = sum(1 for v in kline_by_stock.values() if v.get('match'))
    kline_total = len(kline_by_stock) if kline_by_stock else len(pool_result.get("codes", []))
    fund_ok = sum(1 for v in fund_flow_by_stock.values() if v.get('exists'))
    margin_ok = sum(1 for v in margin_by_stock.values() if v.get('exists') or v.get('missing_allowed'))
    baseline_ok = sum(1 for v in baseline_by_stock.values() if v.get('found'))
    sector_ok = sum(1 for v in sector_by_stock.values() if v.get('found'))

    detail = {
        "stock_pool_source": pool_result.get("source"),
        "stock_pool_codes": pool_result.get("codes", []),
        "stock_pool_count": len(pool_result.get("codes", [])),
        "pigeon_ok": pool_result.get("ok", False),
        "stock_pool_status": pool_result.get("ok") if pool_result.get("ok") else "ok",
        'ready': kline_ok + fund_ok + margin_ok + baseline_ok + sector_ok,
        'total': kline_total * 5,
        'kline_by_stock': kline_by_stock,
        'baseline_by_stock': baseline_by_stock,
        'fund_flow_by_stock': fund_flow_by_stock,
        'margin_by_stock': margin_by_stock,
        'sector_by_stock': sector_by_stock,
        'kline_match': f'{kline_ok}/{kline_total}',
        'fund_flow_avail': f'{fund_ok}/{kline_total}',
        'margin_avail': f'{margin_ok}/{kline_total}',
        'baseline_avail': f'{baseline_ok}/{kline_total}',
        'sector_avail': f'{sector_ok}/{kline_total}',
        'manifest': manifest_meta,
    }

    # BLOCK if kline < 8/10 or baseline < 5/10
    if kline_ok < 8 or baseline_ok < 5:
        status = 'BLOCK'
    elif kline_ok < 10 or fund_ok < 8:
        status = 'WARN'
    else:
        status = 'READY'

    # 第5.9-FIX: manifest 状态覆盖 status 判定
    # missing/empty/parse_error → BLOCK
    if manifest_degraded_override is True and not manifest_meta.get("reason", ""):
        # defensive: reason should exist
        pass
    if manifest_degraded_override is True:
        # manifest 缺失/空/失效 → BLOCK
        if not manifest_meta.get("updated"):
            if status in ('READY', 'WARN'):
                status = 'BLOCK'
        else:
            # manifest 日期早于 target → WARN（不降级到 BLOCK）
            if status == 'READY':
                status = 'WARN'

    return status, detail

def write_signal(signal_type, data):
    """Write a signal file for Claude Code to pick up."""
    signal_file = os.path.join(SIGNAL_DIR, f"signal_{signal_type}.json")
    payload = {
        "signal": signal_type,
        "timestamp": datetime.now(TZ_SHANGHAI).isoformat(),
        "data_ready": True,
        **data,
    }
    try:
        with open(signal_file, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        log(f"Signal written: {signal_file}")
    except OSError as e:
        log(f"Failed to write signal: {e}", "ERROR")





def _load_baseline_for_stock(code):
    """Load baseline from report_dir or基线 dir."""
    report_dir = os.path.join(ROOT, "重点股票", "股票报告")
    if os.path.isdir(report_dir):
        for d in os.listdir(report_dir):
            if code in d:
                bl_dir = os.path.join(report_dir, d)
                if os.path.isdir(bl_dir):
                    for fname in sorted(os.listdir(bl_dir), reverse=True):
                        if "baseline" in fname.lower() and fname.endswith(".json"):
                            try:
                                with open(os.path.join(bl_dir, fname), "r", encoding="utf-8") as f:
                                    return json.load(f)
                            except Exception:
                                pass
    bl_dir = os.path.join(ROOT, "重点股票", "基线")
    if os.path.isdir(bl_dir):
        for fname in sorted(os.listdir(bl_dir), reverse=True):
            if code in fname and "baseline" in fname.lower() and fname.endswith(".json"):
                try:
                    with open(os.path.join(bl_dir, fname), "r", encoding="utf-8") as f:
                        return json.load(f)
                except Exception:
                    pass
    return None


def _load_fund_flow_for_stock(code, target_date=None):
    """Load latest fund flow from single-stock cache. 规范化5项字段。
    优先 fund_flow_cache, 兜底 data_full.json.FundFlows (支持 raw Tushare 格式映射)。"""
    # 1. Try fund_flow_cache
    ff_file = os.path.join(DATA_CACHE_DIR, "fund_flow_cache", f"{code}.json")
    if os.path.exists(ff_file):
        try:
            with open(ff_file, "r", encoding="utf-8") as f:
                rows = json.load(f)
            raw = None
            if target_date and isinstance(rows, list):
                for r in rows:
                    d = str(r.get("date", "")).replace("-", "")
                    if d == target_date:
                        raw = r
                        break
            if not raw:
                raw = rows[-1] if isinstance(rows, list) and rows else rows
            if raw:
                raw["source_trace"] = "Tushare Pro moneyflow"
                fields = ["super_large_net", "large_net", "medium_net", "small_net", "main_force_net"]
                for fld in fields:
                    if fld not in raw:
                        raw[fld] = 0
                    disp_fld = fld.replace("_net", "_display")
                    if disp_fld not in raw:
                        val = raw.get(fld, 0)
                        try:
                            raw[disp_fld] = f"{val:+.0f}万"
                        except (ValueError, TypeError):
                            raw[disp_fld] = "0万"
                return raw
        except Exception:
            pass

    # 2. Fallback to data_full.json.FundFlows
    df_path = os.path.join(DATA_CACHE_DIR, "data_full.json")
    if os.path.exists(df_path):
        try:
            with open(df_path, "r", encoding="utf-8-sig") as f:
                dfull = json.load(f)
            flows = dfull.get("FundFlows", {}).get(code, [])
            if not flows:
                return None
            # Find matching trade_date
            match = None
            for row in flows:
                d = str(row.get("trade_date") or row.get("date", "")).replace("-", "")
                if target_date and d == target_date:
                    match = row
                    break
            if not match:
                return None
            # Map raw Tushare fields → standard 5-field format
            def to_f(v):
                return round(float(v or 0), 2)
            super_large = round(to_f(match.get("buy_elg_amount", 0)) - to_f(match.get("sell_elg_amount", 0)), 2)
            large_net = round(to_f(match.get("buy_lg_amount", 0)) - to_f(match.get("sell_lg_amount", 0)), 2)
            medium_net = round(to_f(match.get("buy_md_amount", 0)) - to_f(match.get("sell_md_amount", 0)), 2)
            small_net = round(to_f(match.get("buy_sm_amount", 0)) - to_f(match.get("sell_sm_amount", 0)), 2)
            main_force = round(to_f(match.get("net_mf_amount", 0)), 2)
            result = {
                "date": str(match.get("trade_date") or match.get("date", target_date or "")).replace("-", ""),
                "source": "data_full.json.FundFlows",
                "freshness": "当日",
                "raw_unit": "万元",
                "display_unit": "万元",
                "super_large_net": super_large,
                "large_net": large_net,
                "medium_net": medium_net,
                "small_net": small_net,
                "main_force_net": main_force,
                "super_large_display": f"{super_large:+.0f}万",
                "large_display": f"{large_net:+.0f}万",
                "medium_display": f"{medium_net:+.0f}万",
                "small_display": f"{small_net:+.0f}万",
                "main_force_display": f"{main_force:+.0f}万",
                "source_trace": "Tushare Pro moneyflow via data_full.json",
                "collected_at": "",
            }
            return result
        except Exception:
            return None

    return None


def _load_margin_for_stock(code, trade_date=None):
    """Load latest margin from Tushare margin_detail.
    Returns dict with margin data + source_snapshot metadata for P0-B post-release validation."""
    if code == "300736":
        return {"missing": True, "source_snapshot": {"missing": True, "source_path": f"margin_detail/{code}.json"}}
    mg_file = os.path.join(DATA_CACHE_DIR, "tushare", "margin_detail", f"{code}.json")
    if not os.path.exists(mg_file):
        return None
    try:
        with open(mg_file, "r", encoding="utf-8") as f:
            rows = json.load(f)
        row = rows[0] if isinstance(rows, list) and rows else rows
        if not row or not isinstance(row, dict):
            return None
        # Build source_snapshot for P0-B margin date validation
        snapshot = {}
        if trade_date and row.get("trade_date"):
            latest_ts = str(row["trade_date"])
            report_ts = str(trade_date).replace("-", "")
            lag = 0
            try:
                from datetime import datetime as _dt
                latest_d = _dt.strptime(latest_ts, "%Y%m%d").date()
                report_d = _dt.strptime(report_ts, "%Y%m%d").date()
                lag = (report_d - latest_d).days
            except Exception:
                pass
            snapshot = {
                "latest_trade_date": latest_ts,
                "report_trade_date": report_ts,
                "lag_days": max(0, lag),
                "degraded": latest_ts != report_ts,
                "declared_in": "degraded_items",
                "source_path": str(mg_file)
            }
        return {
            "trade_date": row.get("trade_date"),
            "rzye": row.get("rzye"),
            "rzmre": row.get("rzmre"),
            "rzche": row.get("rzche"),
            "rzye_display": round(row.get("rzye", 0) / 100000000, 2) if row.get("rzye") else None,
            "source_snapshot": snapshot
        }
    except Exception:
        return None



def _load_northbound_for_stock(code):
    hk = os.path.join(DATA_CACHE_DIR, "tushare", "hk_hold", f"{code}.json")
    if os.path.exists(hk):
        return {"status": "缓存存在", "source": "hk_hold", "action_impact": "不作为明日买卖触发"}
    return {"status": "缓存缺失", "source": "hk_hold", "action_impact": "不使用北向增强或削弱动作"}

def _load_pledge_for_stock(code):
    pf = os.path.join(DATA_CACHE_DIR, "tushare", "pledge", f"{code}.json")
    if os.path.exists(pf):
        return {"status": "缓存存在", "source": "pledge", "risk_light": "🟢", "action_impact": "不作为仓位上调依据"}
    return {"status": "缓存缺失", "source": "pledge", "risk_light": "🟡", "action_impact": "缓存缺失，不用于增强动作"}

def _load_unlock_for_stock(code):
    uf = os.path.join(DATA_CACHE_DIR, "tushare", "share_float", f"{code}.json")
    if os.path.exists(uf):
        return {"status": "缓存存在", "source": "share_float", "risk_light": "🟢", "action_impact": "未识别可用于明日动作的近期解禁压力"}
    return {"status": "缓存缺失", "source": "share_float", "risk_light": "🟡", "action_impact": "缓存缺失，不作为仓位调整依据"}

def _load_holder_number_for_stock(code):
    hf = os.path.join(DATA_CACHE_DIR, "tushare", "holder_number", f"{code}.json")
    if os.path.exists(hf):
        return {"status": "数据可用", "source": "holder_number", "action_impact": "不足2期仅披露不推断筹码"}
    return {"status": "缓存缺失", "source": "holder_number", "action_impact": "样本不足，不判断筹码集中或分散"}

def _load_financial_for_stock(code):
    ff = os.path.join(DATA_CACHE_DIR, "tushare", "fina_indicator", f"{code}.json")
    df = os.path.join(DATA_CACHE_DIR, "tushare", "daily_basic", f"{code}.json")
    if os.path.exists(ff):
        return {"status": "fina_indicator缓存存在", "source": "fina_indicator", "action_impact": "具体指标用于深度分析，日报仅作风险覆盖", "key_metrics": "fina_indicator缓存存在，具体指标用于深度分析，日报仅作风险覆盖"}
    if os.path.exists(df):
        return {"status": "daily_basic缓存存在", "source": "daily_basic", "action_impact": "估值数据用于风控参考", "key_metrics": "daily_basic估值数据用于风控参考"}
    return {"status": "缓存缺失", "source": "fina_indicator/daily_basic", "action_impact": "财务数据引用深度分析baseline", "key_metrics": "财务数据引用深度分析baseline"}


def _compute_risk_context(code):
    p = _load_pledge_for_stock(code)
    u = _load_unlock_for_stock(code)
    return {
        "pledge_light": p.get("risk_light", "🟡"),
        "unlock_light": u.get("risk_light", "🟡"),
        "margin_light": "🟡",
        "valuation_light": "🟡",
        "technical_light": "🟡",
        "event_light": "🟢",
        "fund_or_sector_light": "🟡",
        "overall_light": "🟡",
        "position_discount": "\u00d70.5"
    }

def _load_sector_for_stock(code):
    """Load sector/phase from data_scored.json. 保证industry+phase非空。"""
    scored_file = os.path.join(DATA_CACHE_DIR, "data_scored.json")
    if not os.path.exists(scored_file):
        return {"industry": "", "phase": "待确认", "status": "missing_file"}
    try:
        with open(scored_file, "r", encoding="utf-8-sig") as f:
            scored = json.load(f)
        for bucket in ("AllStocks", "Recommendations", "VetoedStocks"):
            for s in scored.get(bucket, []) or []:
                if str(s.get("Code") or s.get("code")) == code:
                    phase = s.get("SectorPhase")
                    if not phase:
                        return {"industry": s.get("Industry"), "phase": "待确认", "status": "missing_phase"}
                    return {"industry": s.get("Industry"), "phase": phase}
    except Exception:
        pass
    return {"industry": "", "phase": "待确认", "status": "not_found"}


def _load_signal_meta():
    """Check if signal_winrate_db exists."""
    sw_file = os.path.join(DATA_CACHE_DIR, "signal_winrate_db.json")
    return {"available": os.path.exists(sw_file)}
def extract_stock_daily_context(target_date_str):
    """v3.6.3: Extract per-stock 4-day OHLCV from kline_cache (primary).
    Falls back to data_full.json only if kline_cache is unavailable.

    Returns:
        dict: {code: {name, days: [{date, w, c, chg, h, l, vol, to}], baseline, fund_flow_4level, margin, sector_phase, signal_winrate, data_status}}
    """
    kline_dir = os.path.join(DATA_CACHE_DIR, "kline_cache")

    # Read stock pool from pigeon_config (single source of truth)
    pool_result = _load_pigeon_stock_pool()
    pool_codes = pool_result.get("codes", [])
    stock_name_map = pool_result.get("name_map", {})
    if not pool_codes:
        log("No stock pool found from pigeon_config.json", "WARN")
        return {}

    result = {}
    for code in pool_codes:
        kf = os.path.join(kline_dir, f"{code}.json")
        if not os.path.exists(kf):
            continue
        try:
            with open(kf, "r", encoding="utf-8") as f:
                kd = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue
        if not kd or len(kd) < 4:
            continue

        # Take last 4 records as the 4-day window
        last4 = kd[-4:]
        days = []
        for d in last4:
            volume_shares = int(d.get("volume") or 0)
            days.append({
                "date": d.get("date", ""),
                "o": d.get("open", 0),
                "c": d.get("close", 0),
                "h": d.get("high", 0),
                "l": d.get("low", 0),
                "v": round(volume_shares / 1000000.0, 1),
                "volume_shares": volume_shares,
                "volume_wan_shou": round(volume_shares / 1000000.0, 1),
                "volume_unit": "万手",
                "chg": d.get("change_pct", 0)
            })

        # Build context with all required fields; name from pigeon_config
        from datetime import timezone, datetime as _dt_ctx
        report_now = _dt_ctx.now(timezone.utc).astimezone(TZ_SHANGHAI) if hasattr(locals(), 'TZ_SHANGHAI') else _dt_ctx.now()
        report_generated_at = report_now.strftime("%Y-%m-%dT%H:%M:%S+08:00")
        margin_data = _load_margin_for_stock(code, target_date_str)
        ctx = {
            "code": code,
            "name": stock_name_map.get(code, code),
            "days": days,
            "baseline": _load_baseline_for_stock(code),
            "fund_flow_4level": _load_fund_flow_for_stock(code, target_date_str),
            "margin": margin_data,
            "sector_phase": _load_sector_for_stock(code),
            "signal_winrate": _load_signal_meta(),
            "data_status": "fresh" if days else "missing",
            "northbound": _load_northbound_for_stock(code),
            "pledge": _load_pledge_for_stock(code),
            "unlock": _load_unlock_for_stock(code),
            "holder_number": _load_holder_number_for_stock(code),
            "financial": _load_financial_for_stock(code),
            "risk_context": _compute_risk_context(code),
            "report_generated_at": report_generated_at,
        }
        # Add source_snapshot if margin data has it
        if isinstance(margin_data, dict) and margin_data.get("source_snapshot"):
            ctx["source_snapshot"] = {"margin": margin_data["source_snapshot"]}
        result[code] = ctx

    return result






def check_pigeon_freshness():
    """Check if events_db.json has been updated today."""
    if not os.path.exists(EVENTS_DB):
        return False, "events_db.json not found"
    mtime = os.path.getmtime(EVENTS_DB)
    mtime_dt = datetime.fromtimestamp(mtime, tz=TZ_SHANGHAI)
    today = datetime.now(TZ_SHANGHAI).date()
    if mtime_dt.date() == today:
        return True, f"events_db updated today at {mtime_dt.strftime('%H:%M')}"
    return False, f"events_db last updated: {mtime_dt.strftime('%Y-%m-%d %H:%M')}"


def _run_canonical_shadow(today_str):
    """Run canonical shadow-only pipeline. 失败只记 WARN，不改变调用方 exit_code。"""
    import subprocess as _subprocess
    shadow_script = os.path.join(ROOT, "scripts", "run_canonical_shadow.py")
    if not os.path.isfile(shadow_script):
        log("canonical-shadow: 脚本不存在", "WARN")
        return
    cmd = [sys.executable, shadow_script, "--date", today_str]
    try:
        proc = _subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if proc.returncode == 0:
            log("SHADOW_CANONICAL: PASS", "OK")
        else:
            log("SHADOW_CANONICAL: BLOCK", "WARN")
        if proc.stdout.strip():
            for line in proc.stdout.strip().splitlines():
                log(f"  [shadow] {line}", "INFO")
        if proc.stderr.strip():
            for line in proc.stderr.strip().splitlines():
                log(f"  [shadow] {line}", "INFO")
    except Exception as e:
        log(f"canonical-shadow 异常: {e}", "WARN")


def run_mode_daily(skip_data_check=False, target_date=None, canonical_shadow=False):
    """Daily report mode: data readiness check, signal if ready."""
    if target_date is None and not is_trading_day():
        return 0

    if target_date:
        today_str = target_date
    else:
        today_str = datetime.now(TZ_SHANGHAI).strftime("%Y%m%d")

    if not acquire_lock("daily_orchestrator"):
        return 0

    try:
        # today_str already set from target_date or current date above

        if skip_data_check:
            if os.environ.get("ALLOW_DAILY_SKIP_DATA_CHECK") != "1":
                log("BLOCK: --skip-data-check is forbidden for production daily report", "BLOCK")
                log("  设置环境变量 ALLOW_DAILY_SKIP_DATA_CHECK=1 可跳过此阻断（仅限本地测试）", "BLOCK")
                return 2
            log("Data check skipped (--skip-data-check) — 测试用，禁止生产发布", "SKIP")
            stock_ctx = extract_stock_daily_context(today_str)
            write_signal("daily_report", {
                "date": today_str,
                "mode": "daily",
                "data_ready": False,
                "skip_data_check": True,
                "publish_allowed": False,
                "stocks_daily_data": stock_ctx,
            })
            log("测试信号已写入，publish_allowed=false，禁止生产发布", "WARN")
            if canonical_shadow:
                _run_canonical_shadow(today_str)
            return 1

        for attempt in range(1, MAX_RETRIES + 1):
            ready, detail = check_data_readiness()
            log(f"Data readiness check (attempt {attempt}/{MAX_RETRIES}): {detail}")

            if ready:
                v36_status, v36_detail = check_v36_data_readiness(target_date)
                log(f"v3.6 data readiness: {v36_status} ({v36_detail['ready']}/{v36_detail['total']})")
                if v36_status == 'BLOCK':
                    missing_summary = {
                        "kline_match": v36_detail.get("kline_match"),
                        "fund_flow_avail": v36_detail.get("fund_flow_avail"),
                        "margin_avail": v36_detail.get("margin_avail"),
                        "baseline_avail": v36_detail.get("baseline_avail"),
                        "sector_avail": v36_detail.get("sector_avail"),
                        "manifest_reason": (v36_detail.get("manifest") or {}).get("reason"),
                    }
                    log(f"v3.6 BLOCK: readiness summary {missing_summary}", "BLOCK")
                    log("日报生成已阻断——不发送daily_report signal。请补齐必须数据后重试。", "BLOCK")

                    # === P3-B: BLOCK 补偿机制 — 写告警信号 + retry trigger ===
                    alert_payload = {
                        "alert": "v36_data_block",
                        "severity": "P1",
                        "date": today_str,
                        "mode": "daily",
                        "block_reason": f"v3.6 BLOCK: kline_match={missing_summary.get('kline_match','?')} "
                                        f"manifest={missing_summary.get('manifest_reason','?')}",
                        "recommend": f"运行以下命令重试数据获取: "
                                     f"python3 scripts/run_daily_data_retry_once.py --date {today_str} --attempt 1",
                    }
                    alert_path = os.path.join(SIGNAL_DIR, "signal_alert.json")
                    try:
                        with open(alert_path, "w", encoding="utf-8") as _af:
                            json.dump(alert_payload, _af, ensure_ascii=False, indent=2)
                        log(f"v3.6 BLOCK ALERT 已写入: {alert_path}", "WARN")
                    except OSError as _e:
                        log(f"v3.6 BLOCK 告警写入失败: {_e}", "ERROR")

                    # 写 retry_trigger 文件供外部脚本/运维识别
                    trigger_path = os.path.join(LOG_DIR, f"retry_trigger_{today_str}.json")
                    try:
                        with open(trigger_path, "w", encoding="utf-8") as _tf:
                            json.dump({
                                "date": today_str,
                                "status": "v3.6_BLOCK",
                                "triggered_at": datetime.now(TZ_SHANGHAI).isoformat(),
                                "retry_command": f"python3 scripts/run_daily_data_retry_once.py --date {today_str} --attempt 1",
                                "note": "v3.6 BLOCK after check_data_readiness passed. Run retry to supplement data.",
                            }, _tf, ensure_ascii=False, indent=2)
                        log(f"v3.6 BLOCK RETRY_TRIGGER 已写入: {trigger_path}", "WARN")
                    except OSError as _e:
                        log(f"v3.6 BLOCK retry_trigger 写入失败: {_e}", "ERROR")

                    return 1
                stock_ctx = extract_stock_daily_context(today_str)
                write_signal("daily_report", {
                    "date": today_str,
                    "mode": "daily",
                    "attempt": attempt,
                    "stocks_daily_data": stock_ctx,
                    "v36_readiness": {"status": v36_status, "detail": v36_detail},
                })
                log("Daily report signal sent", "OK")
                if canonical_shadow:
                    _run_canonical_shadow(today_str)
                return 0

            if attempt < MAX_RETRIES:
                log(f"Waiting {RETRY_DELAY}s before retry...")
                time.sleep(RETRY_DELAY)

        # All retries exhausted — still try to extract context with stale cache
        v36_status, v36_detail = check_v36_data_readiness(target_date)
        log(f"v3.6 data readiness (degraded mode): {v36_status} ({v36_detail['ready']}/{v36_detail['total']})")
        stock_ctx = extract_stock_daily_context(today_str)
        write_signal("daily_report", {
            "date": today_str,
            "mode": "daily",
            "data_ready": False,
            "degraded": True,
            "stocks_daily_data": stock_ctx,
            "v36_readiness": {"status": v36_status, "detail": v36_detail},
        })
        log("Data not ready after max retries, signal sent with degraded flag", "WARN")
        # P3-B: degraded 模式写告警
        try:
            _alert_path = os.path.join(SIGNAL_DIR, "signal_alert.json")
            with open(_alert_path, "w", encoding="utf-8") as _af:
                json.dump({
                    "alert": "v36_data_degraded",
                    "severity": "P1",
                    "date": today_str,
                    "mode": "daily",
                    "block_reason": f"v3.6 degraded: {v36_status} ({v36_detail['ready']}/{v36_detail['total']})",
                    "note": "数据获取重试已达上限，使用陈旧数据生成。需人工核查数据管线。",
                }, _af, ensure_ascii=False, indent=2)
            log(f"v3.6 DEGRADED ALERT 已写入: {_alert_path}", "WARN")
        except OSError as _e:
            log(f"v3.6 DEGRADED 告警写入失败: {_e}", "ERROR")
        if canonical_shadow:
            _run_canonical_shadow(today_str)
        return 1
    finally:
        release_lock("daily_orchestrator")


def run_mode_deep():
    """Weekly deep analysis mode (Friday): check pigeon freshness, signal."""
    if not is_trading_day():
        return 0

    if not acquire_lock("deep_orchestrator"):
        return 0

    try:
        # Check pigeon event data freshness
        fresh, detail = check_pigeon_freshness()
        log(f"Pigeon freshness check: {detail}")

        if not fresh:
            log("Events DB stale, triggering pigeon collection first", "WARN")
            trigger_pigeon_collection()

        write_signal("deep_analysis", {
            "date": datetime.now(TZ_SHANGHAI).strftime("%Y%m%d"),
            "mode": "deep",
            "pigeon_fresh": fresh,
        })
        log("Deep analysis signal sent", "OK")
        return 0
    finally:
        release_lock("deep_orchestrator")


def run_mode_pigeon():
    """Trigger pigeon event collection."""
    if not is_trading_day():
        return 0

    if not acquire_lock("pigeon_orchestrator"):
        return 0

    try:
        trigger_pigeon_collection()
        return 0
    finally:
        release_lock("pigeon_orchestrator")


def trigger_pigeon_collection():
    """Run pigeon collector as subprocess."""
    pigeon_script = os.path.join(ROOT, "代码文件", "信鸽信息采集", "pigeon_collector.py")
    if not os.path.exists(pigeon_script):
        log(f"Pigeon collector not found: {pigeon_script}", "ERROR")
        return False

    log(f"Triggering pigeon collection: {pigeon_script}")
    try:
        result = subprocess_run([sys.executable, pigeon_script],
                                timeout=300, cwd=ROOT)
        if result.returncode == 0:
            log("Pigeon collection completed", "OK")
            return True
        elif result.returncode == 1:
            log("Pigeon collection: no new events (all filtered or already collected)", "INFO")
            return True
        else:
            log(f"Pigeon collection failed (exit={result.returncode})", "ERROR")
            return False
    except subprocess.TimeoutExpired:
        log("Pigeon collection timed out (300s)", "ERROR")
        return False
    except Exception as e:
        log(f"Pigeon collection error: {e}", "ERROR")
        return False


def run_mode_health():
    """Standalone data readiness check (for manual/health use).

    Checks: cache freshness + API source health (reads .health.json files).
    Writes signal_alert.json if API sources are degraded.
    """
    ready, detail = check_data_readiness()

    # Also check API source health from persisted health files
    api_status = check_api_source_health()
    health_ok = ready and api_status["all_ok"]

    if not api_status["all_ok"]:
        detail += f" | API: {api_status['summary']}"
        # Write alert signal for degraded API sources
        write_alert_signal("api_degraded", {
            "sources": api_status["down_sources"],
            "summary": api_status["summary"],
            "recommend": "玉夜检查故障历史表，红枫排查网络/API状态",
        })

    log(f"Health check: {detail}", "OK" if health_ok else "WARN")
    return 0 if health_ok else 1


def check_api_source_health():
    """Read per-source health files (.tencent_health.json etc). Returns status dict.

    Returns:
        dict with keys: all_ok, summary, down_sources, degraded_sources
    """
    health_files = {
        "tencent": os.path.join(DATA_CACHE_DIR, "..", "..", "代码文件", "数据", ".tencent_health.json"),
        "sina": os.path.join(DATA_CACHE_DIR, "..", "..", "代码文件", "数据", ".sina_health.json"),
        "eastmoney": os.path.join(DATA_CACHE_DIR, "..", "..", "代码文件", "数据", ".eastmoney_health.json"),
    }
    # Normalize paths
    for k in health_files:
        health_files[k] = os.path.normpath(os.path.join(ROOT, "代码文件", "数据", f".{k}_health.json"))

    result = {"all_ok": True, "summary": "", "down_sources": [], "degraded_sources": []}

    for name, fpath in health_files.items():
        if not os.path.exists(fpath):
            result["all_ok"] = False
            result["down_sources"].append({"source": name, "status": "unknown", "reason": "health file not found"})
            continue
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                h = json.load(f)
            status = h.get("Status", "unknown")
            if status == "down":
                result["all_ok"] = False
                result["down_sources"].append({
                    "source": name, "source_id": h.get("SourceId", ""),
                    "status": "down", "consecutive_fails": h.get("ConsecutiveFails", 0),
                    "last_success": h.get("LastSuccess"),
                })
            elif status == "degraded":
                result["degraded_sources"].append({
                    "source": name, "source_id": h.get("SourceId", ""),
                    "status": "degraded",
                })
        except (json.JSONDecodeError, OSError):
            result["all_ok"] = False
            result["down_sources"].append({"source": name, "status": "corrupt", "reason": "health file unreadable"})

    if result["down_sources"]:
        names = [s["source"] for s in result["down_sources"]]
        result["summary"] = f"DOWN: {', '.join(names)}"
    elif result["degraded_sources"]:
        names = [s["source"] for s in result["degraded_sources"]]
        result["summary"] = f"DEGRADED: {', '.join(names)}"
    else:
        result["summary"] = "all sources ok"

    return result


def write_alert_signal(alert_type, data):
    """Write an alert signal file for Claude Code / user notification."""
    alert_file = os.path.join(SIGNAL_DIR, "signal_alert.json")
    payload = {
        "alert": alert_type,
        "timestamp": datetime.now(TZ_SHANGHAI).isoformat(),
        "severity": "WARN",
        **data,
    }
    try:
        with open(alert_file, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        log(f"Alert signal written: {alert_file}")
    except OSError as e:
        log(f"Failed to write alert signal: {e}", "ERROR")


def check_fault_events_and_alert():
    """Post-engine check: read fault_events.json, alert on P0-P2 events.

    P0级 → 玉夜+腰子 | P1级 → 玉夜 | P2级 → 玉夜+红枫
    P3级 → 仅记录（连续3次升级为P2后通知）
    """
    try:
        from fault_events import summarize_faults, read_fault_events
    except ImportError:
        return

    summary = summarize_faults()
    if summary["total"] == 0:
        return

    # Check for P0-P2 events (unresolved, last 24h)
    active_alerts = read_fault_events(since_hours=24, min_level="P2")
    if not active_alerts:
        # Check for P3→P2 upgrades
        for alert in summary.get("alerts", []):
            active_alerts.append({
                "EventID": alert["event_id"],
                "Source": alert["source"],
                "Level": "P2(upgraded)",
                "Description": alert["reason"],
            })

    if not active_alerts:
        return

    # Classify by severity and determine who to notify
    notify = {}
    for evt in active_alerts:
        lvl = evt.get("Level", "P5")
        if lvl.startswith("P0"):
            notify.setdefault("玉夜+腰子", []).append(evt)
        elif lvl.startswith("P1"):
            notify.setdefault("玉夜", []).append(evt)
        elif lvl.startswith("P2"):
            notify.setdefault("玉夜+红枫", []).append(evt)

    if notify:
        write_alert_signal("fault_events", {
            "total_events": summary["total"],
            "by_source": summary["by_source"],
            "by_level": summary["by_level"],
            "notify": {k: [f"{e['EventID']} {e.get('Source','')}" for e in v]
                        for k, v in notify.items()},
            "recommend": "玉夜更新故障历史表(08-数据源故障历史.md)，连续3次同源同类型→升级告警",
        })


# Use standard subprocess for Python 3.6+ compatibility
import subprocess as _subprocess


def subprocess_run(args, timeout=None, cwd=None):
    return _subprocess.run(args, capture_output=True, text=True,
                           timeout=timeout, cwd=cwd)


def main():
    parser = argparse.ArgumentParser(description="每日调度统一入口")
    parser.add_argument("--mode", choices=["daily", "deep", "pigeon", "health"],
                        default="health", help="执行模式")
    parser.add_argument("--date", help="指定日期 YYYYMMDD (默认今天)")
    parser.add_argument("--skip-data-check", action="store_true",
                        help="跳过数据就绪检查(测试用)")
    parser.add_argument("--canonical-shadow", action="store_true",
                        help="日报signal后运行canonical shadow-only旁路(不写入正式报告目录)")
    args = parser.parse_args()

    ensure_dirs()
    log(f"Orchestrator started: mode={args.mode} date={args.date or 'today'}")

    mode_handlers = {
        "daily": run_mode_daily,
        "deep": run_mode_deep,
        "pigeon": run_mode_pigeon,
        "health": run_mode_health,
    }

    handler = mode_handlers.get(args.mode)
    if handler:
        if args.mode == "daily":
            exit_code = handler(skip_data_check=args.skip_data_check, target_date=args.date, canonical_shadow=args.canonical_shadow)
        else:
            exit_code = handler()
        log(f"Orchestrator finished: mode={args.mode} exit={exit_code}")
        sys.exit(exit_code)
    else:
        log(f"Unknown mode: {args.mode}", "ERROR")
        sys.exit(2)


if __name__ == "__main__":
    main()
