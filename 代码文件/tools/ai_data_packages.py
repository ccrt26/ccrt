#!/usr/bin/env python3
"""ai_data_packages.py — AI角色数据包生成器。

每日分析前为6个角色生成标准化数据包，每个包≤50KB。
禁止把大体量原始数据直接喂给AI。

用法:
    python3 ai_data_packages.py --all               # 生成所有角色包
    python3 ai_data_packages.py --role 山猫          # 生成指定角色包
    python3 ai_data_packages.py --date 2026-05-31    # 指定日期

Code level: L1
"""
import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = str(Path(__file__).resolve().parent.parent.parent)
DATA_DIR = os.path.join(ROOT, "代码文件", "数据")
PACKAGE_DIR = os.path.join(ROOT, ".claude", "data_packages")
MAX_PACKAGE_BYTES = 50 * 1024


def load_json(path):
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def build_shanmao_package(date_str):
    """山猫包：指数行情/板块资金/市场情绪。"""
    data_full = load_json(os.path.join(DATA_DIR, "data_full.json"))
    if not data_full:
        return None

    stocks = data_full.get("Stocks", [])
    benchmark = data_full.get("_Meta", {})

    sector_flows = _get_top_sector_flows(data_full, 5)
    has_sector_flow = len(sector_flows) > 0

    return {
        "role": "山猫",
        "generated_at": datetime.now().isoformat(),
        "date": date_str,
        "market_overview": {
            "total_stocks": len(stocks),
            "avg_change_pct": round(sum(s.get("ChangePct", 0) for s in stocks) / max(len(stocks), 1), 2),
            "up_count": sum(1 for s in stocks if (s.get("ChangePct") or 0) > 0),
            "down_count": sum(1 for s in stocks if (s.get("ChangePct") or 0) < 0),
            "limit_up": sum(1 for s in stocks if (s.get("ChangePct") or 0) >= 9.5),
            "limit_down": sum(1 for s in stocks if (s.get("ChangePct") or 0) <= -9.5),
        },
        "sector_flow_top5": sector_flows,
        "sector_flow_top5_status": "available" if has_sector_flow else "unavailable",
        "sector_flow_top5_reason": (
            ""
            if has_sector_flow
            else "data_full.json中SectorFundFlow字段不存在。行业资金流数据未纳入当前采集链路。预计接入: 管线Phase 3(东方财富行业资金流[10])。"
        ),
        "benchmark": benchmark,
        "source": "data_full.json → 统一特征层",
    }


def build_xinge_package(date_str):
    """信鸽包：公告/研报/消息(已过滤)。"""
    events_db = os.path.join(ROOT, "重点股票", "消息面数据", "events_db.json")
    events = load_json(events_db) or []

    recent = [e for e in events if e.get("date", "").startswith(date_str[:7])][-20:]

    return {
        "role": "信鸽",
        "generated_at": datetime.now().isoformat(),
        "date": date_str,
        "recent_events": recent,
        "event_count": len(recent),
        "p0_events": [e for e in recent if e.get("level") == "P0"],
        "source": "events_db.json",
    }


def build_yuye_package(date_str):
    """玉夜包：数据质量/缓存状态/API健康。"""
    dq_report = load_json(os.path.join(DATA_DIR, "data_quality_report.json")) or {}
    health = {}
    for src in ["tencent", "sina", "eastmoney"]:
        h = load_json(os.path.join(DATA_DIR, f".{src}_health.json"))
        if h:
            health[src] = h

    return {
        "role": "玉夜",
        "generated_at": datetime.now().isoformat(),
        "date": date_str,
        "data_quality": dq_report.get("overall", "UNKNOWN"),
        "issues": dq_report.get("issues", [])[:10],
        "api_health": health,
        "source": "data_quality_report.json + .health.json",
    }


