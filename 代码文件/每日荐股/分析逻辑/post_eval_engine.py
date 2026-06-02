#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
铁律量化 · 每日荐股后评估引擎 v1.0
=====================================
Code level: L1 — 策略/评分相关，涉及评分有效性判断与参数调整建议

对齐: 次日后评估白皮书 v1.6 + 每日荐股分析逻辑白皮书 v3.0
调度: daily_workflow.py --mode eval → run_daily_eval.py → post_eval_engine.py

用法:
  python3 post_eval_engine.py --date 2026-05-28          # 评估指定日荐股
  python3 post_eval_engine.py --date 2026-05-28 --verbose # 输出全量per_stock
  python3 post_eval_engine.py --date 2026-05-28 --dry-run # 预览不写入
"""
import argparse, csv, json, math, os, sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

ROOT = str(Path(__file__).resolve().parent.parent.parent.parent)
HISTORY_FILE = os.path.join(ROOT, "代码文件", "数据", "score_history.jsonl")
RECORDS_CSV = os.path.join(ROOT, "每日荐股", "事后评估", "records.csv")
SUMMARY_CSV = os.path.join(ROOT, "每日荐股", "事后评估", "summary.csv")
EVAL_OUTPUT = os.path.join(ROOT, "每日荐股", "事后评估")

# L0 helper — CSV 输出 (imported from same directory)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _eval_writer import write_records_csv, write_summary_csv

# ── 配置常量 ──
FLOATING_BENCHMARKS = {"强普涨":{"win_rate":0,"score_distinction":2},"普涨":{"win_rate":65,"score_distinction":15},"震荡":{"win_rate":55,"score_distinction":12},"普跌":{"win_rate":45,"score_distinction":10},"强普跌":{"win_rate":35,"score_distinction":8}}
DIM_CONFIG = {"tech":{"label":"技术面","max":20,"key":"S_Tech"},"money":{"label":"资金面","max":20,"key":"S_Money"},"fund":{"label":"基本面","max":15,"key":"S_Fund"},"news":{"label":"消息面","max":15,"key":"S_News"},"sector":{"label":"板块趋势","max":20,"key":"S_SectorTrend"}}
ALERT_THRESHOLDS = {"win_rate_warn":5,"miskill_rate":15,"misjudge_rate":20,"spearman_warn":0.1,"c8_false_kill":20,"veto_effectiveness":20}


def classify_market(hs300_chg):
    if hs300_chg > 3: return "强普涨"
    if hs300_chg > 1: return "普涨"
    if hs300_chg > -1: return "震荡"
    if hs300_chg > -3: return "普跌"
    return "强普跌"


def spearman_r(xs, ys):
    n = len(xs)
    if n < 3: return 0.0
    def rank(vals):
        sv = sorted(vals); rm = {v: float(i+1) for i, v in enumerate(sv)}
        cnt = defaultdict(int)
        for v in vals: cnt[v] += 1
        res = []
        for v in vals:
            if cnt[v] > 1:
                idx = [j for j, svj in enumerate(sv) if svj == v]
                res.append(sum(i+1 for i in idx) / len(idx))
            else: res.append(rm[v])
        return res
    rx, ry = rank(xs), rank(ys)
    d2 = sum((rx[i]-ry[i])**2 for i in range(n))
    return 1.0 - (6.0*d2)/(n*(n**2-1))


def load_records(target_date):
    if not os.path.exists(HISTORY_FILE):
        print(f"[eval] {HISTORY_FILE} 不存在", file=sys.stderr)
        return [], []
    records, all_recs = [], []
    with open(HISTORY_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line: continue
            try:
                rec = json.loads(line)
                all_recs.append(rec)
                if rec.get("date") == target_date: records.append(rec)
            except json.JSONDecodeError: continue
    return records, all_recs


def load_historical_records():
    if not os.path.exists(RECORDS_CSV): return []
    try:
        with open(RECORDS_CSV, "r", encoding="utf-8-sig") as f:
            return list(csv.DictReader(f))
    except (IOError, csv.Error): return []


def compute_core_metrics(recs, hs300_chg=0):
    """计算核心指标: 胜率、盈亏比、组合收益、超额收益、评分区分度"""
    total = len(recs)
    if total == 0:
        return {"total_recs": 0, "error": "no_records"}

    rets_t1 = [r.get("ret_t1") for r in recs]
    valid = [(r, ret) for r, ret in zip(recs, rets_t1) if ret is not None]

    if not valid:
        return {"total_recs": total, "error": "no_ret_t1_data"}

    wins = sum(1 for _, ret in valid if ret > 0)
    losses = sum(1 for _, ret in valid if ret < 0)
    win_rate = wins / len(valid) * 100
    total_profit = sum(ret for _, ret in valid if ret > 0)
    total_loss = abs(sum(ret for _, ret in valid if ret < 0))
    pl_ratio = total_profit / total_loss if total_loss > 0 else 0
    portfolio_return = sum(ret for _, ret in valid) / len(valid)
    excess_return = portfolio_return - hs300_chg

    market_stage = classify_market(hs300_chg)
    benchmark = FLOATING_BENCHMARKS.get(market_stage, FLOATING_BENCHMARKS["震荡"])
    benchmark_ok = win_rate >= benchmark["win_rate"]

    # 评分区分度: >=70分 vs <70分
    above70 = [(r, ret) for r, ret in valid if r.get("TotalScore", 0) >= 70]
    below70 = [(r, ret) for r, ret in valid if r.get("TotalScore", 0) < 70]
    above70_rate = sum(1 for _, ret in above70 if ret > 0) / len(above70) * 100 if above70 else 0
    below70_rate = sum(1 for _, ret in below70 if ret > 0) / len(below70) * 100 if below70 else 0
    score_dist_70 = above70_rate - below70_rate

    # Spearman: 总分 vs 次日收益
    scores = [r.get("TotalScore", 0) for r, _ in valid]
    rets = [ret for _, ret in valid]
    spearman_rho = spearman_r(scores, rets) if len(scores) >= 5 else 0

    return {
        "total_recs": total, "valid_recs": len(valid),
        "wins": wins, "losses": losses,
        "win_rate": round(win_rate, 1),
        "floating_benchmark": benchmark["win_rate"],
        "market_stage": market_stage,
        "benchmark_status": "达标" if benchmark_ok else "未达标",
        "profit_loss_ratio": round(pl_ratio, 2),
        "portfolio_return": round(portfolio_return, 2),
        "hs300_return": round(hs300_chg, 2),
        "excess_return": round(excess_return, 2),
        "score_distinction_70": round(score_dist_70, 1),
        "spearman_rho": round(spearman_rho, 3),
    }


def compute_v30_metrics(recs, valid_ret):
    """v3.0指标: C8拦截、A/B/C档、相位折扣"""
    total = len(recs)
    if total == 0:
        return {}

    # C8
    c8_blocked = [r for r in recs if r.get("c8_blocked", False)]
    c8_unblocked = [r for r in recs if not r.get("c8_blocked", False)]
    c8_correct = sum(1 for r in c8_blocked if (r.get("ret_t1") or 0) <= 0)
    c8_false = sum(1 for r in c8_blocked if (r.get("ret_t1") or 0) > 3)

    # Tier
    a_tier = [r for r in recs if r.get("tier") == "A"]
    non_a = [r for r in recs if r.get("tier") != "A"]
    a_wins = sum(1 for r in a_tier if (r.get("ret_t1") or 0) > 0)
    non_a_wins = sum(1 for r in non_a if (r.get("ret_t1") or 0) > 0)
    a_rate = a_wins / len(a_tier) * 100 if a_tier else 0
    non_a_rate = non_a_wins / len(non_a) * 100 if non_a else 0
    a_fill = min(len(a_tier), 5) / 5 * 100  # Top5仿真: A档占5席中的比例

    # Phase discount effectiveness
    phases = defaultdict(list)
    for r in recs:
        p = r.get("phase", "潜伏期")
        phases[p].append(r)

    discount_effect = {}
    for p, stocks in phases.items():
        if len(stocks) < 3:
            continue
        mis_count = sum(1 for s in stocks if (s.get("ret_t1") or 0) < -3)
        rate = mis_count / len(stocks) * 100
        discount_effect[p] = {"count": len(stocks), "misjudge_rate": round(rate, 1)}

    return {
        "c8_blocked_count": len(c8_blocked),
        "c8_correct_rate": round(c8_correct / len(c8_blocked) * 100, 1) if c8_blocked else 0,
        "c8_false_kill_rate": round(c8_false / len(c8_blocked) * 100, 1) if c8_blocked else 0,
        "a_tier_count": len(a_tier),
        "a_tier_fill_rate": round(a_fill, 1),
        "a_tier_win_rate": round(a_rate, 1),
        "non_a_tier_win_rate": round(non_a_rate, 1),
        "a_vs_non_a_gap": round(a_rate - non_a_rate, 1),
        "phase_discount_by_phase": discount_effect,
    }


def compute_dimension_misjudge(recs):
    """维度误判率: 各维度高分(>60%满分)但亏损>3%的比例 (v3.0维度)"""
    results = {}
    for dim_key, cfg in DIM_CONFIG.items():
        key = cfg["key"]
        threshold = cfg["max"] * 0.6
        high_score = [r for r in recs if r.get(key, 0) >= threshold]
        misjudged = [r for r in high_score if (r.get("ret_t1") or 0) < -3]
        rate = len(misjudged) / len(high_score) * 100 if high_score else 0
        results[cfg["label"]] = {
            "rate": round(rate, 1),
            "total": len(high_score),
            "misjudged": len(misjudged),
            "threshold": round(threshold, 1),
        }
    return results


def compute_dimension_corr(recs):
    """各维度 + 总分 与 ret_t1 的 Spearman 相关系数"""
    dims = {
        "总分": "TotalScore", "技术": "S_Tech", "资金": "S_Money",
        "基本面": "S_Fund", "消息": "S_News", "板块趋势": "S_SectorTrend",
    }
    corr = {}
    for label, key in dims.items():
        pairs = [(r.get(key, 0), r.get("ret_t1")) for r in recs
                 if r.get(key) is not None and r.get("ret_t1") is not None]
        if len(pairs) >= 5:
            xs = [p[0] for p in pairs]
            ys = [p[1] for p in pairs]
            corr[label] = round(spearman_r(xs, ys), 3)
        else:
            corr[label] = None
    return corr


def compute_veto_analysis(recs):
    """否决分析: 推荐池 vs 否决池"""
    passed = [r for r in recs if not r.get("veto_reason")]
    vetoed = [r for r in recs if r.get("veto_reason")]

    rec_wins = sum(1 for r in passed if (r.get("ret_t1") or 0) > 0)
    rec_rate = rec_wins / len(passed) * 100 if passed else 0

    veto_wins = sum(1 for r in vetoed if (r.get("ret_t1") or 0) > 0)
    veto_rate = veto_wins / len(vetoed) * 100 if vetoed else 0

    miskilled = [r for r in vetoed if (r.get("ret_t1") or 0) > 5]
    miskill_rate = len(miskilled) / len(vetoed) * 100 if vetoed else 0

    effectiveness = rec_rate - veto_rate

    return {
        "recommended_count": len(passed),
        "vetoed_count": len(vetoed),
        "recommended_win_rate": round(rec_rate, 1),
        "veto_win_rate": round(veto_rate, 1),
        "veto_effectiveness": round(effectiveness, 1),
        "miskill_rate": round(miskill_rate, 1),
        "miskill_count": len(miskilled),
        "miskill_stocks": [{"code": r["code"], "name": r.get("name", ""),
                           "reason": r.get("veto_reason", ""),
                           "ret_t1": r.get("ret_t1")} for r in miskilled[:5]],
    }


def compute_per_stock(recs):
    """逐股明细: 按评分降序"""
    sorted_recs = sorted(recs, key=lambda r: r.get("TotalScore", 0), reverse=True)
    result = []
    for r in sorted_recs:
        ret = r.get("ret_t1")
        # 误判维度判断
        misjudge_dim = None
        if ret is not None and ret < -3:
            for dim_key, cfg in DIM_CONFIG.items():
                key = cfg["key"]
                threshold = cfg["max"] * 0.6
                if r.get(key, 0) >= threshold:
                    misjudge_dim = cfg["label"]
                    break
        result.append({
            "code": r.get("code", ""),
            "name": r.get("name", ""),
            "score": r.get("TotalScore", 0),
            "tier": r.get("tier", "B"),
            "c8_blocked": r.get("c8_blocked", False),
            "phase": r.get("phase", ""),
            "rating": r.get("rating", ""),
            "change_pct": r.get("change_pct", 0),
            "ret_t1": round(ret, 2) if ret is not None else None,
            "ret_t3": round(r.get("ret_t3"), 2) if r.get("ret_t3") is not None else None,
            "ret_t5": round(r.get("ret_t5"), 2) if r.get("ret_t5") is not None else None,
            "misjudge_dim": misjudge_dim,
        })
    return result


def generate_alerts(core, v30, dim_misjudge, dim_corr, veto, hist_records):
    """L1阈值报警 + L2趋势预判"""
    alerts = []

    # L1: 胜率
    wr = core.get("win_rate", 0)
    bm = core.get("floating_benchmark", 55)
    if wr < bm - ALERT_THRESHOLDS["win_rate_warn"]:
        alerts.append({"level": "L1", "indicator": "win_rate",
                       "value": wr, "threshold": bm,
                       "action": f"胜率{wr}%低于浮动基准{bm}%，可能需要收紧推荐条件"})

    # L1: 否决误杀率
    mr = veto.get("miskill_rate", 0)
    if mr > ALERT_THRESHOLDS["miskill_rate"]:
        alerts.append({"level": "L1", "indicator": "veto_miskill",
                       "value": mr, "threshold": ALERT_THRESHOLDS["miskill_rate"],
                       "action": f"否决误杀率{mr}%>{ALERT_THRESHOLDS['miskill_rate']}%，审查否决阈值"})

    # L1: 维度误判率
    for dim_name, info in dim_misjudge.items():
        if info["rate"] > ALERT_THRESHOLDS["misjudge_rate"]:
            alerts.append({"level": "L1", "indicator": f"misjudge_{dim_name}",
                           "value": info["rate"], "threshold": ALERT_THRESHOLDS["misjudge_rate"],
                           "action": f"{dim_name}误判率{info['rate']}%>{ALERT_THRESHOLDS['misjudge_rate']}%，审查该维度评分逻辑"})

    # L1: Spearman
    sp = core.get("spearman_rho", 0)
    if sp < ALERT_THRESHOLDS["spearman_warn"]:
        alerts.append({"level": "L1", "indicator": "spearman_rho",
                       "value": sp, "threshold": ALERT_THRESHOLDS["spearman_warn"],
                       "action": "评分与次日收益Spearman<0.1，评分预测力极弱"})

    # L1: C8误杀
    c8_fk = v30.get("c8_false_kill_rate", 0)
    if c8_fk > ALERT_THRESHOLDS["c8_false_kill"]:
        alerts.append({"level": "L1", "indicator": "c8_false_kill",
                       "value": c8_fk, "threshold": ALERT_THRESHOLDS["c8_false_kill"],
                       "action": f"C8误杀率{c8_fk}%>{ALERT_THRESHOLDS['c8_false_kill']}%，建议上调C8阈值(>7%→>8%或>9%)"})

    # L1: 否决有效度
    ve = veto.get("veto_effectiveness", 0)
    if ve < ALERT_THRESHOLDS["veto_effectiveness"]:
        alerts.append({"level": "L1", "indicator": "veto_effectiveness",
                       "value": ve, "threshold": ALERT_THRESHOLDS["veto_effectiveness"],
                       "action": f"否决有效度{ve}%<{ALERT_THRESHOLDS['veto_effectiveness']}%，否决规则可能无效"})

    # L2: 趋势预判 (需要历史records)
    if hist_records and len(hist_records) >= 3:
        recent_wrs = []
        for row in hist_records[-5:]:
            try:
                recent_wrs.append(float(row.get("win_rate", 0)))
            except (ValueError, TypeError):
                pass
        if len(recent_wrs) >= 3 and all(recent_wrs[i] > recent_wrs[i+1] for i in range(len(recent_wrs)-1)):
            drop = recent_wrs[0] - recent_wrs[-1]
            if drop > 5:
                alerts.append({"level": "L2", "indicator": "win_rate_trend",
                               "value": f"{recent_wrs[-1]}%", "trend": f"连续{len(recent_wrs)}日下降, 累计降{drop:.1f}%",
                               "action": "趋势预判: 胜率可能即将跌破阈值，关注后续表现"})

    return alerts


def generate_param_suggestions(core, v30, dim_misjudge, veto, alerts):
    """参数校准建议 (白皮书v1.6 §5.1)"""
    suggestions = []

    # C8阈值
    if v30.get("c8_false_kill_rate", 0) > 20:
        suggestions.append({
            "param": "C8涨幅阈值", "current": ">7%",
            "suggested": ">8%", "confidence": "中",
            "reason": f"C8误杀率{v30['c8_false_kill_rate']}%偏高"
        })

    # 否决阈值
    if veto.get("miskill_rate", 0) > 15:
        suggestions.append({
            "param": "否决规则阈值", "current": "当前值",
            "suggested": "逐条审查", "confidence": "中",
            "reason": f"否决误杀率{veto['miskill_rate']}%超过15%阈值"
        })

    # 相位折扣
    for p, info in v30.get("phase_discount_by_phase", {}).items():
        if info.get("misjudge_rate", 0) > 30:
            suggestions.append({
                "param": f"相位折扣系数({p})",
                "current": {"潜伏期": 1.0, "主升调整": 0.75, "高潮期": 0.55, "衰退期": 0.45}.get(p, "?"),
                "suggested": "下调0.05",
                "confidence": "低",
                "reason": f"{p}阶段误判率{info['misjudge_rate']}%偏高，折扣可能不足"
            })

    # 评分区分度
    if core.get("score_distinction_70", 0) < 10 and core.get("spearman_rho", 0) < 0.1:
        suggestions.append({
            "param": "评分维度权重", "current": "v3.0权重",
            "suggested": "审查低相关维度", "confidence": "低",
            "reason": "评分区分度与Spearman双低，部分维度可能无预测力"
        })

    return suggestions


def main():
    parser = argparse.ArgumentParser(description="每日荐股后评估引擎 v1.0")
    parser.add_argument("--date", required=True, help="被评估的荐股日期 YYYY-MM-DD")
    parser.add_argument("--verbose", action="store_true", help="输出全量per_stock (默认仅top/bottom 10)")
    parser.add_argument("--dry-run", action="store_true", help="预览模式，不写入CSV")
    args = parser.parse_args()

    report_date = args.date

    print(f"[eval] 加载 {report_date} 评分数据...")
    recs, all_records = load_records(report_date)
    if not recs:
        print(f"[eval] {report_date} 无评分记录", file=sys.stderr); sys.exit(1)

    recommended = [r for r in recs if not r.get("veto_reason")]
    vetoed = [r for r in recs if r.get("veto_reason")]
    print(f"[eval] {len(recs)} 条 ({len(recommended)}推荐+{len(vetoed)}否决)")

    filled = sum(1 for r in recs if r.get("ret_t1") is not None)
    if filled == 0: print("[eval] WARNING: ret_t1全部为null，请先运行 backfill_returns.py")
    else: print(f"[eval] ret_t1回填: {filled}/{len(recs)} ({filled/len(recs)*100:.0f}%)")

    # 获取市场数据 (简化: 从score_history估算, 或设默认值)
    # 完整版需从data_full.json或API获取沪深300涨跌幅
    hs300_chg = 0.0  # 默认, 后续可接入市场数据API

    hist_records = load_historical_records()

    # ── 计算各项指标 ──
    core = compute_core_metrics(recommended, hs300_chg)
    v30 = compute_v30_metrics(recommended, [r for r in recommended if r.get("ret_t1") is not None])
    dim_misjudge = compute_dimension_misjudge(recommended)
    dim_corr = compute_dimension_corr(recommended)
    veto_analysis = compute_veto_analysis(recs)
    per_stock = compute_per_stock(recs)

    # 截断per_stock (默认top/bottom 10)
    if not args.verbose:
        per_stock = per_stock[:10] + (
            [{"_truncated": f"... {len(per_stock) - 20} 只省略，使用 --verbose 查看全量"}]
            if len(per_stock) > 20 else []
        ) + per_stock[-10:] if len(per_stock) > 20 else per_stock

    alerts = generate_alerts(core, v30, dim_misjudge, dim_corr, veto_analysis, hist_records)
    suggestions = generate_param_suggestions(core, v30, dim_misjudge, veto_analysis, alerts)

    # ── 组装输出 ──
    result = {
        "meta": {
            "eval_date": date.today().strftime("%Y-%m-%d"),
            "report_date": report_date,
            "generated_at": date.today().strftime("%Y-%m-%dT%H:%M:%S"),
            "engine_version": "v1.0",
        },
        "core_metrics": core,
        "v30_metrics": v30,
        "dimension_misjudge": dim_misjudge,
        "dimension_corr": dim_corr,
        "veto_analysis": veto_analysis,
        "alerts": alerts,
        "param_suggestions": suggestions,
        "per_stock": per_stock,
    }

    # ── 输出 ──
    os.makedirs(EVAL_OUTPUT, exist_ok=True)
    json_path = os.path.join(EVAL_OUTPUT, f"eval_result_{report_date.replace('-', '')}.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    if not args.dry_run:
        write_records_csv(recs, report_date, RECORDS_CSV)
        write_summary_csv(core, dim_misjudge, veto_analysis, SUMMARY_CSV)

    # ── 控制台摘要 ──
    print()
    print("=" * 50)
    print(f"  后评估 {report_date} 完成")
    print(f"  推荐 {core.get('total_recs', 0)} 只 | 盈利 {core.get('wins', 0)} | 亏损 {core.get('losses', 0)} | 胜率 {core.get('win_rate', 0)}%")
    print(f"  浮动基准 {core.get('floating_benchmark', 0)}% ({core.get('market_stage', '')}) — {core.get('benchmark_status', '')}")
    print(f"  组合收益 {core.get('portfolio_return', 0):+.2f}% | 超额 {core.get('excess_return', 0):+.2f}%")
    print(f"  Spearman ρ={core.get('spearman_rho', 0):.3f} | 评分区分度 {core.get('score_distinction_70', 0)}%")
    if alerts:
        print(f"  ⚠ {len(alerts)} 个报警: {', '.join(a['indicator'] for a in alerts[:3])}")
    else:
        print(f"  无报警")
    if suggestions:
        print(f"  参数建议: {len(suggestions)} 项")
        for s in suggestions:
            print(f"    - {s['param']}: {s['current']} → {s['suggested']} [{s['confidence']}置信度]")
    print(f"  JSON → {json_path}")
    if not args.dry_run:
        print(f"  CSV → {RECORDS_CSV}, {SUMMARY_CSV}")
    print("=" * 50)

    # 返回alert数量作为exit code参考 (供调度脚本判断是否需要AI介入)
    if alerts:
        sys.exit(min(len(alerts), 10))  # 0-10, 供shell判断
    sys.exit(0)


if __name__ == "__main__":
    main()
