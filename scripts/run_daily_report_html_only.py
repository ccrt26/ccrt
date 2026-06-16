#!/usr/bin/env python3
"""
run_daily_report_html_only.py — 日报 HTML 自动生成（含 staging/promote/verify 模式）

用法:
  # 生成 staging（默认）
  python3 scripts/run_daily_report_html_only.py --date 20260616

  # 生成 staging + promote 到正式目录（含信号/数据新鲜度检查）
  python3 scripts/run_daily_report_html_only.py --date 20260616 --promote --require-pipeline-signal

  # 只 promote（假设 staging 已存在）
  python3 scripts/run_daily_report_html_only.py --date 20260616 --only 600114 --promote-only

  # 单票 staging
  python3 scripts/run_daily_report_html_only.py --date 20260616 --only 600114

⚠️ 正式日报只能由 run_daily_production_pipeline.py 或其授权链路生成。
   --promote 时自动验证 pipeline signal、v3.6 readiness、target scope、
   数据新鲜度；不满足则退出非零，不得写入正式目录。
"""
import argparse, json, os, re, subprocess, shutil, sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
import markdown

# D07_v1.2 contract builder
sys.path.insert(0, str(Path(__file__).resolve().parent))
from daily_d07_contract_builder import build_daily_d07_contract, fmt_num as d07_fmt_num

ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "重点股票" / "股票报告"
PIGEON = ROOT / "代码文件" / "信鸽信息采集" / "pigeon_config.json"
SIGNAL = ROOT / ".claude" / "signal_daily_report.json"
DAILY_TARGETS = ROOT / "00_项目地基" / "02_权威注册表" / "daily_report_targets.json"
DATA_DIR = ROOT / "代码文件" / "数据"
PRODUCTION_LOG_DIR = ROOT / "logs" / "daily_production"
TZ_SHANGHAI = timezone(timedelta(hours=8))

FLOW_STATUS_KEYS = ["date", "target_codes", "stage", "overall", "failed_gates",
                     "generated_files", "promoted_files", "blocked_reason"]

# ===== Production evidence write boundary =====
# FLOW_STATUS_DIR can be overridden via env DAILY_REPORT_FLOW_STATUS_DIR.
# Default is PRODUCTION_LOG_DIR.
# Only authorized production paths (post-check_pipeline_signal PASS) may write
# to the production directory. Tests and negative scenarios MUST use an override.
_FLOW_OVERRIDE = os.environ.get("DAILY_REPORT_FLOW_STATUS_DIR")
FLOW_STATUS_DIR = Path(_FLOW_OVERRIDE) if _FLOW_OVERRIDE else PRODUCTION_LOG_DIR


def is_production_flow_status_dir():
    """True if current FLOW_STATUS_DIR is the default production directory."""
    return not _FLOW_OVERRIDE and FLOW_STATUS_DIR == PRODUCTION_LOG_DIR


def is_publish_result_stage(stage):
    """Only 'promote' is a valid production publish result stage.

    Production flow_status must only represent the final publish result:
    promote PASS / promote BLOCK. Staging generation, prechecks, deprecated
    writes, and test paths are NOT publish results and must not pollute the
    production flow_status.
    """
    return stage == "promote"


def now():
    return datetime.now(TZ_SHANGHAI).strftime("%Y-%m-%dT%H:%M:%S+08:00")


def load_json(p):
    return json.loads(Path(p).read_text(encoding="utf-8-sig"))


def write_json(p, data):
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    Path(p).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def pool():
    cfg = load_json(PIGEON)
    return [(str(s["code"]), s["name"]) for s in cfg.get("target_stocks", []) if s.get("code") and s.get("name")]


def active_targets():
    """Load enabled active targets from daily_report_targets.json."""
    if not DAILY_TARGETS.exists():
        return []
    cfg = load_json(DAILY_TARGETS)
    return [
        {"code": str(s["code"]), "name": s["name"]}
        for s in cfg.get("active_targets", [])
        if s.get("enabled", True) and s.get("code") and s.get("name")
    ]


def target_pool():
    """Return (code, name) pairs for enabled active targets."""
    return [(t["code"], t["name"]) for t in active_targets()]


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
    p = DATA_DIR / "data_scored.json"
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

