#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tushare 历史数据沉淀脚本
=========================
从Tushare Pro拉取全量历史数据，存入本地JSON，支持增量更新。
双层存储：热缓存(core.ps1 data_cache) + 冷历史(代码文件/数据/tushare/)

用法：
    python tushare_history_sync.py --all                     # 全量同步
    python tushare_history_sync.py --stock 600114            # 单只股票
    python tushare_history_sync.py --type holder_number       # 按数据类型
    python tushare_history_sync.py --daily                    # 仅日频数据

P3-B: 内建日志系统。日志写入 logs/tushare_sync/{date}.log，
不依赖外部 tee 重定向（crontab 中 tee 路径在部分环境失效）。
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "数据", "tushare")
TUSHARE_TOKEN = os.environ.get("TUSHARE_TOKEN", "")
RATE_LIMIT = 0.35

# === P3-B: 内建日志系统 — 自动创建目录，不依赖外部重定向 ===
_LOG_DIR = os.path.join(os.path.dirname(BASE_DIR), "logs", "tushare_sync")


def _log_init():
    """确保日志目录存在，返回日志文件路径。"""
    os.makedirs(_LOG_DIR, exist_ok=True)
    return os.path.join(_LOG_DIR, f"{datetime.now().strftime('%Y%m%d')}.log")


_LOG_PATH = _log_init()


