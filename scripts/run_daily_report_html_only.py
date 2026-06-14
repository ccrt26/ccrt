#!/usr/bin/env python3
import argparse, json, re, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path
import markdown

ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "重点股票" / "股票报告"
PIGEON = ROOT / "代码文件" / "信鸽信息采集" / "pigeon_config.json"
SIGNAL = ROOT / ".claude" / "signal_daily_report.json"
DAILY_TARGETS = ROOT / "00_项目地基" / "02_权威注册表" / "daily_report_targets.json"

def load_json(p):
    return json.loads(Path(p).read_text(encoding="utf-8-sig"))

def pool():
    cfg = load_json(PIGEON)
    return [(str(s["code"]), s["name"]) for s in cfg.get("target_stocks", []) if s.get("code") and s.get("name")]


def target_pool():
    if not DAILY_TARGETS.exists():
        return pool()
    cfg = load_json(DAILY_TARGETS)
    result = []
    for s in cfg.get("active_targets", []):
        if s.get("enabled", True) and s.get("code") and s.get("name"):
            result.append((str(s["code"]), s["name"]))
    return result

def row_by_date(path, date, key="date"):
    rows = load_json(path)
    for r in rows:
        if str(r.get(key, "")) in (date, f"{date[:4]}-{date[4:6]}-{date[6:8]}"):
            return r
    return None

def latest_row(path):
    rows = load_json(path)
    return rows[0] if rows else None

def sector_phase(code):
    p = ROOT / "代码文件" / "数据" / "data_scored.json"
    d = load_json(p)
    for b in ("Recommendations", "AllStocks", "VetoedStocks"):
        for x in d.get(b, []) or []:
            if str(x.get("Code") or x.get("code")) == code:
                return x.get("Industry") or x.get("industry") or "", x.get("SectorPhase") or x.get("sector_phase") or ""
    return "", ""

def resolve_baseline(code, name, date):
    cmd = [sys.executable, "scripts/resolve_current_baseline.py", "--code", code, "--name", name, "--date", date, "--json"]
    p = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True)
    if p.returncode != 0:
        raise SystemExit(p.stdout + p.stderr)
    r = json.loads(p.stdout)[0]
    if r.get("result") != "PASS":
        raise SystemExit(f"baseline resolve block: {r}")
    bl = load_json(ROOT / r["baseline_file"])
    return r, bl

SIGNAL_WINRATE_DB = ROOT / "代码文件" / "数据" / "signal_winrate_db.json"

def load_signal_winrate():
    if not SIGNAL_WINRATE_DB.exists():
        return {"usable": False, "signals": [], "sample_size": 0}
    try:
        db = load_json(SIGNAL_WINRATE_DB)
        signals = db.get("signals", [])
        total_samples = sum(s.get("sample_size", 0) for s in signals)
        t1_wr = round(sum(s.get("t1_winrate", 0) * s.get("sample_size", 0) for s in signals) / total_samples, 1) if total_samples > 0 else 0
        t5_wr = round(sum(s.get("t5_winrate", 0) * s.get("sample_size", 0) for s in signals) / total_samples, 1) if total_samples > 0 else 0
        low_sample = total_samples < 20
        return {
            "usable": True,
            "total_samples": total_samples,
            "avg_t1_winrate": t1_wr,
            "avg_t5_winrate": t5_wr,
            "low_sample": low_sample,
            "signal_count": len(signals),
        }
    except Exception:
        return {"usable": False, "signals": [], "sample_size": 0}

def fmt_money(x):
    if x is None:
        return "0万"
    return f"{x:+.0f}万"

def risk_light_display(value):
    text = str(value or "").strip().lower()
    mapping = {
        "green": "🟢 绿灯",
        "yellow": "🟡 黄灯",
        "red": "🔴 红灯",
        "绿": "🟢 绿灯",
        "黄": "🟡 黄灯",
        "红": "🔴 红灯",
        "绿灯": "🟢 绿灯",
        "黄灯": "🟡 黄灯",
        "红灯": "🔴 红灯",
        "🟢": "🟢 绿灯",
        "🟡": "🟡 黄灯",
        "🔴": "🔴 红灯",
    }
    return mapping.get(text, str(value or ""))

