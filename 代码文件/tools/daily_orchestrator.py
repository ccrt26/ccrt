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

# Data readiness: sample stocks to check for closing price freshness
SAMPLE_STOCKS = ["600114", "601727", "002230"]
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


def check_v36_data_readiness(target_date=None):
    """v3.6日报数据就绪检查——13项+fund_flow深度校验。
    返回 (status: str, detail: dict)
    target_date: 目标交易日(YYYY-MM-DD)，默认今天
    """
    if target_date is None:
        today_str = datetime.now(TZ_SHANGHAI).strftime('%Y-%m-%d')
    else:
        today_str = target_date
    date_compact = today_str.replace('-', '')

    items = {}
    # 1. K线缓存
    kline_dir = os.path.join(DATA_CACHE_DIR, "kline_cache")
    items['kline'] = os.path.isdir(kline_dir) and any(
        f.endswith('.json') for f in os.listdir(kline_dir)[:1])

    # K线trade_date校验
    trade_date_ok = False
    kline_file = os.path.join(kline_dir, '600114.json')
    if os.path.exists(kline_file):
        try:
            with open(kline_file, 'r', encoding='utf-8') as f:
                kd = json.load(f)
            if kd and isinstance(kd, list) and len(kd) > 0:
                latest_kline_date = kd[-1].get('date', '')
                trade_date_ok = (latest_kline_date == today_str)
                items['kline_trade_date_match'] = trade_date_ok
        except:
            pass

    # 2-5. 数据文件(降级为辅助)
    for fname, label in [('data_scored.json', 'scored'), ('data_full.json', 'full')]:
        fp = os.path.join(DATA_CACHE_DIR, fname)
        items[f'data_{label}'] = os.path.exists(fp) and os.path.getsize(fp) > 1000

    # ===== P0-4: 四档资金深度校验 =====
    fund_ok = False
    fund_source_ok = False
    fund_cache_all = os.path.join(DATA_CACHE_DIR, 'fund_flow_cache', f'{date_compact}_all.json')
    tushare_health_file = os.path.join(DATA_CACHE_DIR, '.tushare_health.json')

    # 检查tushare health
    if os.path.exists(tushare_health_file):
        try:
            with open(tushare_health_file) as f:
                th = json.load(f)
            items['tushare_health_status'] = th.get('status', 'unknown')
            items['tushare_health_date'] = th.get('latest_trade_date', '')
            items['tushare_health_stocks'] = th.get('stock_count', 0)
        except:
            items['tushare_health_status'] = 'error'

    # 检查fund_flow_cache
    if os.path.exists(fund_cache_all):
        try:
            with open(fund_cache_all) as f:
                ff_all = json.load(f)
            # 验证每只重点股票
            sample_codes = ['600114', '601727', '002230']
            matched = 0
            tushare_count = 0
            for code in sample_codes:
                if code in ff_all:
                    rec = ff_all[code]
                    rec_date = str(rec.get('date', '')).replace('-', '')
                    if rec_date == date_compact:
                        matched += 1
                    if 'tushare' in str(rec.get('source', '')).lower():
                        tushare_count += 1

            # 验证单票缓存一致性
            consistent = True
            for code in ff_all:
                single_file = os.path.join(DATA_CACHE_DIR, 'fund_flow_cache', f'{code}.json')
                if os.path.exists(single_file):
                    try:
                        with open(single_file) as f:
                            single = json.load(f)
                        single_june1 = [r for r in single if str(r.get('date', '')).replace('-', '') == date_compact]
                        if single_june1:
                            s = single_june1[0].get('main_force_net', 0)
                            a = ff_all[code].get('main_force_net', -999)
                            if abs(s - a) > 0.01:
                                consistent = False
                                break
                    except:
                        pass

            fund_ok = matched >= 2 and tushare_count >= 2
            fund_source_ok = tushare_count >= 2
            items['fund_flow_match'] = matched
            items['fund_flow_tushare'] = tushare_count
            items['fund_flow_consistent'] = consistent
        except:
            pass

    items['fund_flow_4level'] = fund_ok
    items['fund_flow_source_ok'] = fund_source_ok
    items['fund_flow_consistent'] = items.get('fund_flow_consistent', False)

    # 简单字段
    items['margin'] = True  # Tushare可用
    items['northbound'] = True
    for label in ['pledge', 'unlock', 'holder', 'financial']:
        items[label] = os.path.exists(os.path.join(DATA_CACHE_DIR, 'data_scored.json'))
    items['events'] = os.path.exists(EVENTS_DB) if os.path.exists(EVENTS_DB) else False
    items['signal_winrate'] = os.path.exists(os.path.join(DATA_CACHE_DIR, 'signal_winrate_db.json'))
    deep_dir = os.path.join(ROOT, '重点股票', '深度分析', '深度分析报告')
    items['baseline'] = os.path.isdir(deep_dir) and any(
        '600114' in f for f in os.listdir(deep_dir)[:20]) if os.path.isdir(deep_dir) else False
    items['baseline'] = os.path.isdir(deep_dir) and any(
        '600114' in f for f in os.listdir(deep_dir)[:20]) if os.path.isdir(deep_dir) else False
    items['deep_appendix'] = items['baseline']

    ready = sum(1 for v in items.values() if v)
    total = len(items)
    pct = ready / total * 100

    # P0-4: 必须项含fund_flow校验
    must_have = ['kline', 'kline_trade_date_match', 'fund_flow_4level', 'fund_flow_source_ok']
    must_ok = all(items.get(k) for k in must_have)
    fund_inconsistent = not items.get('fund_flow_consistent', True)

    if not must_ok or fund_inconsistent:
        status = 'BLOCK'
    elif ready < 12:
        status = 'WARN'
    else:
        status = 'READY'

    return status, {'ready': ready, 'total': total, 'pct': round(pct, 1),
                    'must_ok': must_ok, 'items': items}


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


