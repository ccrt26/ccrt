#!/usr/bin/env python3
"""P0-I: 日报数据完整性检测——禁止有数据却写缺失/待确认"""
import argparse, json, re, sys
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parents[1]

BAD_PHRASES = [
    "待baseline确认", "待深度分析baseline确认", "深度分析baseline待引用",
    "无baseline参考", "质押/解禁待baseline引用",
    "大盘数据待收盘更新", "板块相位待确认",
    "信号样本不足，低样本信号不能单独触发操作",
    "待确认", "待更新", "默认不买。只有满足P0触发条件",
    "趋势信号", "量价信号", "板块数据待更新",
    "当前状态", "板块相位需等",
]

def load_json(path):
    with open(path, "r", encoding="utf-8-sig") as f:
        return json.load(f)

def compact(date):
    return date.replace("-", "")

def dashed(date):
    d = compact(date)
    return f"{d[:4]}-{d[4:6]}-{d[6:8]}"

def find_report_dir(code, name):
    return ROOT / "重点股票" / "股票报告" / f"{name}({code})"

def find_baseline(code, name, date):
    d = compact(date)
    report_dir = find_report_dir(code, name)
    p = report_dir / f"{name}({code})深度分析_baseline_{d}.json"
    if p.exists():
        return p
    base_dir = ROOT / "重点股票" / "基线"
    candidates = sorted(base_dir.glob(f"{name}({code})_baseline_*.json"), reverse=True)
    target = datetime.strptime(d, "%Y%m%d").date()
    for c in candidates:
        try:
            j = load_json(c)
            bd = datetime.strptime(j.get("baseline_date", "1900-01-01"), "%Y-%m-%d").date()
            vu = datetime.strptime(j.get("valid_until", "1900-01-01"), "%Y-%m-%d").date()
            if bd <= target <= vu:
                return c
        except Exception:
            continue
    return None

def latest_kline(code, date):
    p = ROOT / "代码文件" / "数据" / "kline_cache" / f"{code}.json"
    target = dashed(date)
    if p.exists():
        rows = load_json(p)
        for r in rows:
            if r.get("date") == target:
                return r, p
    # Fallback to data_full.json
    df_path = ROOT / "代码文件" / "数据" / "data_full.json"
    if df_path.exists():
        try:
            dfull = load_json(df_path)
            for s in dfull.get("Stocks", []) or []:
                c = str(s.get("Code") or s.get("code") or "")
                if c != code:
                    continue
                kdates = s.get("KDate") or []
                if target in kdates:
                    idx = kdates.index(target)
                    row = {
                        "date": target,
                        "open": s.get("KOpen", [None]*len(kdates))[idx] if idx < len(s.get("KOpen",[])) else None,
                        "high": s.get("KHigh", [None]*len(kdates))[idx] if idx < len(s.get("KHigh",[])) else None,
                        "low": s.get("KLow", [None]*len(kdates))[idx] if idx < len(s.get("KLow",[])) else None,
                        "close": s.get("KClose", [None]*len(kdates))[idx] if idx < len(s.get("KClose",[])) else None,
                        "volume": s.get("KVolume", [None]*len(kdates))[idx] if idx < len(s.get("KVolume",[])) else None,
                        "change_pct": s.get("ChangePct"),
                        "_source": str(df_path),
                    }
                    return row, df_path
        except Exception:
            pass
    return None, p

def latest_fund_flow(code):
    p = ROOT / "代码文件" / "数据" / "fund_flow_cache" / f"{code}.json"
    if not p.exists():
        return None, p
    rows = load_json(p)
    return rows[-1] if rows else None, p

def latest_margin(code):
    p = ROOT / "代码文件" / "数据" / "tushare" / "margin_detail" / f"{code}.json"
    if not p.exists():
        return None, p
    rows = load_json(p)
    return rows[0] if rows else None, p

def stock_sector_phase(code):
    scored = ROOT / "代码文件" / "数据" / "data_scored.json"
    if not scored.exists():
        return None
    j = load_json(scored)
    for bucket in ("AllStocks", "Recommendations", "VetoedStocks"):
        for s in j.get(bucket, []) or []:
            if str(s.get("Code") or s.get("code")) == code:
                if s.get("SectorPhase"):
                    return {"industry": s.get("Industry"), "phase": s.get("SectorPhase")}
    return None

def extract_text(path):
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="ignore")