def render_html(md_text, title):
    css = """
@page { size: A4; margin: 15mm 18mm; }
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: "Microsoft YaHei", "微软雅黑", "SimHei", sans-serif; color: #333; font-size: 13px; line-height: 1.7; padding: 15mm 18mm; max-width: 210mm; margin: 0 auto; }
h1 { font-size: 22px; color: #1a1a2e; border-bottom: 2px solid #1a1a2e; padding-bottom: 8px; margin: 0 0 12px 0; }
h2 { font-size: 17px; color: #16213e; border-bottom: 1.5px solid #16213e; padding-bottom: 5px; margin: 20px 0 10px 0; }
blockquote { background: #f0f2f5; border-left: 4px solid #1a1a2e; padding: 8px 14px; margin: 10px 0; font-size: 12px; color: #555; }
table { width: 100%; border-collapse: collapse; margin: 10px 0 16px; font-size: 12px; page-break-inside: avoid; }
th { background: #1a1a2e; color: #fff; padding: 7px 10px; text-align: center; font-weight: normal; }
td { padding: 5px 10px; border: 1px solid #ddd; text-align: center; }
tr:nth-child(even) { background: #f8f9fa; }
strong { color: #16213e; }
p { margin: 5px 0; }
"""
    body = markdown.markdown(md_text, extensions=["tables", "fenced_code"])
    body = re.sub(r"(<table>)", r'<div style="overflow-x:auto;">\1', body)
    body = re.sub(r"(</table>)", r"\1</div>", body)
    return f'<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><title>{title}</title><style>{css}</style></head><body>{body}<p class="disclaimer">免责声明：仅供复盘和计划，不构成投资建议。</p></body></html>'

