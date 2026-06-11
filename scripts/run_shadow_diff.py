#!/usr/bin/env python3
"""
run_shadow_diff.py — Shadow diff 自动化验证（v1.1）
**第一轮主验证入口**：独立脚本，不依赖 cached_data_source.py 改造，
不接入 daily_workflow.py，不改变正式输出。

对比 UnifiedDataSource（新路由）与 legacy 源（kline_cache/data_full）的输出差异。
--date 必须真实参与比对；非核心接口 BLOCK 不得伪装为 PASS。

用法:
  python3 scripts/run_shadow_diff.py --code 600114 --date 20260609
  python3 scripts/run_shadow_diff.py --code 600114 --date 20260609 --json
  python3 scripts/run_shadow_diff.py --all-stocks --date 20260609

退出码:
  0 = CORE PASS（非核心 BLOCK 仍为 0）
  1 = WARN（核心接口有 diff 或非核心有 BLOCK）
  2 = BLOCK（脚本错误）
"""
import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

sys.path.insert(0, str(ROOT / "代码文件" / "数据"))
from unified_data_source import UnifiedDataSource

# ── 容差配置 ─────────────────────────────────────
TOLERANCE = {
    "close": 0.01,         # 收盘价 ≤ ¥0.01
    "change_pct": 0.05,    # 涨跌幅 ≤ 0.05%
    "volume_wan_shou": 1.0,  # 成交量 ≤ 1 万手
}

LOG_DIR = ROOT / "代码文件" / "数据" / "l2_cache"
DIFF_LOG = LOG_DIR / "shadow_diff_log.jsonl"
DATA_DIR = ROOT / "代码文件" / "数据"

# ── 接口分类 ──────────────────────────────────────
CORE_INTERFACES = {"get_kline", "get_quote"}
NON_CORE_INTERFACES = {
    "get_score_history", "get_financials", "get_macro",
    "compare_current_vs_historical", "compute_factor_ic",
    "get_max_drawdown", "get_volatility_percentile", "export_factor_panel",
}


def _now_iso():
    return datetime.now().isoformat()


def find_record_by_date(data_list, date_str, date_fields=("date", "trade_date")):
    """在记录列表中查找指定日期的记录。

    date_str 可接受 YYYYMMDD 或 YYYY-MM-DD 格式。
    data_list 中的日期可以是 YYYY-MM-DD 或 YYYYMMDD。
    未找到返回 None。
    """
    if not data_list:
        return None
    date_compact = date_str.replace("-", "")
    for r in data_list:
        if not isinstance(r, dict):
            continue
        for field in date_fields:
            val = r.get(field, "")
            if str(val).replace("-", "") == date_compact:
                return r
    return None


def load_stock_pool() -> list:
    """从 pigeon_config.json 获取重点股票列表"""
    cfg_path = ROOT / "代码文件" / "信鸽信息采集" / "pigeon_config.json"
    if not cfg_path.exists():
        return []
    try:
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    except (json.JSONDecodeError, OSError):
        return []
    stocks = cfg.get("target_stocks", []) or cfg.get("stocks", [])
    result = []
    for s in stocks:
        code = str(s.get("code") or s.get("Code", ""))
        name = s.get("name") or s.get("Name", "")
        if code and name:
            result.append((code, name))
    return result


def get_legacy_kline(code, limit=120):
    """从 legacy kline_cache/{code}.json 读取"""
    p = DATA_DIR / "kline_cache" / f"{code}.json"
    if not p.exists():
        return None
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return sorted(data, key=lambda r: r.get("date", ""), reverse=True)[:limit]
        return None
    except (json.JSONDecodeError, OSError):
        return None


def get_legacy_quote(code):
    """从 legacy data_full.json 读取报价"""
    p = DATA_DIR / "data_full.json"
    if not p.exists():
        return None
    try:
        with open(p, "r", encoding="utf-8") as f:
            df = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None
    stocks = df.get("Stocks", df.get("stocks", []))
    for s in stocks:
        if str(s.get("Code", s.get("code", ""))) == code:
            kdates = s.get("KDate") or []
            if not kdates:
                return None
            idx = len(kdates) - 1
            return {
                "close": s.get("KClose", [None] * len(kdates))[idx] if idx < len(s.get("KClose", [])) else None,
                "change_pct": s.get("ChangePct"),
                "volume": s.get("KVolume", [None] * len(kdates))[idx] if idx < len(s.get("KVolume", [])) else None,
                "trade_date": kdates[idx],
            }
    return None


