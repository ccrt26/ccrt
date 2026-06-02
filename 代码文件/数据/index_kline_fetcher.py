#!/usr/bin/env python3
"""index_kline_fetcher.py — 指数K线数据获取与缓存。

从新浪K线[2]获取沪深300等指数日线数据，本地缓存。

用法:
    python3 index_kline_fetcher.py                     # 获取HS300
    python3 index_kline_fetcher.py --index hs300       # 指定指数
    python3 index_kline_fetcher.py --all               # 全部指数

数据源: 新浪K线[2]
缓存路径: 代码文件/数据/index_kline/{index_id}.json
Code level: L1
"""
import json
import os
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = str(Path(__file__).resolve().parent.parent.parent)
CACHE_DIR = os.path.join(ROOT, "代码文件", "数据", "index_kline")

INDEX_CONFIG = {
    "hs300": {"code": "sh000300", "name": "沪深300", "source": "[2]"},
    "csi500": {"code": "sh000905", "name": "中证500", "source": "[2]"},
    "csi1000": {"code": "sh000852", "name": "中证1000", "source": "[2]"},
    "sz50": {"code": "sh000016", "name": "上证50", "source": "[2]"},
}

SINA_KLINE_URL = (
    "https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/"
    "CN_MarketData.getKLineData?symbol={code}&scale=240&ma=no&datalen=120"
)


def fetch_index_kline(index_id):
    cfg = INDEX_CONFIG.get(index_id)
    if not cfg:
        print(f"ERROR: 未知指数 {index_id}")
        return None

    code = cfg["code"]
    url = SINA_KLINE_URL.format(code=code)
    print(f"获取 {cfg['name']}({code}) K线数据...")

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("gbk")

        data = json.loads(raw)
        if not data or not isinstance(data, list):
            print(f"WARN: {index_id} 返回数据为空或格式异常")
            return None

        result = []
        for bar in data:
            result.append({
                "date": bar.get("day", ""),
                "open": float(bar.get("open", 0)),
                "high": float(bar.get("high", 0)),
                "low": float(bar.get("low", 0)),
                "close": float(bar.get("close", 0)),
                "volume": float(bar.get("volume", 0)),
            })

        print(f"  {len(result)} 条记录 ({result[0]['date']} ~ {result[-1]['date']})")
        return result

    except urllib.error.URLError as e:
        print(f"WARN: 新浪API不可达: {e}")
        return None
    except (json.JSONDecodeError, ValueError) as e:
        print(f"WARN: 数据解析失败: {e}")
        return None


def save_cache(index_id, data):
    os.makedirs(CACHE_DIR, exist_ok=True)
    fpath = os.path.join(CACHE_DIR, f"{index_id}.json")
    with open(fpath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"缓存: {fpath}")
    return fpath


def load_cache(index_id):
    fpath = os.path.join(CACHE_DIR, f"{index_id}.json")
    if not os.path.exists(fpath):
        return None
    try:
        with open(fpath, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def get_return_on_date(index_id, date_str):
    """获取指定指数在指定日期的日收益率。"""
    data = load_cache(index_id)
    if not data:
        return None

    for i, bar in enumerate(data):
        if bar["date"] == date_str:
            if i > 0:
                prev = data[i - 1]["close"]
                curr = bar["close"]
                if prev and prev != 0:
                    return round((curr - prev) / prev * 100, 2)
            return None
    return None


def main():
    import argparse
    parser = argparse.ArgumentParser(description="指数K线获取")
    parser.add_argument("--index", default="hs300", choices=list(INDEX_CONFIG.keys()))
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--date", help="查询指定日期收益 YYYYMMDD")
    args = parser.parse_args()

    if args.date:
        ret = get_return_on_date(args.index, args.date)
        cfg = INDEX_CONFIG[args.index]
        print(f"{cfg['name']} {args.date} 收益: {ret}%")
        return

    indices = list(INDEX_CONFIG.keys()) if args.all else [args.index]
    for idx in indices:
        data = fetch_index_kline(idx)
        if data:
            save_cache(idx, data)
            time.sleep(0.5)  # API节流


if __name__ == "__main__":
    main()