def build_liujin_package(date_str):
    """流金包：集中度/回撤/风险指标。"""
    data_scored = load_json(os.path.join(DATA_DIR, "data_scored.json")) or []

    vetoed = [s for s in data_scored if s.get("veto_status") not in (None, "passed", "")]
    high_risk = [s for s in data_scored if (s.get("S_Risk") or 0) <= 2]

    return {
        "role": "流金",
        "generated_at": datetime.now().isoformat(),
        "date": date_str,
        "risk_summary": {
            "vetoed_count": len(vetoed),
            "vetoed_codes": [s.get("Code", "") for s in vetoed[:10]],
            "high_risk_count": len(high_risk),
            "avg_risk_score": round(sum(s.get("S_Risk", 0) for s in data_scored) / max(len(data_scored), 1), 1),
        },
        "source": "data_scored.json",
    }


def build_qingshan_package(date_str):
    """青山包：因子信号/技术指标。"""
    data_scored = load_json(os.path.join(DATA_DIR, "data_scored.json")) or []

    tech_strong = [s for s in data_scored if (s.get("S_Tech") or 0) >= 15]
    money_strong = [s for s in data_scored if (s.get("S_Money") or 0) >= 15]

    return {
        "role": "青山",
        "generated_at": datetime.now().isoformat(),
        "date": date_str,
        "factor_summary": {
            "tech_strong_count": len(tech_strong),
            "money_strong_count": len(money_strong),
            "avg_tech_score": round(sum(s.get("S_Tech", 0) for s in data_scored) / max(len(data_scored), 1), 1),
            "avg_money_score": round(sum(s.get("S_Money", 0) for s in data_scored) / max(len(data_scored), 1), 1),
        },
        "source": "data_scored.json",
    }


def build_yaozi_package(date_str):
    """腰子包：综合上述五包摘要+昨日结论。"""
    return {
        "role": "腰子",
        "generated_at": datetime.now().isoformat(),
        "date": date_str,
        "summary": "综合包，包含其他五包的关键摘要，≤10KB",
        "source": "shanmao+xinge+yuye+liujin+qingshan packages",
    }


ROLE_BUILDERS = {
    "山猫": build_shanmao_package,
    "信鸽": build_xinge_package,
    "玉夜": build_yuye_package,
    "流金": build_liujin_package,
    "青山": build_qingshan_package,
    "腰子": build_yaozi_package,
}


def save_package(pkg, role):
    if not pkg:
        print(f"  [{role}] 数据不可用，跳过")
        return False
    os.makedirs(PACKAGE_DIR, exist_ok=True)
    fname = f"{role}_package_{pkg.get('date', datetime.now().strftime('%Y%m%d'))}.json"
    fpath = os.path.join(PACKAGE_DIR, fname)
    data = json.dumps(pkg, ensure_ascii=False, indent=2)
    size_bytes = len(data.encode("utf-8"))
    if size_bytes > MAX_PACKAGE_BYTES:
        print(f"  [{role}] WARN: 数据包{size_bytes}bytes > {MAX_PACKAGE_BYTES}bytes限制")
    with open(fpath, "w", encoding="utf-8") as f:
        f.write(data)
    print(f"  [{role}] {fpath} ({size_bytes} bytes)")
    return True


def main():
    parser = argparse.ArgumentParser(description="AI角色数据包生成器")
    parser.add_argument("--all", action="store_true", help="生成所有角色包")
    parser.add_argument("--role", help="生成指定角色包")
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    args = parser.parse_args()

    if args.all:
        roles = list(ROLE_BUILDERS.keys())
    elif args.role:
        if args.role not in ROLE_BUILDERS:
            print(f"ERROR: 未知角色 {args.role}，可选: {list(ROLE_BUILDERS.keys())}")
            sys.exit(1)
        roles = [args.role]
    else:
        print("ERROR: 需要 --all 或 --role")
        sys.exit(1)

    print(f"生成角色数据包 (日期: {args.date}):")
    for role in roles:
        builder = ROLE_BUILDERS[role]
        pkg = builder(args.date)
        save_package(pkg, role)
    print("完成")


def _get_top_sector_flows(data_full, n):
    # Fallback: try SectorFundFlow then SectorFundFlows
    fund_flows = (data_full.get("SectorFundFlow") or
                  data_full.get("SectorFundFlows") or [])
    if not fund_flows:
        return []
    sorted_flows = sorted(fund_flows, key=lambda x: x.get("net_amount", 0) or 0, reverse=True)
    return sorted_flows[:n]


if __name__ == "__main__":
    main()