def diff_close(old, new, tolerance=TOLERANCE["close"]):
    """对比收盘价"""
    if old is None or new is None:
        return {"old": old, "new": new, "delta": None, "within_tolerance": True}
    delta = abs(float(old) - float(new))
    return {"old": float(old), "new": float(new), "delta": round(delta, 4),
            "within_tolerance": delta <= tolerance}


def diff_volume(old_volume, new_volume):
    """对比成交量（统一为股单位，容差 1 万手 = 10,000,000 股）"""
    if old_volume is None or new_volume is None:
        return {"old": old_volume, "new": new_volume, "delta": None,
                "within_tolerance": True}
    delta = abs(int(old_volume) - int(new_volume))
    tolerance_vol = TOLERANCE["volume_wan_shou"] * 1_000_000
    return {"old": int(old_volume), "new": int(new_volume), "delta": delta,
            "within_tolerance": delta <= tolerance_vol}


def diff_change_pct(old, new, tolerance=TOLERANCE["change_pct"]):
    if old is None or new is None:
        return {"old": old, "new": new, "delta": None, "within_tolerance": True}
    delta = abs(float(old) - float(new))
    return {"old": float(old), "new": float(new), "delta": round(delta, 4),
            "within_tolerance": delta <= tolerance}


def write_diff_log(entry):
    """追加 shadow diff 日志"""
    os.makedirs(str(LOG_DIR), exist_ok=True)
    with open(DIFF_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def run_shadow(code, name, ds, target_date=None):
    """对单只股票运行 shadow diff。

    target_date: YYYYMMDD 格式（来自 --date）。必须真实参与比对。
    """
    if target_date is None:
        target_date = datetime.now().strftime("%Y%m%d")
    date_dash = f"{target_date[:4]}-{target_date[4:6]}-{target_date[6:8]}"

    result = {
        "code": code,
        "name": name,
        "target_date": target_date,
        "timestamp": _now_iso(),
        "checks": [],
        "is_pass": True,
        "core_pass": True,
        "has_non_core_block": False,
        "known_degraded_count": 0,
    }

    # ================================================================
    #  1. get_kline shadow — 按 --date 比对
    # ================================================================
    legacy_k = get_legacy_kline(code)
    uds_k = ds.get_kline(code, 120)

    l_kline_rec = find_record_by_date(legacy_k, target_date) if legacy_k else None
    u_kline_data = uds_k.get("data", [])
    u_kline_rec = find_record_by_date(u_kline_data, target_date) if isinstance(u_kline_data, list) else None

    check_k = {
        "interface": "get_kline",
        "core": True,
        "legacy_source": "kline_cache" if legacy_k else "unavailable",
        "uds_source": uds_k.get("data_source", "?"),
        "uds_status": uds_k.get("status", "?"),
        "target_date": date_dash,
        "legacy_date_found": l_kline_rec is not None,
        "uds_date_found": u_kline_rec is not None,
        "legacy_rows": len(legacy_k) if legacy_k else 0,
        "uds_rows": len(u_kline_data) if isinstance(u_kline_data, list) else 0,
        "diff": {},
        "is_pass": True,
    }

    if l_kline_rec and u_kline_rec:
        check_k["diff"]["close"] = diff_close(
            l_kline_rec.get("close"), u_kline_rec.get("close")
        )
        check_k["diff"]["volume"] = diff_volume(
            l_kline_rec.get("volume"), u_kline_rec.get("volume")
        )
        check_k["is_pass"] = (
            all(d.get("within_tolerance", True) for d in check_k["diff"].values())
            if check_k["diff"] else True
        )
    elif l_kline_rec or u_kline_rec:
        # 只有一侧找到记录 → 数据不完整，不 PASS
        check_k["is_pass"] = False
        check_k["date_missing"] = False
        check_k.setdefault("warnings", []).append(
            f"目标日期 {date_dash} 仅在 {'legacy' if l_kline_rec else 'UDS'} 侧找到"
        )
    else:
        # 两侧都找不到目标日期 → 数据缺口，不 PASS
        check_k["is_pass"] = False
        check_k["date_missing"] = True
        check_k.setdefault("warnings", []).append(
            f"目标日期 {date_dash} 在 legacy 和 UDS 中均未找到"
        )

    result["checks"].append(check_k)
    if not check_k["is_pass"]:
        result["is_pass"] = False
        result["core_pass"] = False

    # ================================================================
    #  2. get_quote shadow — 校验 trade_date 与 --date 一致
    # ================================================================
    legacy_q = get_legacy_quote(code)
    uds_q = ds.get_quote(code)

    legacy_quote_date = legacy_q.get("trade_date", "") if legacy_q else ""
    legacy_date_match = (legacy_quote_date.replace("-", "") == target_date) if legacy_quote_date else False

    uds_quote_data = uds_q.get("data", {})
    uds_quote_date = uds_quote_data.get("trade_date", "") if isinstance(uds_quote_data, dict) else ""
    uds_date_match = (uds_quote_date.replace("-", "") == target_date) if uds_quote_date else False

    check_q = {
        "interface": "get_quote",
        "core": True,
        "legacy_source": "data_full" if legacy_q else "unavailable",
        "uds_source": uds_q.get("data_source", "?"),
        "uds_status": uds_q.get("status", "?"),
        "target_date": date_dash,
        "legacy_trade_date": legacy_quote_date,
        "uds_trade_date": uds_quote_date,
        "legacy_date_matches_target": legacy_date_match,
        "uds_date_matches_target": uds_date_match,
        "date_mismatch": False,
        "diff": {},
        "is_pass": True,
    }

    # 日期匹配检查 — 日期不匹配则 is_pass=False
    date_ok = True
    if legacy_q and not legacy_date_match:
        check_q["date_mismatch"] = True
        date_ok = False
        check_q.setdefault("warnings", []).append(
            f"legacy 报价日期 {legacy_quote_date} 与 --date {date_dash} 不一致"
        )
    if isinstance(uds_quote_data, dict) and uds_quote_date and not uds_date_match:
        check_q["date_mismatch"] = True
        date_ok = False
        check_q.setdefault("warnings", []).append(
            f"UDS 报价日期 {uds_quote_date} 与 --date {date_dash} 不一致"
        )

    if legacy_q and isinstance(uds_quote_data, dict) and date_ok:
        # 日期已匹配，才做数值 diff
        check_q["diff"]["close"] = diff_close(
            legacy_q.get("close"), uds_quote_data.get("close")
        )
        check_q["diff"]["change_pct"] = diff_change_pct(
            legacy_q.get("change_pct"), uds_quote_data.get("change_pct")
        )
        value_pass = (
            all(d.get("within_tolerance", True) for d in check_q["diff"].values())
            if check_q["diff"] else True
        )
        check_q["is_pass"] = value_pass
    else:
        check_q["is_pass"] = False

    result["checks"].append(check_q)
    if not check_q["is_pass"]:
        result["is_pass"] = False
        result["core_pass"] = False

    # ================================================================
    #  3. 非核心接口 — 记录 data_source/status，BLOCK 不得计为 PASS
    # ================================================================
    for iface in sorted(NON_CORE_INTERFACES):
        method = getattr(ds, iface, None)
        if not method:
            continue
        try:
            if iface == "get_score_history":
                r = method(code, "2026-01-01", "2026-06-09")
            elif iface == "get_financials":
                r = method(code, 2)
            elif iface == "get_macro":
                r = method("CPI", 3)
            elif iface == "compare_current_vs_historical":
                r = method(code, "close", 60)
            elif iface == "compute_factor_ic":
                r = method("TotalScore", 20)
            elif iface == "get_max_drawdown":
                r = method(code)
            elif iface == "get_volatility_percentile":
                r = method(code, 20)
            elif iface == "export_factor_panel":
                r = method([code], "2026-01-01", "2026-06-09")
            else:
                r = method(code)

            uds_status = r.get("status", "?")
            is_pass = uds_status != "BLOCK"
            if not is_pass:
                result["has_non_core_block"] = True
                result["is_pass"] = False

            result["known_degraded_count"] += 1
            result["checks"].append({
                "interface": iface,
                "core": False,
                "known_degraded": True,
                "legacy_source": "N/A",
                "uds_source": r.get("data_source", "?"),
                "uds_status": uds_status,
                "is_pass": is_pass,
            })
        except Exception as e:
            result["known_degraded_count"] += 1
            result["checks"].append({
                "interface": iface,
                "core": False,
                "known_degraded": True,
                "legacy_source": "N/A",
                "uds_source": "error",
                "uds_status": str(e)[:60],
                "is_pass": False,
            })
            result["has_non_core_block"] = True
            result["is_pass"] = False

    # 写日志
    write_diff_log(result)
    return result


def format_text(result):
    lines = []
    lines.append(f"\n{'='*60}")
    lines.append(f" {result['name']}({result['code']}) | Shadow Diff ({result.get('target_date','?')})")
    lines.append(f"{'='*60}")
    lines.append(f"  核心接口: {'PASS' if result['core_pass'] else 'WARN'}")
    if result["has_non_core_block"]:
        lines.append(f"  非核心: WARN (有 BLOCK)")
    lines.append(f"  known_degraded 接口数: {result['known_degraded_count']}")
    for c in result["checks"]:
        if c.get("core"):
            ci = "✅" if c["is_pass"] else "⚠️"
            lines.append(f"  {ci} [{c['interface']}] legacy={c['legacy_source']} → UDS={c['uds_source']} (status={c['uds_status']})")
            lines.append(f"     date={c.get('target_date','?')} legacy_found={c.get('legacy_date_found','?')} uds_found={c.get('uds_date_found','?')}")
            if c.get("date_missing"):
                lines.append(f"     ❌ 目标日期 {c.get('target_date','')} 在两侧均未找到 — core FAIL")
            if c.get("date_mismatch"):
                lines.append(f"     ❌ 报价日期与目标日期不一致 — core FAIL")
            if c.get("warnings"):
                for w in c["warnings"]:
                    lines.append(f"     ⚠ {w}")
            if c.get("diff"):
                for k, v in c["diff"].items():
                    tol_icon = "✓" if v.get("within_tolerance") else "✗"
                    lines.append(f"     {k}: old={v.get('old')} new={v.get('new')} delta={v.get('delta')} [{tol_icon}]")
        else:
            ci = "✅" if c["is_pass"] else "⚠️"
            lines.append(f"  {ci} [{c['interface']}] → {c['uds_source']} (status={c['uds_status']})")
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description="Shadow diff 自动化验证（v1.1）")
    parser.add_argument("--date", required=True, help="交易日 YYYYMMDD")
    parser.add_argument("--code", help="限单只股票")
    parser.add_argument("--all-stocks", action="store_true", help="验证全部重点股票")
    parser.add_argument("--json", action="store_true", help="JSON 格式输出")
    args = parser.parse_args()

    ds = UnifiedDataSource()

    # 股票池
    stocks = []
    if args.code:
        stocks = [(args.code, "")]
    elif args.all_stocks:
        stocks = load_stock_pool()
    if not stocks:
        print("ERROR: 指定 --code 或 --all-stocks")
        return 2

    results = []
    all_core_pass = True
    has_non_core_block = False
    for code, name in stocks:
        r = run_shadow(code, name, ds, target_date=args.date)
        results.append(r)
        if not r["core_pass"]:
            all_core_pass = False
        if r["has_non_core_block"]:
            has_non_core_block = True

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        for r in results:
            print(format_text(r))
        core_pass_count = sum(1 for r in results if r["core_pass"])
        total = len(results)
        block_count = sum(1 for r in results if r["has_non_core_block"])
        print(f"\nCORE PASS: {core_pass_count}/{total} | 非核心 BLOCK: {block_count} | {'CORE ALL PASS' if all_core_pass else 'CORE HAS WARN'}")

    if not all_core_pass or has_non_core_block:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
