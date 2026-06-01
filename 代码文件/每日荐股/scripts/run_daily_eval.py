#!/usr/bin/env python3
"""run_daily_eval.py — 每日荐股后评估统一入口。

编排 backfill_returns.py → post_eval_engine.py，确保 eval_result JSON 落地。

用法:
    python3 run_daily_eval.py --date 2026-05-29
    python3 run_daily_eval.py --date 20260529 --dry-run

退出码: 0=正常 1=告警(非致命) 2=数据不足/脚本错误
"""
import argparse, os, subprocess, sys
from pathlib import Path

ROOT = str(Path(__file__).resolve().parent.parent.parent.parent)
BACKFILL = os.path.join(ROOT, "代码文件", "tools", "backfill_returns.py")
EVAL_ENGINE = os.path.join(ROOT, "代码文件", "每日荐股", "分析逻辑", "post_eval_engine.py")
EVAL_DIR = os.path.join(ROOT, "每日荐股", "事后评估")


def norm_date(s):
    c = s.replace("-", "").strip()
    if len(c) != 8: raise ValueError("Invalid date: {}".format(s))
    return c, "{}-{}-{}".format(c[:4], c[4:6], c[6:])


def run(cmd, label):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=300, cwd=ROOT)
        return r.returncode, r.stdout, r.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "{} TIMEOUT".format(label)
    except Exception as e:
        return -1, "", "{} ERROR: {}".format(label, e)


def check_outputs(dc):
    missing = []
    for f, n in [(os.path.join(EVAL_DIR, "eval_result_{}.json".format(dc)), "eval_result JSON"),
                  (os.path.join(EVAL_DIR, "records.csv"), "records.csv"),
                  (os.path.join(EVAL_DIR, "summary.csv"), "summary.csv")]:
        if not os.path.exists(f): missing.append(n)
    return missing


def main():
    p = argparse.ArgumentParser(description="每日荐股后评估统一入口")
    p.add_argument("--date", required=True)
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args()

    try:
        dc, df = norm_date(a.date)
    except ValueError as e:
        print("ERROR: {}".format(e), file=sys.stderr); return 2

    if a.dry_run:
        print("[dry-run] {}: {} --date {} → {} --date {}".format(df, BACKFILL, dc, EVAL_ENGINE, df))
        return 0

    alerts = 0
    for step, script, arg in [("backfill", BACKFILL, dc), ("post_eval", EVAL_ENGINE, df)]:
        if not os.path.exists(script):
            print("FATAL: {} 不存在".format(script), file=sys.stderr); return 2
        rc, out, err = run(["python3", script, "--date", arg], step)
        if rc < 0:
            print("FATAL: {}失败\n{}".format(step, err[:300]), file=sys.stderr); return 2
        if step == "post_eval": alerts = rc

    missing = check_outputs(dc)
    if missing:
        print("FATAL: 产物缺失: {}".format(", ".join(missing)), file=sys.stderr); return 2

    ej = os.path.join(EVAL_DIR, "eval_result_{}.json".format(dc))
    print("{} OK: eval={:.0f}K rec={:.0f}K sum={:.0f}K alerts={}".format(
        df, os.path.getsize(ej)/1024, os.path.getsize(os.path.join(EVAL_DIR, "records.csv"))/1024,
        os.path.getsize(os.path.join(EVAL_DIR, "summary.csv"))/1024, alerts))
    return 0 if alerts == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