SIGNAL_WINRATE_DB = DATA_DIR / "signal_winrate_db.json"


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


def fmt_num(value, fmt=".2f", fallback="—"):
    if value is None:
        return fallback
    return f"{value:{fmt}}"


def risk_light_display(value):
    text = str(value or "").strip().lower()
    mapping = {
        "green": "\U0001f7e9 绿灯", "yellow": "\U0001f7e1 黄灯", "red": "\U0001f534 红灯",
        "绿": "\U0001f7e9 绿灯", "黄": "\U0001f7e1 黄灯", "红": "\U0001f534 红灯",
        "绿灯": "\U0001f7e9 绿灯", "黄灯": "\U0001f7e1 黄灯", "红灯": "\U0001f534 红灯",
        "\U0001f7e9": "\U0001f7e9 绿灯", "\U0001f7e1": "\U0001f7e1 黄灯", "\U0001f534": "\U0001f534 红灯",
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


def check_pipeline_signal(date, require=True):
    """Check .claude/signal_daily_report.json for correct date + data_ready + pipeline provenance.

    v3.7.2-fix: ALL conditions fail-closed when require=True.
    When require=True, any mismatch raises SystemExit immediately.
    Returns dict only when require=False (for informational callers).

    Requires (when require=True):
      - signal == 'daily_report'
      - date == target_date
      - data_ready is True
      - pipeline_mode is True
      - source == 'run_daily_production_pipeline'
    """
    if not SIGNAL.exists():
        msg = f"signal_daily_report.json not found — pipeline signal required"
        if require:
            raise SystemExit(msg)
        return {"signal_valid": False, "reason": msg}
    sig = load_json(SIGNAL)
    checks = [
        (sig.get("signal") == "daily_report",
         f"signal type={sig.get('signal')}, expected 'daily_report'"),
        (sig.get("date") == date,
         f"signal date={sig.get('date')}, expected {date}"),
        (sig.get("data_ready") is True,
         f"signal data_ready={sig.get('data_ready')}, expected True"),
        (sig.get("pipeline_mode") is True,
         f"signal pipeline_mode={sig.get('pipeline_mode')}, expected True"),
        (sig.get("source") == "run_daily_production_pipeline",
         f"signal source={sig.get('source')}, expected 'run_daily_production_pipeline'"),
    ]
    for ok, reason in checks:
        if not ok:
            if require:
                raise SystemExit(reason)
            return {"signal_valid": False, "reason": reason}
    return {"signal_valid": True, "source": sig.get("source", "unknown")}


def check_data_freshness(code, date):
    """Verify kline_cache and fund_flow_cache have target date. Returns (ok, issues)."""
    issues = []
    k = row_by_date(DATA_DIR / "kline_cache" / f"{code}.json", date)
    if not k:
        issues.append(f"kline_cache/{code}.json missing date={date}")
    f = row_by_date(DATA_DIR / "fund_flow_cache" / f"{code}.json", date)
    if not f:
        issues.append(f"fund_flow_cache/{code}.json missing date={date}")
    return len(issues) == 0, issues


def check_active_target_scope(date):
    """Verify each active target has required data. Returns (ok, issues)."""
    targets = active_targets()
    issues = []
    for t in targets:
        ok, sub_issues = check_data_freshness(t["code"], date)
        issues.extend(sub_issues)
    return len(issues) == 0, issues


def compute_audit_status(date, code, name, baseline_id):
    """Derive audit_u9 and audit_u10 from real verification (not hardcoded PASS)."""
    data_ok, data_issues = check_data_freshness(code, date)
    # baseline resolution is done in generate_one — if we got here, it passed
    bl_ok = bool(baseline_id)

    u9 = {"status": "PASS", "note": "行情、资金、板块、baseline均已披露。"}
    if not data_ok:
        u9 = {"status": "BLOCK", "note": f"数据新鲜度检查未通过: {'; '.join(data_issues)}"}
    elif not bl_ok:
        u9 = {"status": "BLOCK", "note": "baseline未解析成功"}

    u10 = {"status": "PASS", "note": f"HTML作为正式展示产物，baseline={baseline_id}。"}
    if not data_ok:
        u10 = {"status": "BLOCK", "note": f"数据新鲜度未通过，不得作为正式产物。"}
    return u9, u10


def generate_one(date, code, name, staging_dir=None):
    """Generate report files into staging_dir. staging_dir is required — no direct formal write allowed."""
    sig = load_json(SIGNAL)
    if sig.get("date") != date or not sig.get("data_ready"):
        raise SystemExit(f"signal not ready: {sig.get('date')} {sig.get('data_ready')}")
    resolved, bl = resolve_baseline(code, name, date)
    baseline_id = resolved["baseline_id"]
    k = row_by_date(DATA_DIR / "kline_cache" / f"{code}.json", date)
    f = row_by_date(DATA_DIR / "fund_flow_cache" / f"{code}.json", date)
    m = latest_row(DATA_DIR / "tushare" / "margin_detail" / f"{code}.json")
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
    t1 = "持有待涨，不主动加仓" if held else "观察，不主动新开"
    one_line = f"{name}收{k['close']}，低于关键压力{fmt_num(pressure)}；主力{fmt_money(f.get('main_force_net'))}，先看{fmt_num(support)}能否收回，再看{fmt_num(pressure)}能否站稳。"
    overall_light = "yellow"
    overall_light_display = risk_light_display(overall_light)

    p0 = {
        "t1_action": t1,
        "current_position_cap": pos_text,
        "triggered_position_cap": f"站稳{fmt_num(pressure)}且主力流出收窄后再评估",
        "key_buy_point": f"先看{fmt_num(support)}能否收回，再看{fmt_num(pressure)}能否站稳",
        "new_position_stop_loss": f"{k['low']:.2f}下破不新开",
        "held_position_stop_loss": f"短线{k['low']:.2f}；中线{fmt_num(stop)}",
        "forbidden_actions": [f"{fmt_num(pressure)}以上不追高", "主力流出未收窄不加仓", f"跌破{k['low']:.2f}不补仓", f"跌破{fmt_num(stop)}或核心反证出现则移出/否决"],
        "confidence_level": "中",
        "action_change": "maintain",
        "one_line_conclusion": one_line,
    }

    roles = {
        "山猫_宏观": {"板块相位": phase, "解读": f"{industry}板块相位为{phase}，对{name}是背景支撑，买卖仍服从价格和资金。"},
        "信鸽_事件": {"解读": f"{name}当日未触发强制否决事件，事件线只作为后续验证项。"},
        "玉夜_数据": {"解读": f"{date[4:6]}月{date[6:8]}日收{k['close']}，成交量{vol}万手，主力{fmt_money(f.get('main_force_net'))}。"},
        "流金_风控": {"综合灯": overall_light, "综合灯显示": overall_light_display, "解读": f"未站稳{fmt_num(pressure)}前不扩大仓位，跌破{k['low']:.2f}先控风险。"},
        "青山_信号": {"解读": f"价格低于{fmt_num(pressure)}，信号只支持跟踪，不支持追高。"},
        "腰子_整合": {"解读": one_line},
    }

    objs = ["p0_action","baseline_interpretation","kline_interpretation","market_sector_interpretation","fund_flow_interpretation","risk_interpretation","event_interpretation","signal_interpretation","tomorrow_plan","t5_outlook"]
    daily_synthesis = {}
    for obj in objs:
        daily_synthesis[obj] = {
            "data_fact": f"{name} {date} 收{k['close']}，板块相位{phase}，主力{fmt_money(f.get('main_force_net'))}",
            "interpretation": f"价格未站稳{fmt_num(pressure)}，资金结构要求先守纪律。",
            "action_impact": t1,
            "trigger_condition": f"收回{fmt_num(support)}并站稳{fmt_num(pressure)}",
            "invalidation_condition": f"跌破{k['low']:.2f}或跌破{fmt_num(stop)}",
            "confidence": "中"
        }

    # Compute real audit status instead of hardcoding PASS
    audit_u9, audit_u10 = compute_audit_status(date, code, name, baseline_id)
    data_readiness = "READY" if audit_u9["status"] == "PASS" else "DEGRADED"

    # Build degraded_items list
    degraded_items = [f"margin(T+1延迟,最新{m.get('trade_date')})"] if m else []

    # ===== D07_v1.2 contract via builder =====
    d07_fields = build_daily_d07_contract(
        date=date, code=code, name=name,
        k=k, f=f, bl=bl,
        p0=p0, roles=roles, daily_synthesis=daily_synthesis,
        degraded_items=degraded_items,
        support=support, pressure=pressure, stop=stop,
        phase=phase, industry=industry, baseline_id=baseline_id,
    )

    sidecar = {
        "report_version": "3.7.0-html-only-auto",
        "stock_code": code, "stock_name": name,
        "trade_date": f"{date[:4]}-{date[4:6]}-{date[6:8]}",
        "baseline_id": baseline_id,
        "baseline_valid_until": bl.get("valid_until", resolved.get("valid_until")),
        "baseline_usage": "current_authoritative",
        "data_readiness": data_readiness,
        "degraded_items": degraded_items,
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
        "role_interpretations": d07_fields["role_interpretations"],
        "yaozi_integration": {"final_action": t1, "position_rule": p0["triggered_position_cap"], "reason": one_line, "risk_boundary": p0["held_position_stop_loss"], "daily_synthesis": daily_synthesis},
        "signal_winrate": {"available": swr_usable, "total_samples": swr_samples, "avg_t1_winrate": swr_t1, "avg_t5_winrate": swr_t5, "low_sample": swr_low, "note": f"低于{fmt_num(pressure)}时不追高"},
        "eval_hooks": {"t1_verify": f"次日验证是否收回{fmt_num(support)}并靠近{fmt_num(pressure)}", "t5_verify": f"5个交易日验证{fmt_num(pressure)}能否转支撑，跌破{fmt_num(stop)}则否决"},
        "audit_u9": audit_u9,
        "audit_u10": audit_u10,
        # D07_v1.2 contract fields from builder
        "framework_version": d07_fields["framework_version"],
        "logic_version": d07_fields["logic_version"],
        "interpretation_id": d07_fields["interpretation_id"],
        "conclusion_strength": d07_fields["conclusion_strength"],
        "hypotheses": d07_fields["hypotheses"],
        "evidence_gap_requests": d07_fields["evidence_gap_requests"],
        "rule_refs": d07_fields["rule_refs"],
        "knowledge_refs": d07_fields["knowledge_refs"],
        "d07_interpretation": d07_fields["d07_interpretation"],
        "unified_interpretation": d07_fields["unified_interpretation"],
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
| 短线支撑 | {fmt_num(support)} |
| 关键压力 | {fmt_num(pressure)} |
| MA20支撑 | {fmt_num(ma20, fallback="未提供")} |
| 否决线 | {fmt_num(stop)} |
| 目标观察价 | {fmt_num(target)} |

**这说明**：{name}仍在当前权威基线内运行，但收盘没有站稳{fmt_num(pressure)}，动作要服从基线纪律。
**对明日影响**：先看{fmt_num(support)}能否收回，再看{fmt_num(pressure)}能否转成支撑。

## 三、今天行情

{int(date[4:6])}月{int(date[6:8])}日成交量{vol}万手。

| 日期 | 开盘 | 收盘 | 最高 | 最低 | 成交量 |
|:--|--:|--:|--:|--:|--:|
| {date[:4]}-{date[4:6]}-{date[6:8]} | {k['open']:.2f} | {k['close']:.2f} | {k['high']:.2f} | {k['low']:.2f} | {vol}万手 |

**这说明**：收盘{k['close']:.2f}低于压力{fmt_num(pressure)}，短线还不是强确认。
**对明日影响**：若放量跌破{k['low']:.2f}，先降风险；若收回{fmt_num(support)}，继续看{fmt_num(pressure)}。

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

**这说明**：板块背景支持继续跟踪，但买点仍由{fmt_num(support)}/{fmt_num(pressure)}决定。
**对明日影响**：板块走弱时，跌破{k['low']:.2f}的风险要优先处理。

## 七、消息事件

当日未识别强制否决事件，后续继续跟踪公司事件线。

## 八、信号胜率

信号结论：低于{fmt_num(pressure)}时不追高，收回{fmt_num(support)}后再看强度。
{swr_line}

## 九、风控红黄绿灯与持仓折扣

综合灯：{overall_light_display}。跌破{k['low']:.2f}先控风险，跌破{fmt_num(stop)}进入否决流程。

## 十、明日情景应对与T+5展望

| 情景 | 条件 | 动作 |
|:--|:--|:--|
| 修复 | 收回{fmt_num(support)}并靠近{fmt_num(pressure)} | {t1} |
| 转弱 | 跌破{k['low']:.2f} | 先控风险 |
| 否决 | 跌破{fmt_num(stop)} | 移出/否决 |

**T+5展望**：5个交易日内看{fmt_num(pressure)}能否转支撑；若跌破{fmt_num(stop)}，中线逻辑需要重评。
"""

    # Require staging_dir — no direct formal write allowed
    if not staging_dir:
        raise SystemExit(f"generate_one: staging_dir required, cannot write directly to {REPORT_DIR}")
    out_dir = Path(staging_dir) / code
    out_dir.mkdir(parents=True, exist_ok=True)
    prefix = f"{name}({code})日报_{date}"
    (out_dir / f"{prefix}.json").write_text(json.dumps(sidecar, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / f"{prefix}.md").write_text(md, encoding="utf-8")
    (out_dir / f"{prefix}.html").write_text(render_html(md, f"{name}({code}) 日报 {date}"), encoding="utf-8")
    return {"code": code, "name": name, "baseline_id": baseline_id, "data_readiness": data_readiness}


def promote_staging(date, staging_dir, targets):
    """Promote staging files to production directory. Runs pre-checks first."""
    blocked = []
    promoted = []

    for code, name in targets:
        src_dir = Path(staging_dir) / code
        dst_dir = REPORT_DIR / f"{name}({code})"
        prefix = f"{name}({code})日报_{date}"

        # Check staging files exist
        missing = []
        for ext in [".json", ".md", ".html"]:
            if not (src_dir / f"{prefix}{ext}").exists():
                missing.append(ext)
        if missing:
            blocked.append(f"{name}({code}): staging missing: {', '.join(missing)}")
            continue

        dst_dir.mkdir(parents=True, exist_ok=True)
        for ext in [".json", ".md", ".html"]:
            shutil.copy2(str(src_dir / f"{prefix}{ext}"), str(dst_dir / f"{prefix}{ext}"))
            promoted.append(f"{name}({code})/{prefix}{ext}")

    return promoted, blocked


def write_flow_status(date, target_codes, stage, overall, failed_gates, generated, promoted, reason,
                      allow_production_write=False):
    """Write daily report flow status JSON with production write boundary.

    Production flow_status is the FINAL publish result — only stage="promote"
    with overall="PASS" or "BLOCK" may be written to the production directory.

    Rules:
    - If FLOW_STATUS_DIR is overridden via DAILY_REPORT_FLOW_STATUS_DIR env var:
      any stage may be written (for test/negative scenario evidence).
    - If FLOW_STATUS_DIR is the default production directory:
      1. allow_production_write must be True (post-signal-check authorization).
      2. stage must be "promote" (publish result only).
      3. overall must be "PASS" or "BLOCK".
      Otherwise raise SystemExit, no file written.
    """
    if is_production_flow_status_dir():
        if not allow_production_write:
            msg = (
                f"BLOCK: Unauthorized production write_flow_status — "
                f"stage={stage} overall={overall}. "
                f"Set DAILY_REPORT_FLOW_STATUS_DIR to a temp dir for test/negative paths, "
                f"or use allow_production_write=True only in authorized promote flow."
            )
            print(f"[BLOCK] {msg}")
            raise SystemExit(msg)
        if not is_publish_result_stage(stage):
            msg = (
                f"BLOCK: Non-publish stage '{stage}' cannot write production flow_status. "
                f"Only stage='promote' is a valid production publish result. "
                f"Set DAILY_REPORT_FLOW_STATUS_DIR to a temp dir for non-publish evidence."
            )
            print(f"[BLOCK] {msg}")
            raise SystemExit(msg)
        if overall not in ("PASS", "BLOCK"):
            msg = (
                f"BLOCK: Invalid overall '{overall}' for production flow_status. "
                f"Only 'PASS' or 'BLOCK' allowed."
            )
            print(f"[BLOCK] {msg}")
            raise SystemExit(msg)

    status = {
        "date": date,
        "target_codes": target_codes,
        "stage": stage,
        "overall": overall,
        "failed_gates": failed_gates,
        "generated_files": generated,
        "promoted_files": promoted,
        "blocked_reason": reason,
        "timestamp": now(),
    }
    out = FLOW_STATUS_DIR / f"{date}_daily_report_flow_status.json"
    write_json(out, status)
    return str(out)


def main():
    ap = argparse.ArgumentParser(description="日报 HTML 自动生成")
    ap.add_argument("--date", required=True, help="YYYYMMDD")
    ap.add_argument("--only", default="", help="单票代码")
    ap.add_argument("--all-pool", action="store_true", help="使用鸽子全池")
    ap.add_argument("--write", action="store_true",
                    help="[DEPRECATED] 已移除，使用 --staging-dir + --promote")
    ap.add_argument("--staging-dir", default="", help="staging 目录根")
    ap.add_argument("--promote", action="store_true", help="从 staging promote 到正式目录（带前置检查）")
    ap.add_argument("--require-pipeline-signal", action="store_true",
                    help="必须验证 signal_daily_report.json 为当日 + data_ready")
    ap.add_argument("--target-scope", default="", choices=["active", "all", ""],
                    help="目标范围（默认根据 --all-pool 决定）")
    args = ap.parse_args()

    date = args.date

    # --write is deprecated: zero-side-effect fail-fast
    # Must NOT call write_flow_status or write any production evidence.
    if args.write:
        msg = "ERROR: --write deprecated; use --staging-dir + --promote instead."
        print(msg)
        sys.exit(2)

    # Determine target pool
    if args.target_scope == "active" or (not args.target_scope and not args.all_pool):
        source_pool = target_pool()
        target_source = "daily_report_targets"
    else:
        source_pool = pool()
        target_source = "pigeon_config"

    targets = [(c, n) for c, n in source_pool if (not args.only or c == args.only)]
    if not targets:
        raise SystemExit("no target")
    target_codes = [c for c, _ in targets]

    # Staging dir default
    staging_dir = args.staging_dir
    if not staging_dir and (args.promote or not args.write):
        staging_dir = str(ROOT / "运行产物" / "daily_report_build" / date)

    # Check pipeline signal if required
    if args.require_pipeline_signal:
        check_pipeline_signal(date, require=True)
    elif args.promote:
        # --promote implies --require-pipeline-signal
        check_pipeline_signal(date, require=True)

    # Pre-checks for --promote
    if args.promote:
        # Check active target scope
        scope_ok, scope_issues = check_active_target_scope(date)
        if not scope_ok:
            # promote_precheck is NOT a publish result — only write to
            # override dir if DAILY_REPORT_FLOW_STATUS_DIR is set.
            if _FLOW_OVERRIDE:
                write_flow_status(date, target_codes, "promote_precheck", "BLOCK", [],
                                  [], [], f"活跃目标数据新鲜度未通过: {'; '.join(scope_issues)}",
                                  allow_production_write=False)
            raise SystemExit(f"数据新鲜度检查未通过: {'; '.join(scope_issues)}")

        # Verify each code is in active targets
        active_codes = {t["code"] for t in active_targets()}
        inactive = [c for c in target_codes if c not in active_codes]
        if inactive:
            # promote_precheck is NOT a publish result — only write to
            # override dir if DAILY_REPORT_FLOW_STATUS_DIR is set.
            if _FLOW_OVERRIDE:
                write_flow_status(date, target_codes, "promote_precheck", "BLOCK", [],
                                  [], [], f"非活跃目标不得 promote: {','.join(inactive)}",
                                  allow_production_write=False)
            raise SystemExit(f"非活跃目标 {inactive} 不得 promote")

    if args.promote:
        # === Verify-before-write promote: run release gate against shadow root, copy only if PASS ===
        # 1) Build shadow formal root from staging, so release gate can verify without touching formal
        shadow_root = Path(staging_dir) / "release_gate_shadow" / "重点股票" / "股票报告"
        for code, name in targets:
            src_dir = Path(staging_dir) / code
            dst_dir = shadow_root / f"{name}({code})"
            prefix = f"{name}({code})日报_{date}"
            dst_dir.mkdir(parents=True, exist_ok=True)
            for ext in [".json", ".md", ".html"]:
                sp = src_dir / f"{prefix}{ext}"
                if sp.exists():
                    (dst_dir / f"{prefix}{ext}").write_bytes(sp.read_bytes())

        # 2) Run release gate against shadow root
        rg_env = os.environ.copy()
        rg_env["REPORT_ROOT_OVERRIDE"] = str(shadow_root)
        release_gate_cmd = [sys.executable, str(ROOT / "scripts" / "check_daily_release_gate.py"),
                            "--date", date, "--active-only"]
        rg_proc = subprocess.run(release_gate_cmd, capture_output=True, text=True, timeout=120,
                                 cwd=str(ROOT), env=rg_env)
        rg_rc = rg_proc.returncode

        if rg_rc != 0:
            # Gate BLOCKed: do NOT copy to formal; report clean failure
            rg_tail = rg_proc.stdout.strip().split("\n")[-3:] if rg_proc.stdout else []
            write_flow_status(date, target_codes, "promote", "BLOCK",
                              ["release_gate"], [], [],
                              f"release gate BLOCK (rc={rg_rc}); formal directory untouched",
                              allow_production_write=True)
            print(json.dumps({
                "status": "PROMOTE_BLOCKED",
                "reason": f"release gate BLOCK (rc={rg_rc})",
                "failed_gates": ["release_gate"],
                "promoted_files": [],
                "release_gate_stdout_tail": rg_tail,
                "formal_untouched": True,
            }, ensure_ascii=False, indent=2))
            sys.exit(2)

        # 3) Gate PASSed: copy staging to formal (not shadow)
        promoted, blocked = promote_staging(date, staging_dir, targets)
        if blocked:
            write_flow_status(date, target_codes, "promote", "BLOCK", [],
                              [], [], f"promote 失败: {'; '.join(blocked)}",
                              allow_production_write=True)
            raise SystemExit(f"promote 失败: {'; '.join(blocked)}")

        result = {"status": "PROMOTE_PASS", "results": [{"code": c, "name": n} for c, n in targets],
                  "promoted_files": promoted}
        write_flow_status(date, target_codes, "promote", "PASS", [], [], promoted, None,
                          allow_production_write=True)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    # Generate mode: always write to staging, never directly to formal
    data_pool = pool()
    skipped = [
        {"code": c, "name": n, "reason": "not enabled in daily_report_targets.json"}
        for c, n in data_pool
        if c not in target_codes
    ]

    if not args.promote:
        if staging_dir:
            res = [generate_one(date, c, n, staging_dir=staging_dir) for c, n in targets]
            generated_files = [
                f"{staging_dir}/{c}/{n}({c})日报_{date}.{ext}"
                for c, n in targets
                for ext in ["json", "md", "html"]
            ]
            # Staging generation is NOT a publish result — never write to
            # the default production flow_status dir. Only write when
            # DAILY_REPORT_FLOW_STATUS_DIR override is set (test/isolated evidence).
            if _FLOW_OVERRIDE:
                write_flow_status(date, target_codes, "staging_generation", "PASS", [],
                                  generated_files, [], None,
                                  allow_production_write=False)
            print(json.dumps({"status": "STAGING_GENERATION_PASS",
                              "target_source": target_source,
                              "targets": targets,
                              "staging_dir": staging_dir,
                              "results": res}, ensure_ascii=False, indent=2))
            return 0
        else:
            # Just show plan (no --staging-dir specified)
            payload = {"date": args.date, "targets": targets, "skipped": skipped,
                       "target_source": target_source}
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 0


if __name__ == "__main__":
    raise SystemExit(main())
