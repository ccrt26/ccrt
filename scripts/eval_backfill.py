#!/usr/bin/env python3
"""
后评估回填脚本 — T+1/T+3/T+5 eval_hooks 回填
用法:
  python3 scripts/eval_backfill.py --window t1    # T+1 回填
  python3 scripts/eval_backfill.py --window t3    # T+3 回填
  python3 scripts/eval_backfill.py --window t5    # T+5 回填（含综合判定+归因）
  python3 scripts/eval_backfill.py --weekly       # 周报输出
  python3 scripts/eval_backfill.py --list-pending # 列出待回填
"""

import json, os, sys, re
from datetime import datetime, date, timedelta

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EVAL_STORE = os.path.join(PROJECT_ROOT, "统一解读", "eval_hooks", "store")
WEEKLY_REPORT_DIR = os.path.join(PROJECT_ROOT, "统一解读", "eval_hooks", "weekly")
ERROR_CASE_DB = os.path.join(PROJECT_ROOT, "统一解读", "六库", "错误反例库_v1.0.md")
RULE_DB = os.path.join(PROJECT_ROOT, "统一解读", "六库", "统一解读规则库_v1.0.md")

os.makedirs(EVAL_STORE, exist_ok=True)
os.makedirs(WEEKLY_REPORT_DIR, exist_ok=True)


def list_pending_hooks():
    """列出所有 eval_hooks 文件中待回填的条目"""
    pending = []
    if not os.path.exists(EVAL_STORE):
        return pending
    for fn in sorted(os.listdir(EVAL_STORE)):
        if not fn.endswith(".json"):
            continue
        path = os.path.join(EVAL_STORE, fn)
        try:
            with open(path, "r", encoding="utf-8") as f:
                hook = json.load(f)
        except Exception:
            continue
        for window in ["t1", "t3", "t5"]:
            key = f"{window}_check"
            if hook.get(key, {}).get("result") == "待评估":
                check_date_str = hook[key].get("check_date", "")
                if check_date_str:
                    try:
                        cd = datetime.strptime(check_date_str, "%Y-%m-%d").date()
                        if cd <= date.today():
                            pending.append({"file": fn, "hook_id": hook.get("eval_hook_id"),
                                            "window": window, "check_date": check_date_str})
                    except ValueError:
                        pass
    return pending


def run_backfill(window="t1"):
    """执行指定窗口的回填"""
    today = date.today()
    key = f"{window}_check"
    results = {"window": window, "date": today.isoformat(), "processed": [], "errors": []}

    if not os.path.exists(EVAL_STORE):
        print(f"eval_hooks 存储目录不存在: {EVAL_STORE}")
        return results

    for fn in sorted(os.listdir(EVAL_STORE)):
        if not fn.endswith(".json"):
            continue
        path = os.path.join(EVAL_STORE, fn)
        try:
            with open(path, "r", encoding="utf-8") as f:
                hook = json.load(f)
        except Exception as e:
            results["errors"].append({"file": fn, "error": str(e)})
            continue

        ck = hook.get(key, {})
        if ck.get("result") != "待评估":
            continue

        # 检查是否到了回填日期
        check_date_str = ck.get("check_date", "")
        if not check_date_str:
            continue
        try:
            cd = datetime.strptime(check_date_str, "%Y-%m-%d").date()
        except ValueError:
            results["errors"].append({"file": fn, "error": f"日期格式非法: {check_date_str}"})
            continue
        if cd > today:
            continue  # 还没到回填日期

        # 标记为"待手动回填"（数据需从外部获取）
        # 实际运行时由玉夜提供数据，青山判定
        ck["result"] = "数据不足"
        ck["backfilled_at"] = datetime.now().isoformat()
        ck["note"] = f"自动标记: {window}窗口到期，等待数据回填"

        # 保存
        with open(path, "w", encoding="utf-8") as f:
            json.dump(hook, f, ensure_ascii=False, indent=2)

        results["processed"].append({"hook_id": hook.get("eval_hook_id"), "window": window})

    return results


def run_t5_comprehensive():
    """T+5 综合判定 + 失败归因"""
    today = date.today()
    results = {"window": "t5_comprehensive", "date": today.isoformat(), "judged": [], "failures": []}

    if not os.path.exists(EVAL_STORE):
        return results

    for fn in sorted(os.listdir(EVAL_STORE)):
        if not fn.endswith(".json"):
            continue
        path = os.path.join(EVAL_STORE, fn)
        try:
            with open(path, "r", encoding="utf-8") as f:
                hook = json.load(f)
        except Exception:
            continue

        # 只在 T+5 回填完成后做综合判定
        t5 = hook.get("t5_check", {})
        if t5.get("result") in ("待评估", "数据不足"):
            continue

        t1r = hook.get("t1_check", {}).get("result", "待评估")
        t3r = hook.get("t3_check", {}).get("result", "待评估")
        t5r = t5.get("result", "待评估")

        # 综合判定矩阵
        if t1r == "命中" and t3r == "命中" and t5r == "命中":
            verdict = "命中"
        elif t1r == "命中" and t3r == "命中" and t5r in ("部分命中", "失败"):
            verdict = "部分命中"
        elif t1r == "命中" and t3r == "失败":
            verdict = "失败"
        elif t1r == "失败":
            verdict = "失败"
        elif all(r in ("数据不足", "不可评估", "待评估") for r in [t1r, t3r, t5r]):
            verdict = "不可评估"
        else:
            verdict = "部分命中"

        hook["comprehensive_result"] = verdict
        hook["comprehensive_date"] = today.isoformat()

        # 失败归因
        if verdict == "失败":
            attribution = determine_attribution(hook)
            hook["failure_attribution"] = attribution
            results["failures"].append({
                "hook_id": hook.get("eval_hook_id"),
                "interpretation_id": hook.get("interpretation_id"),
                "attribution": attribution,
                "rule_update_candidate": hook.get("rule_update_candidate", False)
            })

        with open(path, "w", encoding="utf-8") as f:
            json.dump(hook, f, ensure_ascii=False, indent=2)

        results["judged"].append({"hook_id": hook.get("eval_hook_id"), "verdict": verdict})

    return results