def log(msg, level="INFO"):
    """写 stdout + 日志文件，不依赖外部 tee 重定向。"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{level}] {msg}"
    print(line)
    try:
        with open(_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}][{level}] {msg}\n")
    except OSError:
        pass

KEY_STOCKS = [
    ("600114", "东睦股份"), ("603019", "中科曙光"), ("301075", "多瑞医药"),
    ("601689", "拓普集团"), ("000967", "盈峰环境"), ("601727", "上海电气"),
    ("002230", "科大讯飞"), ("603092", "德力佳"),
    ("300736", "百邦科技"), ("300450", "先导智能"),
]


def get_pro():
    import tushare as ts
    if not TUSHARE_TOKEN:
        raise RuntimeError("TUSHARE_TOKEN not set")
    ts.set_token(TUSHARE_TOKEN)
    return ts.pro_api()


def safe_json_load(path):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def safe_json_save(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)


def merge_dedup(existing, new_data, key_field):
    """合并去重，按key_field保留最新"""
    seen = {}
    for item in existing:
        k = str(item.get(key_field, ""))
        if k not in seen:
            seen[k] = item
    for item in new_data:
        k = str(item.get(key_field, ""))
        seen[k] = item
    return sorted(seen.values(), key=lambda x: str(x.get(key_field, "")), reverse=True)


def sync_hk_hold(pro, code):
    """北向资金 — 全量历史"""
    path = os.path.join(DATA_DIR, "hk_hold", f"{code}.json")
    existing = safe_json_load(path)
    try:
        ts_code = f"{code}.SH" if code.startswith(("6","9")) else f"{code}.SZ"
        df = pro.hk_hold(ts_code=ts_code)
        if df is not None and len(df) > 0:
            new_data = df.to_dict(orient="records")
            merged = merge_dedup(existing, new_data, "trade_date")
            safe_json_save(path, merged)
            return len(merged)
    except Exception as e:
        log(f"  hk_hold {code}: {e}", "ERROR")
    return len(existing)


def sync_holder_number(pro, code):
    """股东人数 — 全量历史"""
    path = os.path.join(DATA_DIR, "holder_number", f"{code}.json")
    existing = safe_json_load(path)
    try:
        ts_code = f"{code}.SH" if code.startswith(("6","9")) else f"{code}.SZ"
        df = pro.stk_holdernumber(ts_code=ts_code)
        if df is not None and len(df) > 0:
            new_data = df.to_dict(orient="records")
            merged = merge_dedup(existing, new_data, "end_date")
            safe_json_save(path, merged)
            return len(merged)
    except Exception as e:
        log(f"  holder_number {code}: {e}", "ERROR")
    return len(existing)


def sync_pledge(pro, code):
    """股权质押 — 全量"""
    path = os.path.join(DATA_DIR, "pledge", f"{code}.json")
    existing = safe_json_load(path)
    try:
        ts_code = f"{code}.SH" if code.startswith(("6","9")) else f"{code}.SZ"
        df = pro.pledge_detail(ts_code=ts_code)
        if df is not None and len(df) > 0:
            new_data = df.to_dict(orient="records")
            merged = merge_dedup(existing, new_data, "ann_date")
            safe_json_save(path, merged)
            return len(merged)
    except Exception as e:
        log(f"  pledge {code}: {e}", "ERROR")
    return len(existing)


def sync_share_float(pro, code):
    """限售解禁 — 全量"""
    path = os.path.join(DATA_DIR, "share_float", f"{code}.json")
    existing = safe_json_load(path)
    try:
        ts_code = f"{code}.SH" if code.startswith(("6","9")) else f"{code}.SZ"
        df = pro.share_float(ts_code=ts_code)
        if df is not None and len(df) > 0:
            new_data = df.to_dict(orient="records")
            merged = merge_dedup(existing, new_data, "float_date")
            safe_json_save(path, merged)
            return len(merged)
    except Exception as e:
        log(f"  share_float {code}: {e}", "ERROR")
    return len(existing)


def sync_moneyflow(pro, code):
    """资金流向 — 近1年日频"""
    path = os.path.join(DATA_DIR, "moneyflow", f"{code}.json")
    existing = safe_json_load(path)
    try:
        ts_code = f"{code}.SH" if code.startswith(("6","9")) else f"{code}.SZ"
        df = pro.moneyflow(ts_code=ts_code, start_date="20250101")
        if df is not None and len(df) > 0:
            new_data = df.to_dict(orient="records")
            merged = merge_dedup(existing, new_data, "trade_date")
            safe_json_save(path, merged)
            return len(merged)
    except Exception as e:
        log(f"  moneyflow {code}: {e}", "ERROR")
    return len(existing)


def sync_daily_basic(pro, code):
    """每日指标 — 近1年"""
    path = os.path.join(DATA_DIR, "daily_basic", f"{code}.json")
    existing = safe_json_load(path)
    try:
        ts_code = f"{code}.SH" if code.startswith(("6","9")) else f"{code}.SZ"
        df = pro.daily_basic(ts_code=ts_code, start_date="20250101")
        if df is not None and len(df) > 0:
            new_data = df.to_dict(orient="records")
            merged = merge_dedup(existing, new_data, "trade_date")
            safe_json_save(path, merged)
            return len(merged)
    except Exception as e:
        log(f"  daily_basic {code}: {e}", "ERROR")
    return len(existing)


def sync_fina_indicator(pro, code):
    """财务指标 — 全量"""
    path = os.path.join(DATA_DIR, "fina_indicator", f"{code}.json")
    existing = safe_json_load(path)
    try:
        ts_code = f"{code}.SH" if code.startswith(("6","9")) else f"{code}.SZ"
        df = pro.fina_indicator(ts_code=ts_code)
        if df is not None and len(df) > 0:
            new_data = df.to_dict(orient="records")
            merged = merge_dedup(existing, new_data, "end_date")
            safe_json_save(path, merged)
            return len(merged)
    except Exception as e:
        log(f"  fina_indicator {code}: {e}", "ERROR")
    return len(existing)


def sync_margin_detail(pro, code):
    """融资融券 — 近1年"""
    path = os.path.join(DATA_DIR, "margin_detail", f"{code}.json")
    existing = safe_json_load(path)
    try:
        ts_code = f"{code}.SH" if code.startswith(("6","9")) else f"{code}.SZ"
        df = pro.margin_detail(ts_code=ts_code, start_date="20250101")
        if df is not None and len(df) > 0:
            new_data = df.to_dict(orient="records")
            merged = merge_dedup(existing, new_data, "trade_date")
            safe_json_save(path, merged)
            return len(merged)
    except Exception as e:
        log(f"  margin_detail {code}: {e}", "ERROR")
    return len(existing)


def sync_forecast(pro, code):
    """业绩预告 — 全量"""
    path = os.path.join(DATA_DIR, "forecast", f"{code}.json")
    existing = safe_json_load(path)
    try:
        ts_code = f"{code}.SH" if code.startswith(("6","9")) else f"{code}.SZ"
        df = pro.forecast(ts_code=ts_code)
        if df is not None and len(df) > 0:
            new_data = df.to_dict(orient="records")
            merged = merge_dedup(existing, new_data, "ann_date")
            safe_json_save(path, merged)
            return len(merged)
    except Exception as e:
        log(f"  forecast {code}: {e}", "ERROR")
    return len(existing)


def sync_fina_mainbz(pro, code):
    """主营业务构成 — 全量"""
    path = os.path.join(DATA_DIR, "fina_mainbz", f"{code}.json")
    existing = safe_json_load(path)
    try:
        ts_code = f"{code}.SH" if code.startswith(("6","9")) else f"{code}.SZ"
        df = pro.fina_mainbz(ts_code=ts_code)
        if df is not None and len(df) > 0:
            new_data = df.to_dict(orient="records")
            merged = merge_dedup(existing, new_data, "end_date")
            safe_json_save(path, merged)
            return len(merged)
    except Exception as e:
        log(f"  fina_mainbz {code}: {e}", "ERROR")
    return len(existing)


def sync_block_trade(pro, code):
    """大宗交易 — 全量"""
    path = os.path.join(DATA_DIR, "block_trade", f"{code}.json")
    existing = safe_json_load(path)
    try:
        ts_code = f"{code}.SH" if code.startswith(("6","9")) else f"{code}.SZ"
        df = pro.block_trade(ts_code=ts_code)
        if df is not None and len(df) > 0:
            new_data = df.to_dict(orient="records")
            merged = merge_dedup(existing, new_data, "trade_date")
            safe_json_save(path, merged)
            return len(merged)
    except Exception as e:
        log(f"  block_trade {code}: {e}", "ERROR")
    return len(existing)


def sync_top_list(pro, code):
    """龙虎榜 — 按日期拉取全市场，过滤个股"""
    path = os.path.join(DATA_DIR, "top_list", f"{code}.json")
    existing = safe_json_load(path)
    try:
        ts_code = f"{code}.SH" if code.startswith(("6","9")) else f"{code}.SZ"
        today = datetime.now().strftime("%Y%m%d")
        df = pro.top_list(trade_date=today)
        if df is not None and len(df) > 0:
            stock_df = df[df["ts_code"] == ts_code]
            if len(stock_df) > 0:
                new_data = stock_df.to_dict(orient="records")
                merged = merge_dedup(existing, new_data, "trade_date")
                safe_json_save(path, merged)
                return len(merged)
    except Exception as e:
        log(f"  top_list {code}: {e}", "ERROR")
    return len(existing)


def sync_dividend(pro, code):
    """分红送股 — 全量"""
    path = os.path.join(DATA_DIR, "dividend", f"{code}.json")
    existing = safe_json_load(path)
    try:
        ts_code = f"{code}.SH" if code.startswith(("6","9")) else f"{code}.SZ"
        df = pro.dividend(ts_code=ts_code)
        if df is not None and len(df) > 0:
            new_data = df.to_dict(orient="records")
            merged = merge_dedup(existing, new_data, "end_date")
            safe_json_save(path, merged)
            return len(merged)
    except Exception as e:
        log(f"  dividend {code}: {e}", "ERROR")
    return len(existing)


def sync_stk_holdertrade(pro, code):
    """股东增减持 — 全量"""
    path = os.path.join(DATA_DIR, "stk_holdertrade", f"{code}.json")
    existing = safe_json_load(path)
    try:
        ts_code = f"{code}.SH" if code.startswith(("6","9")) else f"{code}.SZ"
        df = pro.stk_holdertrade(ts_code=ts_code)
        if df is not None and len(df) > 0:
            new_data = df.to_dict(orient="records")
            merged = merge_dedup(existing, new_data, "ann_date")
            safe_json_save(path, merged)
            return len(merged)
    except Exception as e:
        log(f"  stk_holdertrade {code}: {e}", "ERROR")
    return len(existing)


def sync_repurchase(pro, code):
    """股票回购 — 全量"""
    path = os.path.join(DATA_DIR, "repurchase", f"{code}.json")
    existing = safe_json_load(path)
    try:
        ts_code = f"{code}.SH" if code.startswith(("6","9")) else f"{code}.SZ"
        df = pro.repurchase(ts_code=ts_code)
        if df is not None and len(df) > 0:
            new_data = df.to_dict(orient="records")
            merged = merge_dedup(existing, new_data, "ann_date")
            safe_json_save(path, merged)
            return len(merged)
    except Exception as e:
        log(f"  repurchase {code}: {e}", "ERROR")
    return len(existing)


def update_manifest():
    """更新元数据文件"""
    manifest = {"version": 1, "updated": datetime.now().isoformat(), "stocks": {}}
    for code, name in KEY_STOCKS:
        stock_data = {}
        for api_type in os.listdir(DATA_DIR):
            api_path = os.path.join(DATA_DIR, api_type)
            if not os.path.isdir(api_path):
                continue
            data_file = os.path.join(api_path, f"{code}.json")
            if os.path.exists(data_file):
                records = safe_json_load(data_file)
                stock_data[api_type] = {"records": len(records), "size_kb": os.path.getsize(data_file) // 1024}
        manifest["stocks"][code] = {"name": name, "data": stock_data}
    safe_json_save(os.path.join(DATA_DIR, "manifest.json"), manifest)
    return manifest


SYNC_FUNCS = {
    "hk_hold": sync_hk_hold, "holder_number": sync_holder_number,
    "pledge": sync_pledge, "share_float": sync_share_float,
    "moneyflow": sync_moneyflow, "daily_basic": sync_daily_basic,
    "fina_indicator": sync_fina_indicator, "margin_detail": sync_margin_detail,
    "forecast": sync_forecast, "fina_mainbz": sync_fina_mainbz,
    "block_trade": sync_block_trade, "top_list": sync_top_list,
    "stk_holdertrade": sync_stk_holdertrade, "repurchase": sync_repurchase,
    "dividend": sync_dividend,
}

DAILY_TYPES = ["moneyflow", "daily_basic", "margin_detail"]


def main():
    parser = argparse.ArgumentParser(description="Tushare历史数据沉淀")
    parser.add_argument("--all", action="store_true", help="全量同步所有数据类型")
    parser.add_argument("--stock", type=str, help="指定股票代码")
    parser.add_argument("--type", type=str, choices=list(SYNC_FUNCS.keys()), help="指定数据类型")
    parser.add_argument("--daily", action="store_true", help="仅同步日频数据")
    args = parser.parse_args()

    if not TUSHARE_TOKEN:
        log("ERROR: TUSHARE_TOKEN not set", "BLOCK")
        sys.exit(1)

    try:
        pro = get_pro()
    except Exception as _e:
        log(f"Tushare pro_api 初始化失败: {_e}", "BLOCK")
        sys.exit(1)

    stocks = KEY_STOCKS
    if args.stock:
        stocks = [(args.stock, "")]

    types_to_sync = list(SYNC_FUNCS.keys())
    if args.type:
        types_to_sync = [args.type]
    elif args.daily:
        types_to_sync = DAILY_TYPES

    log(f"Tushare历史数据沉淀 — {datetime.now().isoformat()}")
    log(f"股票数: {len(stocks)}, 数据类型: {len(types_to_sync)}")
    total = 0

    try:
        for api_type in types_to_sync:
            func = SYNC_FUNCS[api_type]
            for code, name in stocks:
                count = func(pro, code)
                log(f"  {api_type} {code} {name}: {count}条")
                total += 1
                time.sleep(RATE_LIMIT)

        manifest = update_manifest()
        total_records = sum(
            s.get("data", {}).get(t, {}).get("records", 0)
            for s in manifest.get("stocks", {}).values()
            for t in types_to_sync
        )
        log(f"完成。总记录数: {total_records}, manifest已更新: {os.path.join(DATA_DIR, 'manifest.json')}")
    except Exception as _e:
        log(f"同步过程中发生未预期异常: {_e}", "BLOCK")
        sys.exit(1)


if __name__ == "__main__":
    main()