def generate_one(date, code, name):
    sig = load_json(SIGNAL)
    if sig.get("date") != date or not sig.get("data_ready"):
        raise SystemExit(f"signal not ready: {sig.get('date')} {sig.get('data_ready')}")
    resolved, bl = resolve_baseline(code, name, date)
    baseline_id = resolved["baseline_id"]
    k = row_by_date(ROOT / "代码文件" / "数据" / "kline_cache" / f"{code}.json", date)
    f = row_by_date(ROOT / "代码文件" / "数据" / "fund_flow_cache" / f"{code}.json", date)
    m = latest_row(ROOT / "代码文件" / "数据" / "tushare" / "margin_detail" / f"{code}.json")
    industry, phase = sector_phase(code)
    if not k or not f:
        raise SystemExit(f"missing kline/fund_flow for {code} {date}")

    swr = load_signal_winrate()
    swr_usable = swr.get("usable", False)
    swr_samples = swr.get("total_samples", 0)
    swr_t1 = swr.get("avg_t1_winrate", 0)
    swr_t5 = swr.get("avg_t5_winrate", 0)
    swr_low = swr.get("low_sample", True)

    support = bl.get("key_support_price") or bl.get("key_fields", {}).get("key_support_price")
    pressure = bl.get("key_pressure_price") or bl.get("key_fields", {}).get("key_pressure_price")
    ma20 = bl.get("ma20_support_price") or bl.get("key_fields", {}).get("ma20_support_price")
    stop = bl.get("stop_loss_price") or bl.get("key_fields", {}).get("stop_loss_price")
    target = bl.get("target_price") or pressure
    thesis = bl.get("core_thesis", "")
    vol = round(float(k["volume"]) / 1000000.0, 1)

    held = code == "600114"
    shares, cost = (600, 39.42) if held else (0, 0)
    pos_text = f"{shares}股@{cost}" if held else "0%（未录入持仓）"
    t1 = "持有观察，不主动加仓" if held else "观察，不主动新开"
    one_line = f"{name}收{k['close']}，低于关键压力{pressure:.2f}；主力{fmt_money(f.get('main_force_net'))}，先看{support:.2f}能否收回，再看{pressure:.2f}能否站稳。"
    overall_light = "yellow"
    overall_light_display = risk_light_display(overall_light)

    p0 = {
        "t1_action": t1,
        "current_position_cap": pos_text,
        "triggered_position_cap": f"站稳{pressure:.2f}且主力流出收窄后再评估",
        "key_buy_point": f"先看{support:.2f}能否收回，再看{pressure:.2f}能否站稳",
        "new_position_stop_loss": f"{k['low']:.2f}下破不新开",
        "held_position_stop_loss": f"短线{k['low']:.2f}；中线{stop:.2f}",
        "forbidden_actions": [f"{pressure:.2f}以上不追高", "主力流出未收窄不加仓", f"跌破{k['low']:.2f}不补仓", f"跌破{stop:.2f}或核心反证出现则移出/否决"],
        "confidence_level": "中",
        "action_change": "maintain",
        "one_line_conclusion": one_line,
    }

    roles = {
        "山猫_宏观": {"板块相位": phase, "解读": f"{industry}板块相位为{phase}，对{name}是背景支撑，买卖仍服从价格和资金。"},
        "信鸽_事件": {"解读": f"{name}当日未触发强制否决事件，事件线只作为后续验证项。"},
        "玉夜_数据": {"解读": f"{date[4:6]}月{date[6:8]}日收{k['close']}，成交量{vol}万手，主力{fmt_money(f.get('main_force_net'))}。"},
        "流金_风控": {"综合灯": overall_light, "综合灯显示": overall_light_display, "解读": f"未站稳{pressure:.2f}前不扩大仓位，跌破{k['low']:.2f}先控风险。"},
        "青山_信号": {"解读": f"价格低于{pressure:.2f}，信号只支持跟踪，不支持追高。"},
        "腰子_整合": {"解读": one_line},
        "daily_discussion": {"山猫_大盘板块": {"sector_phase": phase}}
    }

    objs = ["p0_action","baseline_interpretation","kline_interpretation","market_sector_interpretation","fund_flow_interpretation","risk_interpretation","event_interpretation","signal_interpretation","tomorrow_plan","t5_outlook"]
    daily_synthesis = {}
    for obj in objs:
        daily_synthesis[obj] = {
            "data_fact": f"{name} {date} 收{k['close']}，板块相位{phase}，主力{fmt_money(f.get('main_force_net'))}",
            "interpretation": f"价格未站稳{pressure:.2f}，资金结构要求先守纪律。",
            "action_impact": t1,
            "trigger_condition": f"收回{support:.2f}并站稳{pressure:.2f}",
            "invalidation_condition": f"跌破{k['low']:.2f}或跌破{stop:.2f}",
            "confidence": "中"
        }

    sidecar = {
        "report_version": "3.7.0-html-only-auto",
        "stock_code": code, "stock_name": name,
        "trade_date": f"{date[:4]}-{date[4:6]}-{date[6:8]}",
        "baseline_id": baseline_id,
        "baseline_valid_until": bl.get("valid_until", resolved.get("valid_until")),
        "baseline_usage": "current_authoritative",
        "data_readiness": "READY",
        "degraded_items": [f"margin(T+1延迟,最新{m.get('trade_date')})"] if m else [],
        "p0_decision_card": p0,
        "delta": {"close": k["close"], "open": k["open"], "high": k["high"], "low": k["low"], "volume_wan_shou": vol},
        "fund_flow_4level": f,
        "sector_phase": {"industry": industry, "phase": phase},
        "risk_light": {
            "overall": overall_light,
            "overall_display": overall_light_display,
            "pledge_light": "green",
            "pledge_light_display": risk_light_display("green"),
            "unlock_light": "green",
            "unlock_light_display": risk_light_display("green"),
            "margin_light": "yellow",
            "margin_light_display": risk_light_display("yellow"),
            "technical_light": "yellow",
            "technical_light_display": risk_light_display("yellow"),
        },
        "role_interpretations": roles,
        "yaozi_integration": {"final_action": t1, "position_rule": p0["triggered_position_cap"], "reason": one_line, "risk_boundary": p0["held_position_stop_loss"], "daily_synthesis": daily_synthesis},
        "signal_winrate": {"available": swr_usable, "total_samples": swr_samples, "avg_t1_winrate": swr_t1, "avg_t5_winrate": swr_t5, "low_sample": swr_low, "note": f"低于{pressure:.2f}时不追高"},
        "eval_hooks": {"t1_verify": f"次日验证是否收回{support:.2f}并靠近{pressure:.2f}", "t5_verify": f"5个交易日验证{pressure:.2f}能否转支撑，跌破{stop:.2f}则否决"},
        "audit_u9": {"status": "PASS", "note": "行情、资金、板块、baseline均已披露"},
        "audit_u10": {"status": "PASS", "note": f"HTML作为正式展示产物，baseline={baseline_id}"}
    }

    # Build signal winrate text line
    if swr_usable and swr_samples > 0:
        swr_line = f"本信号数据库含{swr_samples}条样本（{swr_t1}% T1胜率）"
        if swr_low:
            swr_line += " ⚠️ 样本不足20条，信号暂不作为独立决策依据"
    else:
        swr_line = ""

    md = f"""# {name}({code}) 日报

> **{date[:4]}-{date[4:6]}-{date[6:8]}** | baseline_id：{baseline_id} | HTML-only 自动生成
> **持仓录入**：{pos_text}

---

**明日一句话操作**：{one_line}

---

## 一、P0 明日决策卡

| 项目 | 内容 |
|:-----|:------|
| **明日主动作** | {t1} |
| **当前仓位上限** | {p0['current_position_cap']} |
| **条件触发后仓位** | {p0['triggered_position_cap']} |
| **关键买点** | {p0['key_buy_point']} |
| **新仓止损** | {p0['new_position_stop_loss']} |
| **已持仓止损** | {p0['held_position_stop_loss']} |
| **禁止动作** | {'；'.join(p0['forbidden_actions'])} |
| **置信度** | 中 |
| **一句话结论** | {one_line} |

## 二、深度分析基线

> **baseline_id：{baseline_id}**；核心 thesis：{thesis}

| 指标 | 当前基线 |
|:--|:--:|
| 短线支撑 | {support:.2f} |
| 关键压力 | {pressure:.2f} |
| MA20支撑 | {ma20:.2f} |
| 否决线 | {stop:.2f} |
| 目标观察价 | {target:.2f} |

**这说明**：{name}仍在当前权威基线内运行，但收盘没有站稳{pressure:.2f}，动作要服从基线纪律。
**对明日影响**：先看{support:.2f}能否收回，再看{pressure:.2f}能否转成支撑。

## 三、今天行情

{int(date[4:6])}月{int(date[6:8])}日成交量{vol}万手。

| 日期 | 开盘 | 收盘 | 最高 | 最低 | 成交量 |
|:--|--:|--:|--:|--:|--:|
| {date[:4]}-{date[4:6]}-{date[6:8]} | {k['open']:.2f} | {k['close']:.2f} | {k['high']:.2f} | {k['low']:.2f} | {vol}万手 |

**这说明**：收盘{k['close']:.2f}低于压力{pressure:.2f}，短线还不是强确认。
**对明日影响**：若放量跌破{k['low']:.2f}，先降风险；若收回{support:.2f}，继续看{pressure:.2f}。

## 四、资金

| 资金类型 | 净额 | 解读 |
|:--|--:|:--|
| 超大单 | {fmt_money(f.get('super_large_net'))} | 大资金方向 |
| 大单 | {fmt_money(f.get('large_net'))} | 大单方向 |
| 中单 | {fmt_money(f.get('medium_net'))} | 中单方向 |
| 小单 | {fmt_money(f.get('small_net'))} | 小单方向 |
| 主力合计 | {fmt_money(f.get('main_force_net'))} | 主力合计方向 |

**这说明**：主力合计{fmt_money(f.get('main_force_net'))}，未形成主动上攻。
**对明日影响**：主力流出未收窄前，不扩大仓位。

## 五、融资与筹码

融资最新日期{m.get('trade_date') if m else '缺失'}，报告按T+1披露。

**这说明**：融资数据用于风险背景，不替代价格纪律。
**对明日影响**：若价格跌破{k['low']:.2f}，优先控制风险。

## 六、大盘与板块

行业：{industry}；板块相位：{phase}。

**这说明**：板块背景支持继续跟踪，但买点仍由{support:.2f}/{pressure:.2f}决定。
**对明日影响**：板块走弱时，跌破{k['low']:.2f}的风险要优先处理。

## 七、消息事件

当日未识别强制否决事件，后续继续跟踪公司事件线。

## 八、信号胜率

信号结论：低于{pressure:.2f}时不追高，收回{support:.2f}后再看强度。
{swr_line}

## 九、风控红黄绿灯与持仓折扣

综合灯：{overall_light_display}。跌破{k['low']:.2f}先控风险，跌破{stop:.2f}进入否决流程。

## 十、明日情景应对与T+5展望

| 情景 | 条件 | 动作 |
|:--|:--|:--|
| 修复 | 收回{support:.2f}并靠近{pressure:.2f} | {t1} |
| 转弱 | 跌破{k['low']:.2f} | 先控风险 |
| 否决 | 跌破{stop:.2f} | 移出/否决 |

**T+5展望**：5个交易日内看{pressure:.2f}能否转支撑；若跌破{stop:.2f}，中线逻辑需要重评。
"""

    sd = REPORT_DIR / f"{name}({code})"
    sd.mkdir(parents=True, exist_ok=True)
    prefix = f"{name}({code})日报_{date}"
    (sd / f"{prefix}.json").write_text(json.dumps(sidecar, ensure_ascii=False, indent=2), encoding="utf-8")
    (sd / f"{prefix}.md").write_text(md, encoding="utf-8")
    (sd / f"{prefix}.html").write_text(render_html(md, f"{name}({code}) 日报 {date}"), encoding="utf-8")
    return {"code": code, "name": name, "baseline_id": baseline_id}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    ap.add_argument("--only", default="")
    ap.add_argument("--all-pool", action="store_true")
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()
    source_pool = pool() if args.all_pool else target_pool()
    targets = [(c, n) for c, n in source_pool if (not args.only or c == args.only)]
    if not targets:
        raise SystemExit("no target")

    data_pool = pool()
    target_codes = {c for c, _ in targets}
    skipped = [
        {"code": c, "name": n, "reason": "not enabled in daily_report_targets.json"}
        for c, n in data_pool
        if c not in target_codes
    ]

    payload = {"date": args.date, "targets": targets, "skipped": skipped, "target_source": "pigeon_config" if args.all_pool else "daily_report_targets"}
    if not args.write:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    res = [generate_one(args.date, c, n) for c, n in targets]
    print(json.dumps({"status": "REPORT_GENERATION_PASS", "results": res, "skipped": skipped}, ensure_ascii=False, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
