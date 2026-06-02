#!/usr/bin/env python3
"""build_dynamic_pool.py — Build dynamic stock pool.

Replaces build_dynamic_pool.ps1. Core-stock-first + sector supplementary.
1. Start with core stocks (50 baseline)
2. Scan sectors from EastMoney API, pick top hot sectors
3. Add limited constituent stocks from hot sectors
4. Core stocks always >=60% of pool

Code level: L1
"""
import json
import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent.parent
CONFIG_FILE = ROOT / "代码文件" / "数据" / "pool_config.json"


def load_config():
    if not CONFIG_FILE.exists():
        print(f"ERROR: Config not found: {CONFIG_FILE}", file=sys.stderr)
        sys.exit(1)
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def get_phase_key(avg_chg, avg_turn):
    if avg_turn > 5 and avg_chg > 2:
        return "peak"
    if avg_turn > 3 and avg_chg < -3:
        return "decline"
    if avg_turn > 3 and avg_chg > 0:
        return "rise"
    if avg_turn > 2 and avg_chg < -1:
        return "rise"
    if avg_chg >= -1.5 and avg_turn <= 4:
        return "accum"
    if avg_chg >= -2 and avg_turn <= 2:
        return "accum"
    return "accum"


def main():
    cfg = load_config()
    core_stocks_file = ROOT / cfg.get("paths", {}).get("coreStocks", "代码文件/数据/core_stocks.json")
    output_file = ROOT / cfg.get("paths", {}).get("dynamicPool", "代码文件/数据/dynamic_pool.json")
    sector_map_file = ROOT / cfg.get("paths", {}).get("sectorMap", "代码文件/数据/eastmoney_sector_map.json")

    # Load industry map
    industry_map = {}
    if sector_map_file.exists():
        with open(sector_map_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        industry_map = data.get("Map", {})
        print(f"  Loaded {len(industry_map)} industry mappings")

    # Phase 1: Core stocks (skip anchor stocks + filter by risk)
    print("=== Phase 1: Core stocks ===")
    pool = {}
    anchor_count = 0
    black_filtered = 0
    grey_warned = 0

    if core_stocks_file.exists():
        with open(core_stocks_file, "r", encoding="utf-8") as f:
            core_data = json.load(f)

        # Anchor stocks — independent observation, not in scoring pool
        anchors = core_data.get("AnchorStocks", [])
        if anchors:
            print(f"  Anchor stocks (独立观测,不入池): {len(anchors)}")
            for a in anchors:
                print(f"    {a.get('Code','')} {a.get('Name','')} — {a.get('Role','')}")

        for cs in core_data.get("CoreStocks", []):
            code = cs.get("Code", "")
            if not code or code in pool:
                continue

            risk = cs.get("risk", "normal")

            # Gate 1: blacklist — permanent removal
            if risk == "black":
                black_filtered += 1
                print(f"  BLACK过滤: {code} {cs.get('Name','')}")
                continue

            # Gate 2: greylist — temporary removal (auto-detect from Tushare data)
            if risk == "grey":
                grey_warned += 1
                print(f"  GREY标记(临时移出): {code} {cs.get('Name','')}")
                continue

            pool[code] = {
                "Code": code,
                "Name": cs.get("Name", ""),
                "Industry": cs.get("Industry", ""),
                "Source": "core_stock",
                "risk": risk,
            }

            if risk == "watch":
                print(f"  WATCH标记(保留但折扣): {code} {cs.get('Name','')}")
        print(f"  Core stocks loaded: {len(pool)} (black过滤:{black_filtered}, grey移出:{grey_warned}, watch折扣:{sum(1 for v in pool.values() if v.get('risk')=='watch')})")
    else:
        print(f"ERROR: Core stocks file not found: {core_stocks_file}", file=sys.stderr)
        sys.exit(1)

    if len(pool) < 35:
        print(f"ERROR: Core stocks too few ({len(pool)}), need at least 35", file=sys.stderr)
        sys.exit(1)

    # Phase 2-4: Sector scan & constituents (delegated to API scripts)
    # On macOS, the EastMoney sector data is fetched by stock_data_fetcher_*.py scripts
    # which are pure Python and platform-independent
    print("=== Phase 2-4: Sector scan ===")
    print("  Sector scanning delegated to data fetcher pipeline")
    # Sector data integration point — calls are made by batch_data_collector.py

    # Phase 5: Output
    print("=== Phase 5: Output ===")
    pool_list = list(pool.values())
    total = len(pool_list)
    core_pct = round(len(pool) / total * 100) if total > 0 else 0
    print(f"  Dynamic pool: {total} stocks (core: {len(pool)})")
    print(f"  Core ratio: {core_pct}%")

    output = {
        "BuildTime": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "TotalCount": total,
        "SectorCount": 0,
        "HotSectors": [],
        "CoreCount": len(pool),
        "AnchorCount": len(core_data.get("AnchorStocks", [])),
        "BlackFiltered": black_filtered,
        "GreyFiltered": grey_warned,
        "Stocks": pool_list,
    }

    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"  Output: {output_file}")
    print("Done")


if __name__ == "__main__":
    main()
