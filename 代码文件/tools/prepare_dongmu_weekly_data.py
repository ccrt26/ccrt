#!/usr/bin/env python3
"""Prepare the minimum data pack for the Dongmu weekly deep-analysis sample.

Scope:
- Fetch only the kline series required by the Dongmu weekly sample.
- Rebuild fund_flow_cache/600114.json from local tushare/moneyflow data.
- Compute temporary PE/PB percentiles from local daily_basic data.
- Emit a reviewable readiness JSON/Markdown pack.

This script does not modify production report templates or report entrances.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "代码文件" / "数据"
KLINE_DIR = DATA_DIR / "kline_cache"
INDEX_KLINE_DIR = DATA_DIR / "index_kline"
TUSHARE_DIR = DATA_DIR / "tushare"
FUND_FLOW_DIR = DATA_DIR / "fund_flow_cache"
OUTPUT_DIR = ROOT / "重点股票" / "深度分析" / "深度分析报告" / "东睦股份(600114)"

KLINE_TARGETS = {
    "600114": {
        "kind": "stock",
        "symbol": "sh600114",
        "name": "东睦股份",
        "path": KLINE_DIR / "600114.json",
    },
    "hs300": {
        "kind": "index",
        "symbol": "sh000300",
        "name": "沪深300",
        "path": INDEX_KLINE_DIR / "hs300.json",
    },
    "cyb": {
        "kind": "index",
        "symbol": "sz399006",
        "name": "创业板指",
        "path": INDEX_KLINE_DIR / "cyb.json",
    },
}

SINA_KLINE_URL = (
    "https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/"
    "CN_MarketData.getKLineData?symbol={symbol}&scale=240&ma=no&datalen={datalen}"
)


def read_json(path: Path, default: Any = None) -> Any:
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return default


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def fetch_sina_kline(symbol: str, datalen: int) -> list[dict[str, Any]]:
    url = SINA_KLINE_URL.format(symbol=symbol, datalen=datalen)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read().decode("gbk")
    data = json.loads(raw)
    if not isinstance(data, list) or not data:
        raise RuntimeError(f"Sina returned empty kline for {symbol}")

    rows = []
    for bar in data:
        rows.append(
            {
                "date": bar.get("day", ""),
                "open": float(bar.get("open", 0) or 0),
                "high": float(bar.get("high", 0) or 0),
                "low": float(bar.get("low", 0) or 0),
                "close": float(bar.get("close", 0) or 0),
                "volume": float(bar.get("volume", 0) or 0),
            }
        )
    return rows


def prepare_kline(datalen: int, fetch: bool) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for target_id, cfg in KLINE_TARGETS.items():
        path = cfg["path"]
        before = read_json(path, [])
        status = "existing"
        error = ""

        if fetch:
            try:
                rows = fetch_sina_kline(cfg["symbol"], datalen)
                if len(rows) >= len(before or []):
                    write_json(path, rows)
                    status = "fetched"
                else:
                    status = "kept_existing_short_fetch"
            except Exception as exc:  # noqa: BLE001 - readiness report needs exact failure
                status = "fetch_failed"
                error = str(exc)

        after = read_json(path, [])
        result[target_id] = {
            "name": cfg["name"],
            "kind": cfg["kind"],
            "path": str(path.relative_to(ROOT)),
            "records_before": len(before or []),
            "records_after": len(after or []),
            "first_date": (after or [{}])[0].get("date") if after else None,
            "last_date": (after or [{}])[-1].get("date") if after else None,
            "status": status,
            "error": error,
            "ready_250": len(after or []) >= 250,
        }
    return result


def normalize_moneyflow_row(row: dict[str, Any]) -> dict[str, Any] | None:
    def to_float(value: Any) -> float:
        try:
            if value is None or (isinstance(value, float) and math.isnan(value)):
                return 0.0
            return round(float(value), 2)
        except (TypeError, ValueError):
            return 0.0

    date = str(row.get("trade_date") or row.get("date") or "").replace("-", "")
    if not date:
        return None

    if "super_large_net" in row:
        super_large = to_float(row.get("super_large_net"))
        large = to_float(row.get("large_net"))
        medium = to_float(row.get("medium_net"))
        small = to_float(row.get("small_net"))
        main = to_float(row.get("main_force_net"))
    else:
        super_large = to_float(row.get("buy_elg_amount")) - to_float(row.get("sell_elg_amount"))
        large = to_float(row.get("buy_lg_amount")) - to_float(row.get("sell_lg_amount"))
        medium = to_float(row.get("buy_md_amount")) - to_float(row.get("sell_md_amount"))
        small = to_float(row.get("buy_sm_amount")) - to_float(row.get("sell_sm_amount"))
        main = to_float(row.get("net_mf_amount"))
        if not main:
            main = super_large + large

    super_large = round(super_large, 2)
    large = round(large, 2)
    medium = round(medium, 2)
    small = round(small, 2)
    main = round(main, 2)
    return {
        "date": date,
        "source": "tushare_moneyflow",
        "raw_unit": "万元",
        "display_unit": "万元",
        "super_large_net": super_large,
        "large_net": large,
        "medium_net": medium,
        "small_net": small,
        "main_force_net": main,
        "super_large_display": f"{super_large:+.0f}万",
        "large_display": f"{large:+.0f}万",
        "medium_display": f"{medium:+.0f}万",
        "small_display": f"{small:+.0f}万",
        "main_force_display": f"{main:+.0f}万",
        "source_trace": "Tushare Pro moneyflow raw cache",
        "collected_at": datetime.now().isoformat(timespec="seconds"),
    }


def rebuild_fund_flow_cache(code: str) -> dict[str, Any]:
    source = TUSHARE_DIR / "moneyflow" / f"{code}.json"
    target = FUND_FLOW_DIR / f"{code}.json"
    raw_rows = read_json(source, [])
    before = read_json(target, [])
    normalized = []
    seen_dates = set()
    for row in raw_rows or []:
        item = normalize_moneyflow_row(row)
        if not item or item["date"] in seen_dates:
            continue
        seen_dates.add(item["date"])
        normalized.append(item)
    normalized.sort(key=lambda r: r["date"])
    if normalized:
        write_json(target, normalized)
    after = read_json(target, [])
    return {
        "source_path": str(source.relative_to(ROOT)),
        "target_path": str(target.relative_to(ROOT)),
        "raw_records": len(raw_rows or []),
        "records_before": len(before or []),
        "records_after": len(after or []),
        "first_date": (after or [{}])[0].get("date") if after else None,
        "last_date": (after or [{}])[-1].get("date") if after else None,
        "latest_5": (after or [])[-5:],
        "ready": len(after or []) >= 20,
    }


def percentile(values: list[float], current: float) -> float | None:
    vals = [v for v in values if isinstance(v, (int, float)) and not math.isnan(v)]
    if not vals:
        return None
    below_or_equal = sum(1 for v in vals if v <= current)
    return round(below_or_equal / len(vals) * 100, 1)


def compute_pe_pb_percentile(code: str) -> dict[str, Any]:
    path = TUSHARE_DIR / "daily_basic" / f"{code}.json"
    rows = read_json(path, [])
    rows = sorted(rows or [], key=lambda r: str(r.get("trade_date", "")))
    if not rows:
        return {"ready": False, "error": "daily_basic missing"}
    latest = rows[-1]
    pe_values = [float(r["pe_ttm"]) for r in rows if r.get("pe_ttm") is not None]
    pb_values = [float(r["pb"]) for r in rows if r.get("pb") is not None]
    pe_latest = float(latest.get("pe_ttm")) if latest.get("pe_ttm") is not None else None
    pb_latest = float(latest.get("pb")) if latest.get("pb") is not None else None
    return {
        "source_path": str(path.relative_to(ROOT)),
        "records": len(rows),
        "window_label": "1.5年临时分位",
        "method": "rank percentile over local tushare/daily_basic rows",
        "trade_date": latest.get("trade_date"),
        "pe_ttm": pe_latest,
        "pe_ttm_percentile": percentile(pe_values, pe_latest) if pe_latest is not None else None,
        "pb": pb_latest,
        "pb_percentile": percentile(pb_values, pb_latest) if pb_latest is not None else None,
        "ready": len(rows) >= 250,
        "limitation": "不足3年/5年正式分位，仅供东睦样稿手工验证",
    }


def latest_record(path: Path, key: str) -> dict[str, Any] | None:
    rows = read_json(path, [])
    if not rows:
        return None
    return sorted(rows, key=lambda r: str(r.get(key, "")))[-1]


def collect_weekly_inputs(code: str) -> dict[str, Any]:
    margin = latest_record(TUSHARE_DIR / "margin_detail" / f"{code}.json", "trade_date")
    holder_rows = read_json(TUSHARE_DIR / "holder_number" / f"{code}.json", [])
    holder_sorted = sorted(holder_rows or [], key=lambda r: str(r.get("end_date", "")))
    holder_latest = holder_sorted[-1] if holder_sorted else None
    holder_prev = holder_sorted[-2] if len(holder_sorted) >= 2 else None
    holder_change = None
    if holder_latest and holder_prev and holder_prev.get("holder_num"):
        holder_change = round(
            (float(holder_latest.get("holder_num") or 0) - float(holder_prev.get("holder_num") or 0))
            / float(holder_prev.get("holder_num"))
            * 100,
            1,
        )

    events = read_json(ROOT / "重点股票" / "消息面数据" / "events_db.json", [])
    stock_events = [e for e in events or [] if str(e.get("code")) == code]

    def count(name: str) -> int:
        return len(read_json(TUSHARE_DIR / name / f"{code}.json", []) or [])

    return {
        "margin_latest": margin,
        "pledge_records": count("pledge"),
        "share_float_records": count("share_float"),
        "block_trade_records": count("block_trade"),
        "holder_latest": holder_latest,
        "holder_previous": holder_prev,
        "holder_change_pct": holder_change,
        "fina_indicator_records": count("fina_indicator"),
        "events_count": len(stock_events),
        "events": stock_events,
        "signal_winrate_rule": "B层可参考；A层禁用强化结论，待后评估来源校验",
        "product_revenue_rule": "产品级营收待信鸽从FY2025年报PDF提取；未完成前只写待验证",
    }


def write_markdown(pack: dict[str, Any], md_path: Path) -> None:
    lines = [
        "# 东睦股份周报样稿数据就绪包 20260610",
        "",
        "> 范围：600114东睦股份周报样稿手工验证。未改正式模板，未切生产入口。",
        "",
        "## 1. K线就绪度",
        "",
        "| 标的 | 记录数 | 日期范围 | 是否≥250 | 状态 |",
        "|:--|--:|:--|:--|:--|",
    ]
    for item in pack["kline"].values():
        lines.append(
            f"| {item['name']} | {item['records_after']} | {item['first_date']}~{item['last_date']} | "
            f"{'是' if item['ready_250'] else '否'} | {item['status']} |"
        )
    ff = pack["fund_flow"]
    pp = pack["pe_pb_percentile"]
    wi = pack["weekly_inputs"]
    lines += [
        "",
        "## 2. 资金缓存",
        "",
        f"- 原始moneyflow：{ff['raw_records']}条",
        f"- fund_flow_cache：{ff['records_before']}条 -> {ff['records_after']}条",
        f"- 日期范围：{ff['first_date']}~{ff['last_date']}",
        "",
        "## 3. 估值临时分位",
        "",
        f"- 来源：{pp.get('source_path')}",
        f"- 记录数：{pp.get('records')}",
        f"- 最新日期：{pp.get('trade_date')}",
        f"- PE_TTM：{pp.get('pe_ttm')}，临时分位：{pp.get('pe_ttm_percentile')}%",
        f"- PB：{pp.get('pb')}，临时分位：{pp.get('pb_percentile')}%",
        f"- 限制：{pp.get('limitation')}",
        "",
        "## 4. 样稿可直接填入项",
        "",
        f"- 融资融券最新：{(wi.get('margin_latest') or {}).get('trade_date')}，融资余额 "
        f"{(wi.get('margin_latest') or {}).get('rzye')}",
        f"- 质押记录：{wi.get('pledge_records')}条",
        f"- 解禁记录：{wi.get('share_float_records')}条",
        f"- 大宗交易记录：{wi.get('block_trade_records')}条",
        f"- 股东户数最新：{(wi.get('holder_latest') or {}).get('end_date')}，"
        f"{(wi.get('holder_latest') or {}).get('holder_num')}户，环比{wi.get('holder_change_pct')}%",
        f"- 财务指标：{wi.get('fina_indicator_records')}条",
        f"- events_db东睦事件：{wi.get('events_count')}条",
        "",
        "## 5. 使用限制",
        "",
        "- signal_winrate：B层可参考；A层禁用强化结论，待后评估来源校验。",
        "- 产品级营收：待信鸽从FY2025年报PDF提取；未完成前只写待验证。",
        "- 大盘北向：本包未纳入；未确认日频净买入来源前不使用。",
    ]
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare Dongmu weekly sample data pack")
    parser.add_argument("--no-fetch", action="store_true", help="不联网抓取K线，只用现有缓存")
    parser.add_argument("--datalen", type=int, default=320)
    args = parser.parse_args()

    pack = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "scope": "东睦股份(600114)周报样稿手工验证",
        "kline": prepare_kline(datalen=args.datalen, fetch=not args.no_fetch),
        "fund_flow": rebuild_fund_flow_cache("600114"),
        "pe_pb_percentile": compute_pe_pb_percentile("600114"),
        "weekly_inputs": collect_weekly_inputs("600114"),
        "stage_boundary": {
            "production_template_changed": False,
            "production_entry_changed": False,
            "full_pool_backfilled": False,
        },
    }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUTPUT_DIR / "东睦股份(600114)_周报样稿数据就绪包_20260610.json"
    md_path = OUTPUT_DIR / "东睦股份(600114)_周报样稿数据就绪包_20260610.md"
    write_json(json_path, pack)
    write_markdown(pack, md_path)
    print(f"JSON: {json_path}")
    print(f"MD:   {md_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