def extract_stock_daily_context(target_date_str):
    """Extract per-stock 4-day OHLCV from data_full.json for daily report context.

    Reads data_full.json and pigeon_config.json, builds a compact dict of the last
    4 trading days' data for each stock in the pool. Written into the daily signal
    so the AI report generator can fill §§1.2 and §zero baseline columns.

    Returns:
        dict: {code: {name, days: [{date, w, c, chg, h, l, vol, to}]}}
        Empty dict if data_full.json is missing or unreadable.
    """
    data_file = os.path.join(DATA_CACHE_DIR, "data_full.json")
    pigeon_cfg = os.path.join(ROOT, "代码文件", "信鸽信息采集", "pigeon_config.json")

    if not os.path.exists(data_file):
        log(f"data_full.json not found at {data_file}", "WARN")
        return {}

    try:
        with open(data_file, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        log(f"Failed to read data_full.json: {e}", "WARN")
        return {}

    stocks_list = raw.get("Stocks", [])
    if not stocks_list:
        return {}

    # Build lookup by code
    by_code = {}
    for s in stocks_list:
        code = s.get("Code", "")
        if code:
            by_code[code] = s

    # Read stock pool
    pool_codes = []
    if os.path.exists(pigeon_cfg):
        try:
            with open(pigeon_cfg, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            pool_codes = [s["code"] for s in cfg.get("target_stocks", [])]
        except (json.JSONDecodeError, KeyError, OSError):
            pass

    if not pool_codes:
        pool_codes = list(by_code.keys())

    # Compute weekday labels from target date
    try:
        target_dt = datetime.strptime(target_date_str, "%Y%m%d")
    except ValueError:
        target_dt = datetime.now(TZ_SHANGHAI)
    WEEKDAY_CN = ["一", "二", "三", "四", "五", "六", "日"]

    result = {}
    for code in pool_codes:
        s = by_code.get(code)
        if not s:
            continue
        kc = s.get("KClose", [])
        if len(kc) < 5:  # need 5 points for 4 changes
            continue
        ko = s.get("KOpen", [])
        kh = s.get("KHigh", [])
        kl = s.get("KLow", [])
        kv = s.get("KVolume", [])

        def _chg(i):
            prev = kc[i - 1]
            return round((kc[i] - prev) / prev * 100, 2) if prev and prev != 0 else None

        def _wkday(offset):
            """offset=0 for today, 1 for yesterday, etc. Skip weekends."""
            d = target_dt - timedelta(days=offset)
            while d.weekday() >= 5:
                d -= timedelta(days=1)
            return WEEKDAY_CN[d.weekday()], d.strftime("%m%d")

        def _hi_lo(i):
            h = kh[i] if abs(i) <= len(kh) else None
            l = kl[i] if abs(i) <= len(kl) else None
            return h, l

        # Build 4-day window: KClose[-1]=today(T), [-2]=T-1, [-3]=T-2, [-4]=T-3
        days = []
        for off in [3, 2, 1, 0]:
            idx = -(off + 1)  # off=0→-1(today), off=3→-4(T-3)
            w, date_md = _wkday(off)
            h, l = _hi_lo(idx)
            entry = {
                "date": date_md,
                "w": w,
                "c": kc[idx],
                "chg": _chg(idx),
                "h": h,
                "l": l,
                "vol": kv[idx] if abs(idx) <= len(kv) else None,
                "to": s.get("TurnoverRate") if off == 0 else None,
            }
            days.append(entry)

        # Fund flow: latest from FundFlows, with staleness note
        fund_flows = raw.get("FundFlows", {})
        ff_data = fund_flows.get(code, [])
        ff_latest = None
        if isinstance(ff_data, list) and ff_data:
            ff_latest = ff_data[0]  # already sorted by date desc
            ff_date = ff_latest.get("trade_date", "")
            ff_stale = (ff_date != target_date_str)
            ff_latest = {
                "date": ff_date,
                "net_mf_amount": ff_latest.get("net_mf_amount"),
                "is_stale": ff_stale,
                "note": f"最新可用{ff_date[4:6]}/{ff_date[6:8]}（T+1延迟）" if ff_stale else "当日数据",
            }

        # Margin: latest from Margins, with staleness note
        margins = raw.get("Margins", {})
        mg_data = margins.get(code, [])
        mg_latest = None
        if isinstance(mg_data, list) and mg_data:
            mg_latest_rec = mg_data[0]
            mg_date = mg_latest_rec.get("trade_date", "")
            mg_stale = (mg_date != target_date_str)
            mg_latest = {
                "date": mg_date,
                "rzye": mg_latest_rec.get("rzye"),        # 融资余额(元)
                "rzmre": mg_latest_rec.get("rzmre"),      # 融资买入额(元)
                "rzche": mg_latest_rec.get("rzche"),      # 融资偿还额(元)
                "is_stale": mg_stale,
                "note": f"最新可用{mg_date[4:6]}/{mg_date[6:8]}" if mg_stale else "当日数据",
            }

        # Financial: latest quarter from Financials
        financials = raw.get("Financials", {})
        fin_data = financials.get(code, [])
        fin_latest = None
        if isinstance(fin_data, list) and fin_data:
            fin_rec = fin_data[0]
            fin_latest = {
                "end_date": fin_rec.get("end_date", ""),
                "roe": fin_rec.get("roe"),
                "gross_margin": fin_rec.get("grossprofit_margin"),
                "ocfps": fin_rec.get("ocfps"),
                "revenue_ps": fin_rec.get("revenue_ps"),
                "eps": fin_rec.get("eps"),
            }

        result[code] = {
            "name": s.get("Name", code),
            "days": days,
            "fund_flow": ff_latest,
            "margin": mg_latest,
            "financial": fin_latest,
        }

    log(f"Stock daily context extracted: {len(result)} stocks, {len(days)} days each")
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


def run_mode_daily(skip_data_check=False, target_date=None):
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
            log("Data check skipped (--skip-data-check)", "SKIP")
            stock_ctx = extract_stock_daily_context(today_str)
            write_signal("daily_report", {
                "date": today_str,
                "mode": "daily",
                "data_ready": True,
                "stocks_daily_data": stock_ctx,
            })
            log("Daily report signal sent (check skipped)", "OK")
            return 0

        for attempt in range(1, MAX_RETRIES + 1):
            ready, detail = check_data_readiness()
            log(f"Data readiness check (attempt {attempt}/{MAX_RETRIES}): {detail}")

            if ready:
                v36_status, v36_detail = check_v36_data_readiness(target_date)
                log(f"v3.6 data readiness: {v36_status} ({v36_detail['ready']}/{v36_detail['total']})")
                if v36_status == 'BLOCK':
                    log(f"v3.6 BLOCK: 必须项缺失 {[k for k,v in v36_detail['items'].items() if not v]}", "BLOCK")
                    log("日报生成已阻断——不发送daily_report signal。请补齐必须数据后重试。", "BLOCK")
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
            exit_code = handler(skip_data_check=args.skip_data_check, target_date=args.date)
        else:
            exit_code = handler()
        log(f"Orchestrator finished: mode={args.mode} exit={exit_code}")
        sys.exit(exit_code)
    else:
        log(f"Unknown mode: {args.mode}", "ERROR")
        sys.exit(2)


if __name__ == "__main__":
    main()