def determine_attribution(hook):
    """失败归因决策树"""
    t1 = hook.get("t1_check", {})
    t5 = hook.get("t5_check", {})

    # 检查是否有数据问题标记
    for ck in [t1, hook.get("t3_check", {}), t5]:
        if "数据" in ck.get("note", "") or "缺失" in ck.get("note", ""):
            return "数据问题"

    # 检查是否有市场突变标记
    combined_note = " ".join([t1.get("note", ""), t5.get("note", "")])
    if "事件" in combined_note or "突变" in combined_note or "不可预见" in combined_note:
        return "市场突变"

    # 默认归因（需人工确认）
    confidence = hook.get("confidence", "MEDIUM")
    action = hook.get("action_bias", "NEUTRAL")
    if confidence == "LOW" and action in ("BUY", "SELL"):
        return "动作过强"
    if confidence == "HIGH" and action in ("BUY", "SELL"):
        return "规则问题"

    return "待进一步分析"


def run_weekly_report():
    """生成周度后评估摘要"""
    today = date.today()
    week_start = today - timedelta(days=today.weekday() + 1)  # 上周一
    week_end = today - timedelta(days=1)  # 昨天（周六出报告用周五）

    report = {
        "report_type": "后评估周报",
        "period": f"{week_start.isoformat()} 至 {week_end.isoformat()}",
        "generated_at": datetime.now().isoformat(),
        "summary": {"总评估数": 0, "命中": 0, "部分命中": 0, "失败": 0, "不可评估": 0},
        "failure_attribution": {},
        "rule_update_candidates": [],
        "signal_winrate_changes": []
    }

    if not os.path.exists(EVAL_STORE):
        return report

    for fn in sorted(os.listdir(EVAL_STORE)):
        if not fn.endswith(".json"):
            continue
        path = os.path.join(EVAL_STORE, fn)
        try:
            with open(path, "r", encoding="utf-8") as f:
                hook = json.load(f)
        except Exception:
            continue

        verdict = hook.get("comprehensive_result")
        if not verdict:
            continue

        report["summary"]["总评估数"] += 1
        if verdict in report["summary"]:
            report["summary"][verdict] += 1

        if verdict == "失败":
            attr = hook.get("failure_attribution", "未知")
            report["failure_attribution"][attr] = report["failure_attribution"].get(attr, 0) + 1
            if hook.get("rule_update_candidate"):
                report["rule_update_candidates"].append(hook.get("interpretation_id"))

    # 写入周报文件
    report_fn = f"后评估周报_{week_end.isoformat()}.json"
    report_path = os.path.join(WEEKLY_REPORT_DIR, report_fn)
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    return report


def main():
    import argparse
    parser = argparse.ArgumentParser(description="后评估回填脚本")
    parser.add_argument("--window", choices=["t1", "t3", "t5"], help="回填窗口")
    parser.add_argument("--weekly", action="store_true", help="生成周报")
    parser.add_argument("--list-pending", action="store_true", help="列出待回填")
    parser.add_argument("--json", action="store_true", help="JSON输出")
    args = parser.parse_args()

    if args.list_pending:
        pending = list_pending_hooks()
        if args.json:
            print(json.dumps(pending, ensure_ascii=False, indent=2))
        else:
            print(f"待回填: {len(pending)} 条")
            for p in pending:
                print(f"  {p['hook_id']} | {p['window']} | {p['check_date']}")
        return

    if args.weekly:
        report = run_weekly_report()
        if args.json:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            print(f"周报已生成: {report['period']}")
            print(f"总评估: {report['summary']}")
            if report['failure_attribution']:
                print(f"失败归因: {report['failure_attribution']}")
        return

    if args.window:
        if args.window == "t5":
            results = run_t5_comprehensive()
            if args.json:
                print(json.dumps(results, ensure_ascii=False, indent=2))
            else:
                print(f"窗口 t5: 综合判定 {len(results.get('judged',[]))} 条, 失败归因 {len(results.get('failures',[]))} 条")
        else:
            results = run_backfill(args.window)
            if args.json:
                print(json.dumps(results, ensure_ascii=False, indent=2))
            else:
                print(f"窗口 {args.window}: 处理 {len(results.get('processed',[]))} 条, 错误 {len(results.get('errors',[]))} 条")
        return

    # 默认: 运行所有到期窗口
    for w in ["t1", "t3", "t5"]:
        r = run_backfill(w) if w != "t5" else run_t5_comprehensive()
        processed = len(r.get("processed", r.get("judged", [])))
        errors = len(r.get("errors", []))
        if processed or errors:
            print(f"  {w}: {processed} processed, {errors} errors")


if __name__ == "__main__":
    main()
