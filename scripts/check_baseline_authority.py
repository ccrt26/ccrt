#!/usr/bin/env python3
"""
P0-A: Baseline 权威闸门 — 检查日报引用的 baseline 是否与基线注册表一致。

用途:
  确保每日报告引用的 baseline_id 指向注册表中当前有效的唯一基线。
  发现 baseline_id 不匹配、多有效基线、无有效基线、关键价位口径混用等问题。

用法:
  python3 scripts/check_baseline_authority.py --code 600114 --name 东睦股份 --date 20260602
  python3 scripts/check_baseline_authority.py --all --date 20260602
  python3 scripts/check_baseline_authority.py --rebuild-registry

退出码:
  0 = PASS (所有检查通过)
  1 = 脚本异常 (参数错误/文件缺失/IO错误)
  2 = BLOCK (至少一项检查未通过)
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = PROJECT_ROOT / "00_项目地基" / "02_权威注册表" / "baseline_registry.json"
BASELINE_DIR = PROJECT_ROOT / "重点股票" / "基线"
REPORT_DIR = PROJECT_ROOT / "重点股票" / "股票报告"
PIGEON_CONFIG = PROJECT_ROOT / "代码文件" / "信鸽信息采集" / "pigeon_config.json"

# ============================================================
# 辅助函数
# ============================================================

def compact_to_dashed(date_str: str) -> str:
    """将 20260602 转为 2026-06-02"""
    d = date_str.replace("-", "")
    if len(d) != 8:
        raise ValueError(f"日期格式非法: {date_str}")
    return f"{d[:4]}-{d[4:6]}-{d[6:8]}"


def dashed_to_compact(date_str: str) -> str:
    """将 2026-06-02 转为 20260602"""
    return date_str.replace("-", "")


def parse_date(date_str: str) -> date:
    """解析日期字符串，支持 20260602 和 2026-06-02"""
    d = date_str.replace("-", "")
    if len(d) != 8:
        raise ValueError(f"日期格式非法: {date_str}")
    return datetime.strptime(d, "%Y%m%d").date()


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_text(path):
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="ignore")


# ============================================================
# Registry 加载与重建
# ============================================================

def load_registry() -> dict:
    """从注册表文件加载"""
    if not REGISTRY_PATH.exists():
        print(f"ERROR: 注册表文件不存在: {REGISTRY_PATH}")
        print("请先运行 python3 scripts/check_baseline_authority.py --rebuild-registry")
        sys.exit(1)
    return load_json(REGISTRY_PATH)


def rebuild_registry() -> dict:
    """从 重点股票/基线/ 重建注册表"""
    bl_files = sorted(BASELINE_DIR.glob("*.json"))
    entries = []

    for fpath in bl_files:
        try:
            d = load_json(fpath)
        except Exception as e:
            print(f"WARN: 跳过 {fpath.name}: {e}")
            continue

        code = d.get("stock_code", "")
        name = d.get("stock_name", "")
        bid = d.get("baseline_id", "")
        bdate = d.get("baseline_date", "")
        vuntil = d.get("valid_until", "")

        # 确定状态
        status = "active"
        if vuntil:
            try:
                vu = datetime.strptime(vuntil, "%Y-%m-%d").date()
                if vu < date.today():
                    status = "expired"
            except ValueError:
                pass

        # 收集关键价位（兼容多命名）
        kf = {}
        for src_field in [
            "key_support_price", "support_price",
            "key_pressure_price", "pressure_price",
            "stop_loss_price", "target_price",
            "position_cap", "position_cap_baseline",
        ]:
            val = d.get(src_field)
            if val is not None:
                kf[src_field] = val

        # 嵌套 key_levels.S1/S2/S3/R1/R2/R3/stop_loss_new/stop_loss_held
        kl = d.get("key_levels", {})
        if kl and isinstance(kl, dict):
            for subk in ["S1", "S2", "S3", "R1", "R2", "R3", "stop_loss_new", "stop_loss_held"]:
                sv = kl.get(subk)
                if sv is not None:
                    kf[subk] = sv

        thesis = d.get("core_thesis", "")
        rf = d.get("risk_flags", {})
        risk = rf.get("overall_risk_level", "") if isinstance(rf, dict) else ""

        entry = {
            "stock_code": code,
            "stock_name": name,
            "baseline_id": bid,
            "baseline_file": str(fpath.relative_to(PROJECT_ROOT)),
            "baseline_date": bdate,
            "valid_until": vuntil,
            "status": status,
            "source_type": "weekly_baseline",
            "strategy_version": d.get("strategy_version", ""),
        }
        if kf:
            entry["key_fields"] = kf
        if thesis:
            entry["core_thesis"] = thesis[:200]
        if risk:
            entry["overall_risk_level"] = risk

        entries.append(entry)

    from datetime import datetime as dt_now
    registry = {
        "registry_version": "1.0",
        "generated_at": dt_now.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "source_dir": str(BASELINE_DIR.relative_to(PROJECT_ROOT)),
        "entries": entries,
    }

    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(REGISTRY_PATH, "w", encoding="utf-8") as f:
        json.dump(registry, f, ensure_ascii=False, indent=2)

    print(f"注册表重建完成: {REGISTRY_PATH}")
    print(f"  基线总数: {len(entries)}")
    active_count = sum(1 for e in entries if e["status"] == "active")
    expired_count = sum(1 for e in entries if e["status"] == "expired")
    print(f"  活跃: {active_count} | 过期: {expired_count}")
    return registry


# ============================================================
# 基线查找
# ============================================================

def find_current_baseline(registry: dict, stock_code: str, trade_date: date) -> list:
    """从注册表中找股票在指定日期的有效基线。
    条件：baseline_date <= trade_date <= valid_until AND status != deprecated
    返回匹配条目列表 (可能0/1/多)"""
    matched = []
    for entry in registry.get("entries", []):
        if entry.get("stock_code") != stock_code:
            continue
        if entry.get("status") == "deprecated":
            continue

        bdate_s = entry.get("baseline_date", "")
        vuntil_s = entry.get("valid_until", "")
        try:
            bd = datetime.strptime(bdate_s, "%Y-%m-%d").date() if bdate_s else None
            vu = datetime.strptime(vuntil_s, "%Y-%m-%d").date() if vuntil_s else None
        except ValueError:
            continue

        if bd and bd > trade_date:
            continue
        if vu and vu < trade_date:
            continue

        matched.append(entry)

    return matched


# ============================================================
# 日报解析
# ============================================================

def find_report_file(code: str, name: str, date_compact: str, ext: str) -> Path:
    """找到日报文件路径。ext = '.json' 或 '.md'"""
    report_subdir = REPORT_DIR / f"{name}({code})"
    return report_subdir / f"{name}({code})日报_{date_compact}{ext}"


def extract_baseline_id_from_md(md_text: str) -> str:
    """从 MD 文件头部提取 baseline_id。
    格式: baseline_id：600114_deep_20260529_v1.4"""
    # 尝试多种分隔符和格式
    patterns = [
        r'baseline_id[：:]\s*([^\s\|\)\]]+)',
        r'baseline_id[：:]\s*([^\s]+?)(?:\s*\||\s*\n|$)',
    ]
    for pat in patterns:
        m = re.search(pat, md_text)
        if m:
            return m.group(1).strip()
    return ""


def extract_key_prices_from_md(md_text: str) -> dict:
    """从MD中提取关键价位。支持多种常见格式。

    支持的格式示例:
      - S1(7.25)
      - | S1支撑 | 7.25元 | 守住 | 未破 |
      - | 新仓止损 | 7.03元(S1下方3%) |
      - | 已持仓止损 | 6.89元 |
      - **新仓止损** | 7.03元(S1下方3%) |
      - S1支撑：7.25
    """
    prices = {}

    # ---- S1 ----
    s1 = None
    # 格式A: S1(7.25)
    m = re.search(r'S1\(([\d.]+)\)', md_text)
    if m: s1 = float(m.group(1))
    # 格式B: | S1支撑 | 7.25元 |
    if s1 is None:
        m = re.search(r'S1[支撑]*\s*\|\s*([\d.]+)', md_text)
        if m: s1 = float(m.group(1))
    # 格式C: S1支撑：7.25
    if s1 is None:
        m = re.search(r'S1[支撑]*[：:]*\s*([\d.]+)', md_text)
        if m: s1 = float(m.group(1))
    if s1 is not None:
        prices['S1'] = s1

    # ---- R1 ----
    r1 = None
    # 格式A: R1(8.87)
    m = re.search(r'R1\(([\d.]+)\)', md_text)
    if m: r1 = float(m.group(1))
    # 格式B: | R1压力 | 8.87元 |
    if r1 is None:
        m = re.search(r'R1[压力]*\s*\|\s*([\d.]+)', md_text)
        if m: r1 = float(m.group(1))
    # 格式C: R1压力：8.87
    if r1 is None:
        m = re.search(r'R1[压力]*[：:]*\s*([\d.]+)', md_text)
        if m: r1 = float(m.group(1))
    if r1 is not None:
        prices['R1'] = r1

    # ---- 新仓止损 ----
    sl_new = None
    # 格式A: | **新仓止损** | 7.03元(S1下方3%) |
    m = re.search(r'(?:\*\*)?新仓止损(?:\*\*)?\s*\|\s*([\d.]+)', md_text)
    if m: sl_new = float(m.group(1))
    # 格式B: 新仓止损：7.03
    if sl_new is None:
        m = re.search(r'新仓止损[：:]*\s*([\d.]+)', md_text)
        if m: sl_new = float(m.group(1))
    if sl_new is not None:
        prices['stop_loss_new'] = sl_new

    # ---- 已持仓止损 ----
    sl_held = None
    # 格式A: | **已持仓止损** | 6.89元 |
    m = re.search(r'(?:\*\*)?已持仓止损(?:\*\*)?\s*\|\s*([\d.]+)', md_text)
    if m: sl_held = float(m.group(1))
    # 格式B: 已持仓止损：6.89
    if sl_held is None:
        m = re.search(r'已持仓止损[：:]*\s*([\d.]+)', md_text)
        if m: sl_held = float(m.group(1))
    if sl_held is not None:
        prices['stop_loss_held'] = sl_held

    return prices


# ============================================================
# 股票池获取
# ============================================================

def get_stock_pool() -> list:
    """从 pigeon_config.json 获取股票池。失败时返回空列表，由调用方 fallback。"""
    if not PIGEON_CONFIG.exists():
        print(f"WARN: 股票池配置文件不存在: {PIGEON_CONFIG}")
        print("WARN: 尝试从 重点股票/股票报告/ 目录解析...")
        return []

    cfg = load_json(PIGEON_CONFIG)
    stocks = cfg.get("target_stocks", []) or cfg.get("stocks", [])
    if not stocks:
        print("WARN: pigeon_config.json 中无 target_stocks 或 stocks")
        print("WARN: 尝试从 重点股票/股票报告/ 目录解析...")
        return []

    result = []
    for s in stocks:
        code = str(s.get("code") or s.get("Code", ""))
        name = s.get("name") or s.get("Name", "")
        if code and name:
            result.append((code, name))
    return result


def get_stock_pool_from_reports() -> list:
    """从 重点股票/股票报告/ 子目录解析股票池"""
    stocks = []
    if not REPORT_DIR.exists():
        return stocks
    for subdir in sorted(REPORT_DIR.iterdir()):
        if not subdir.is_dir():
            continue
        # 解析 "名称(代码)" 格式
        m = re.match(r'(.+)\((\d{6})\)', subdir.name)
        if m:
            stocks.append((m.group(2), m.group(1)))
    return stocks


# ============================================================
# 核心检查逻辑
# ============================================================

def check_one(code: str, name: str, trade_date_str: str, registry: dict, verbose: bool = True) -> dict:
    """检查单只股票。返回检查结果字典。"""
    result = {
        "stock_code": code,
        "stock_name": name,
        "trade_date": trade_date_str,
        "expected_baseline_id": "",
        "actual_sidecar_baseline_id": "",
        "actual_md_baseline_id": "",
        "result": "PASS",
        "issues": [],
    }

    date_compact = trade_date_str.replace("-", "")
    try:
        td = parse_date(trade_date_str)
    except ValueError as e:
        result["result"] = "BLOCK"
        result["issues"].append(f"日期格式错误: {e}")
        return result

    # 1. 找日报 sidecar
    sidecar_path = find_report_file(code, name, date_compact, ".json")
    md_path = find_report_file(code, name, date_compact, ".md")

    if not sidecar_path.exists():
        result["result"] = "BLOCK"
        result["issues"].append(f"日报sidecar不存在: {sidecar_path}")

    if not md_path.exists():
        result["result"] = "BLOCK"
        result["issues"].append(f"日报MD不存在: {md_path}")

    # 如果主要文件都不存在，提前返回
    if result["result"] == "BLOCK" and not sidecar_path.exists() and not md_path.exists():
        return result

    # 2. 从注册表找当前有效基线
    matched = find_current_baseline(registry, code, td)
    current = None  # 初始化，避免 0/多条时 UnboundLocalError

    if len(matched) == 0:
        result["result"] = "BLOCK"
        result["issues"].append(f"注册表中日期 {trade_date_str} 无有效基线")
    elif len(matched) > 1:
        result["result"] = "BLOCK"
        ids = [e["baseline_id"] for e in matched]
        result["issues"].append(f"注册表中存在 {len(matched)} 条有效基线: {ids}")
    else:
        current = matched[0]
        result["expected_baseline_id"] = current["baseline_id"]
        result["actual_sidecar_baseline_id"] = "（文件不存在）"
        result["actual_md_baseline_id"] = "（文件不存在）"

    # 3. 检查 sidecar baseline_id
    if sidecar_path.exists():
        try:
            sidecar = load_json(sidecar_path)
        except Exception as e:
            result["result"] = "BLOCK"
            result["issues"].append(f"sidecar JSON解析失败: {e}")
            sidecar = {}

        sidecar_bid = sidecar.get("baseline_id", "")
        result["actual_sidecar_baseline_id"] = sidecar_bid

        if current and sidecar_bid:
            if sidecar_bid != current["baseline_id"]:
                result["result"] = "BLOCK"
                result["issues"].append(
                    f"sidecar baseline_id='{sidecar_bid}' "
                    f"≠ 注册表当前基线 '{current['baseline_id']}'"
                )

    # 4. 检查 MD baseline_id
    if md_path.exists():
        md_text = load_text(md_path)
        md_bid = extract_baseline_id_from_md(md_text)
        result["actual_md_baseline_id"] = md_bid if md_bid else "（未找到）"

        if current and md_bid:
            if md_bid != current["baseline_id"]:
                result["result"] = "BLOCK"
                result["issues"].append(
                    f"MD baseline_id='{md_bid}' "
                    f"≠ 注册表当前基线 '{current['baseline_id']}'"
                )

    # 5. 检查 MD vs sidecar baseline_id 之间的一致性（即使 registry 中有 id）
    result_sidecar_bid = result.get("actual_sidecar_baseline_id", "")
    result_md_bid = result.get("actual_md_baseline_id", "")
    if result_sidecar_bid and result_md_bid and "（" not in result_sidecar_bid and "（" not in result_md_bid:
        if result_sidecar_bid != result_md_bid:
            result["result"] = "BLOCK"
            result["issues"].append(
                f"MD baseline_id='{result_md_bid}' "
                f"≠ sidecar baseline_id='{result_sidecar_bid}'"
            )

    # 6. 关键价位一致性检查（宽松版：只检查是否有明显矛盾）
    if current and current.get("key_fields") and md_path.exists():
        kf = current["key_fields"]
        md_prices = extract_key_prices_from_md(md_text if md_path.exists() else "")
        if md_prices:
            issues_before = len(result["issues"])
            for price_key, md_val in md_prices.items():
                if price_key == "S1" and kf.get("key_support_price"):
                    registry_val = kf["key_support_price"]
                    if registry_val > 0:
                        diff_pct = abs(md_val - registry_val) / registry_val
                        if diff_pct > 0.15:  # 差异 >15% 才报警
                            result["issues"].append(
                                f"关键价位不一致: MD S1={md_val} "
                                f"≠ 基线 key_support_price={registry_val} "
                                f"(差异{diff_pct*100:.0f}%)"
                            )
                if price_key == "R1" and kf.get("key_pressure_price"):
                    registry_val = kf["key_pressure_price"]
                    if registry_val > 0:
                        diff_pct = abs(md_val - registry_val) / registry_val
                        if diff_pct > 0.15:
                            result["issues"].append(
                                f"关键价位不一致: MD R1={md_val} "
                                f"≠ 基线 key_pressure_price={registry_val} "
                                f"(差异{diff_pct*100:.0f}%)"
                            )
                if price_key == "stop_loss_new" and kf.get("stop_loss_price"):
                    registry_val = kf["stop_loss_price"]
                    if registry_val > 0:
                        diff_pct = abs(md_val - registry_val) / registry_val
                        if diff_pct > 0.10:
                            # 检查是否有合法override依据（白皮书v3.6第82-86行、149-150行）
                            has_override = False
                            if sidecar_path.exists():
                                try:
                                    with open(sidecar_path) as sf:
                                        sc = json.load(sf)
                                    p0 = sc.get("p0_decision_card", {})
                                    if (p0.get("t1_action") or "").strip().lower() not in ("", "none", "n/a", "观望"):
                                        has_override = True
                                    if p0.get("triggered_position_cap") and p0["triggered_position_cap"] not in ("", "N/A", "不适用"):
                                        has_override = True
                                    if p0.get("key_buy_point") and p0["key_buy_point"] not in ("", "N/A", "不适用"):
                                        has_override = True
                                    if p0.get("new_position_stop_loss"):
                                        has_override = True
                                except Exception:
                                    pass
                            if not has_override:
                                result["issues"].append(
                                    f"止损价格不一致: MD stop_loss_new={md_val} "
                                    f"≠ 基线 stop_loss_price={registry_val} "
                                    f"(差异{diff_pct*100:.0f}%，且无合法override理由)"
                                )

            # 如果新增了关键价位问题，将 result 设为 BLOCK
            if len(result["issues"]) > issues_before and result["result"] == "PASS":
                result["result"] = "BLOCK"

    return result


# ============================================================
# 输出格式化
# ============================================================

def format_result(result: dict) -> str:
    """格式化单票结果"""
    lines = []
    code = result["stock_code"]
    name = result["stock_name"]
    date_str = result["trade_date"]
    lines.append(f"{'='*60}")
    lines.append(f" {name}({code}) | {date_str}")
    lines.append(f"{'='*60}")

    expected = result["expected_baseline_id"]
    sidecar = result["actual_sidecar_baseline_id"]
    md_bid = result["actual_md_baseline_id"]

    lines.append(f"  预期 baseline_id:          {expected or '(无)'}")
    lines.append(f"  sidecar baseline_id:       {sidecar or '(无)'}")
    lines.append(f"  MD baseline_id:            {md_bid or '(无)'}")
    lines.append(f"  结果:                      {result['result']}")

    if result["issues"]:
        lines.append(f"  问题 ({len(result['issues'])} 项):")
        for issue in result["issues"]:
            lines.append(f"    - {issue}")

    return "\n".join(lines) + "\n"


# ============================================================
# Main
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="P0-A: Baseline 权威闸门 — 检查日报 baseline_id 与注册表一致性"
    )
    parser.add_argument("--code", help="股票代码，如 600114")
    parser.add_argument("--name", help="股票名称，如 东睦股份")
    parser.add_argument("--date", help="交易日期，YYYYMMDD 或 YYYY-MM-DD")
    parser.add_argument("--all", action="store_true", help="检查全部重点股票")
    parser.add_argument("--rebuild-registry", action="store_true",
                        help="从 重点股票/基线/ 重建注册表")
    args = parser.parse_args()

    # --rebuild-registry 模式
    if args.rebuild_registry:
        rebuild_registry()
        return 0

    # 检查参数完整性
    if not args.date:
        parser.error("需要 --date 参数 (YYYYMMDD 或 YYYY-MM-DD)")

    # 加载注册表
    registry = load_registry()

    # --all 模式
    if args.all:
        stocks = get_stock_pool()
        if not stocks:
            stocks = get_stock_pool_from_reports()
        if not stocks:
            print("ERROR: 无法获取股票池（pigeon_config.json 不存在且股票报告目录为空）")
            return 1

        print(f"股票池: {len(stocks)} 只\n")
        all_pass = True
        results = []
        for code, name in stocks:
            res = check_one(code, name, args.date, registry, verbose=True)
            results.append(res)
            print(format_result(res))
            if res["result"] != "PASS":
                all_pass = False

        # 汇总
        pass_count = sum(1 for r in results if r["result"] == "PASS")
        block_count = sum(1 for r in results if r["result"] == "BLOCK")
        print(f"{'='*60}")
        print(f"  PASS: {pass_count} | BLOCK: {block_count} | TOTAL: {len(results)}")
        print(f"{'='*60}")

        if all_pass:
            print("\nBASELINE_AUTHORITY_ALL: PASS")
            return 0
        else:
            print("\nBASELINE_AUTHORITY_ALL: BLOCK")
            return 2

    # 单票模式
    if not args.code or not args.name:
        parser.error("单票模式需要 --code 和 --name，或使用 --all --date")

    result = check_one(args.code, args.name, args.date, registry)
    print(format_result(result))

    if result["result"] == "PASS":
        print("BASELINE_AUTHORITY: PASS")
        return 0
    else:
        print("BASELINE_AUTHORITY: BLOCK")
        return 2


if __name__ == "__main__":
    sys.exit(main())