def check_one(code, name, date_str):
    """Check a single stock, returns (passed: bool, issues: list)"""
    date = compact(date_str)
    report_dir = find_report_dir(code, name)
    md = report_dir / f"{name}({code})日报_{date}.md"
    sidecar = report_dir / f"{name}({code})日报_{date}.json"
    html = report_dir / f"{name}({code})日报_{date}.html"
    issues = []

    for p in (md, sidecar):
        if not p.exists():
            issues.append(f"文件缺失: {p}")

    md_text = extract_text(md)
    sidecar_text = extract_text(sidecar)
    html_text = extract_text(html)
    all_text = md_text + "\n" + sidecar_text + "\n" + html_text

    for phrase in BAD_PHRASES:
        if phrase in all_text:
            issues.append(f"禁止占位话术仍存在: {phrase}")

    baseline_path = find_baseline(code, name, date_str)
    if not baseline_path:
        issues.append("baseline 文件未找到")
    else:
        bl = load_json(baseline_path)
        if "baseline缺失" in sidecar_text:
            issues.append(f"baseline 已存在但 sidecar 标为缺失: {baseline_path}")
        kl = bl.get("key_levels", {})
        for k in ("R1", "S1", "stop_loss_new", "stop_loss_held"):
            v = kl.get(k)
            if v is not None and str(v) not in md_text:
                issues.append(f"baseline关键字段未进入MD: {k}={v}")
        if bl.get("position_cap") and str(bl.get("position_cap")) not in all_text:
            issues.append(f"baseline仓位上限未进入报告: {bl.get('position_cap')}")

    krow, kpath = latest_kline(code, date_str)
    if not krow:
        issues.append(f"K线源无目标日期行情: {kpath}")
    else:
        close = krow.get("close")
        if str(close) not in all_text:
            issues.append(f"kline收盘价未进入报告: close={close}")
        if sidecar.exists():
            sj = load_json(sidecar)
            delta_close = (sj.get("delta") or {}).get("close")
            if delta_close is not None and abs(float(delta_close) - float(close)) > 0.001:
                issues.append(f"sidecar delta.close与kline_cache不一致")

    ff, ffpath = latest_fund_flow(code)
    if ff:
        has_any = any(str(ff.get(k)) in all_text for k in ("super_large_net","large_net","medium_net","small_net","main_force_net","super_large_display","large_display"))
        if not has_any:
            issues.append(f"四档资金有缓存但报告未展示具体数值: {ffpath}")
    else:
        issues.append(f"四档资金单票缓存缺失: {ffpath}")

    mg, mgpath = latest_margin(code)
    if mg:
        if "融资T+1延迟" in all_text and str(mg.get("trade_date","")) not in all_text:
            issues.append(f"融资有记录但报告只写T+1延迟未披露最新日期: {mgpath}")
    else:
        if code == "300736":
            if "margin_detail/300736.json缺失" not in all_text and "margin_detail/300736.json 缺失" not in all_text:
                issues.append("300736融资文件缺失但未明确披露缺失路径")
        else:
            issues.append(f"融资数据文件缺失或为空: {mgpath}")

    sector = stock_sector_phase(code)
    if sector and sector.get("phase"):
        if sector["phase"] not in all_text:
            issues.append(f"板块相位有数据但未进入报告: {sector}")

    winrate_db = ROOT / "代码文件" / "数据" / "signal_winrate_db.json"
    if winrate_db.exists():
        signal_section = re.search(r"(?:## 八、信号|信号胜率)(.+?)(?:\n---|\n## 九、|\n## 十、)", md_text, re.S)
        sec = signal_section.group(1) if signal_section else ""
        if not re.search(r"样本.*?\d+|\d+.*?样本|sample", sec, re.I):
            issues.append("信号胜率段没有样本数，禁止泛写样本不足")

    # P0-K: sidecar必填字段检查
    if sidecar.exists():
        sj = load_json(sidecar)
        for field in ['baseline_id','sector_phase','fund_flow_4level','signal_winrate',
                       'role_interpretations','yaozi_integration','audit_u9','audit_u10','eval_hooks']:
            if field not in sj:
                issues.append(f"sidecar缺字段: {field}")
        sp = sj.get('sector_phase', {})
        if not sp.get('phase') or sp.get('phase') in ('待确认','待更新',''):
            issues.append("sidecar sector_phase.phase为空/待确认/待更新")
        eh = sj.get('eval_hooks', {})
        if not eh.get('t1_verify'):
            issues.append("sidecar eval_hooks.t1_verify为空")
        if not eh.get('t5_verify'):
            issues.append("sidecar eval_hooks.t5_verify为空")

    return len(issues) == 0, issues

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--code", required=False)
    ap.add_argument("--name", required=False)
    ap.add_argument("--date", required=False)
    ap.add_argument("--all-pool", action="store_true", help="检查全部重点股票")
    args = ap.parse_args()

    if args.all_pool:
        if not args.date:
            print("--all-pool 需要 --date")
            return 2
        # Read pigeon_config.json
        cfg = load_json(ROOT / "代码文件" / "信鸽信息采集" / "pigeon_config.json")
        stocks = cfg.get("target_stocks", []) or cfg.get("stocks", [])
        if not stocks:
            print("pigeon_config.json 无 target_stocks")
            return 2

        all_pass = True
        for s in stocks:
            code = str(s.get("code") or s.get("Code", ""))
            name = s.get("name") or s.get("Name", "")
            if not code or not name:
                continue
            passed, issues = check_one(code, name, args.date)
            if passed:
                print(f"{code} {name}: PASS")
            else:
                print(f"{code} {name}: BLOCK")
                for i in issues:
                    print(f"  - {i}")
                all_pass = False

        if all_pass:
            print("\nDAILY_DATA_COMPLETENESS --all-pool: PASS")
            return 0
        else:
            print("\nDAILY_DATA_COMPLETENESS --all-pool: BLOCK")
            return 2

    # Single stock mode
    if not all([args.code, args.name, args.date]):
        print("单票模式需要 --code --name --date，或使用 --all-pool --date")
        return 2
    passed, issues = check_one(args.code, args.name, args.date)
    if passed:
        print("DAILY_DATA_COMPLETENESS: PASS")
        return 0
    else:
        print("DAILY_DATA_COMPLETENESS: BLOCK")
        for i in issues:
            print(f"- {i}")
        return 2

if __name__ == "__main__":
    sys.exit(main())
