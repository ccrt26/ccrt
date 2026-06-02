#!/usr/bin/env python3
"""保护快照生成器 v1.0 — 只读主系统数据，只写 保护机制/保护快照.json"""
import json, os, sys, time
from datetime import datetime, date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SNAPSHOT_PATH = ROOT / "保护机制" / "保护快照.json"
SCHEMA_PATH = ROOT / "保护机制" / "保护快照.schema.json"
LEDGER_PATH = ROOT / "保护机制" / "持仓账本.json"
RISK_PARAMS_PATH = ROOT / "保护机制" / "知识库" / "个人风控参数.md"
BEHAVIOR_PATH = ROOT / "保护机制" / "知识库" / "行为模式.md"
KEY_LEVELS_PATH = ROOT / "保护机制" / "知识库" / "持仓关键位.md"
TRAP_CALENDAR_PATH = ROOT / "保护机制" / "知识库" / "陷阱日历.md"


def now_iso():
    return datetime.now().isoformat()


def load_json(path):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        return {"_error": str(e), "_path": str(path)}


def parse_risk_params(path):
    """从个人风控参数.md中提取结构化数值"""
    params = {
        "single_position_limit_pct": 30.0,
        "total_position_limit_pct": 70.0,
        "daily_loss_limit_pct": 5.0,
        "daily_loss_limit_amount": 1800.0,
        "hard_stop_loss_pct": -8.0,
        "time_stop_days": 10,
        "cooling_rules": [
            {"trigger": "单笔亏损超5%", "action": "次日禁止开新仓", "days": 1},
            {"trigger": "连续2笔止损", "action": "暂停交易", "days": 2},
            {"trigger": "连续3笔止损", "action": "暂停交易+腰子复盘", "days": 5},
        ],
        "forbid_rules": [
            "开盘30分钟内追涨",
            "无事件催化追3%以上涨幅",
            "浮亏加仓摊平",
            "操作前不刹车",
        ]
    }
    try:
        raw = open(path, 'r', encoding='utf-8').read()
        import re
        single = re.search(r'单票仓位上限[^\d]*(\d+)', raw)
        total = re.search(r'总仓位上限[^\d]*(\d+)', raw)
        loss_pct = re.search(r'单日最大亏损限额[^\d]*(\d+)', raw)
        loss_amt = re.search(r'(\d+[,.]?\d*)\s*元', raw)
        hard_stop = re.search(r'硬止损比例[^\d]*[-]?(\d+)', raw)
        if single: params["single_position_limit_pct"] = float(single.group(1))
        if total: params["total_position_limit_pct"] = float(total.group(1))
        if loss_pct: params["daily_loss_limit_pct"] = float(loss_pct.group(1))
        if loss_amt: params["daily_loss_limit_amount"] = float(loss_amt.group(1).replace(',', ''))
        if hard_stop: params["hard_stop_loss_pct"] = -float(hard_stop.group(1))
    except Exception:
        pass
    return params


def check_data_quality(sources: dict, stale_threshold: int = 600) -> dict:
    """判定数据整体质量状态"""
    statuses = [v.get("status", "missing") for v in sources.values()]
    max_age = max((v.get("age_seconds", 0) for v in sources.values()), default=0)

    flags = [{"source": k, "status": v.get("status", "missing"), "detail": v.get("detail", "")}
             for k, v in sources.items()]

    warnings = []
    if "missing" in statuses:
        overall = "missing"
    elif "conflict" in statuses:
        overall = "conflict"
    elif max_age > stale_threshold:
        overall = "stale"
        warnings.append(f"数据过期: max_age={max_age}s > threshold={stale_threshold}s")
    elif "degraded" in statuses:
        overall = "degraded"
    else:
        overall = "normal"

    return {"data_status": overall, "stale_seconds": max_age, "flags": flags, "warnings": warnings}


def build_positions(ledger, risk_params):
    """从持仓账本构建positions[]段"""
    positions = []
    raw_positions = ledger.get("positions", []) if isinstance(ledger, dict) else []
    stats = ledger.get("stats", {}) if isinstance(ledger, dict) else {}

    for p in raw_positions:
        code = p.get("code", "")
        name = p.get("name", "")
        avg_cost = float(p.get("buy_price", 0) or 0)
        shares = int(p.get("shares", 0) or 0)
        buy_date = p.get("buy_date", "")
        current_price = float(p.get("current_price", avg_cost) or avg_cost)

        if avg_cost > 0:
            unrealized_pnl_pct = round((current_price - avg_cost) / avg_cost * 100, 2)
        else:
            unrealized_pnl_pct = 0.0

        discipline_stop = round(avg_cost * (1 + risk_params["hard_stop_loss_pct"] / 100), 2)
        strategy_stop = discipline_stop  # default, 青山 to override in future
        effective_stop = max(discipline_stop, strategy_stop)

        stop_conflict = abs(discipline_stop - strategy_stop) / avg_cost > 0.03 if avg_cost > 0 else False

        pos = {
            "code": code, "name": name, "shares": shares,
            "avg_cost": avg_cost, "current_price": current_price,
            "unrealized_pnl_pct": unrealized_pnl_pct,
            "position_pct": round(shares * current_price / 36000 * 100, 2) if shares > 0 else 0,
            "buy_date": buy_date, "buy_time": p.get("buy_time", ""),
            "holding_days": (date.today() - date.fromisoformat(buy_date)).days if buy_date else 0,
            "discipline_stop_loss": discipline_stop,
            "strategy_stop_loss": strategy_stop,
            "effective_stop_loss": effective_stop,
            "stop_loss_conflict": stop_conflict,
            "stop_loss_conflict_detail": (
                f"纪律止损{discipline_stop} vs 策略止损{strategy_stop}，差距{abs(discipline_stop-strategy_stop):.2f}元"
                if stop_conflict else ""
            ),
            "target_price": round(avg_cost * 1.1, 2),
            "report_action": "hold", "report_direction": "neutral", "report_confidence": "unknown",
            "triggered_signals": [], "vetoed_signals": [],
            "signal_winrate": 0.5,
            "risk_factors": [], "counter_evidence": [],
            "key_levels": {"support": round(avg_cost * 0.92, 2), "resistance": round(avg_cost * 1.1, 2),
                           "current_zone": "mid_range"},
            "data_quality_flags": [],
            "recent_events": []
        }
        positions.append(pos)

    return positions


def build_market_guard():
    """构建市场环境守护段"""
    return {
        "market_sentiment": "warm",
        "sentiment_indicators": {
            "advance_decline_ratio": 0, "turnover_billion": 0,
            "northbound_net_billion": 0, "limit_up_count": 0,
            "limit_down_count": 0, "margin_balance_billion": 0, "vix_or_equivalent": 0
        },
        "index_change": {"shanghai_pct": 0, "shenzhen_pct": 0, "chinext_pct": 0, "star50_pct": 0},
        "overnight": {"sp500_pct": 0, "nasdaq_pct": 0, "a50_pct": 0, "usdcny": 7.15},
        "liquidity_status": "normal",
        "market_forbid_rules": []
    }


def build_event_guard():
    """构建事件催化守护段"""
    return {
        "recent_events": [],
        "event_direction": "none",
        "has_valid_catalyst": False,
        "sensitive_event_hit": False,
        "sensitive_event_detail": "",
        "negative_announcements": []
    }


def build_behavior_guard(cooling_active=False, cooling_reason=""):
    """构建行为模式守护段"""
    return {
        "forbidden_patterns_hit": [],
        "cooldown_reason": cooling_reason,
        "open_30min_block": True,
        "chase_without_event_block": True,
        "loss_averaging_block": True,
        "revenge_trade_risk": False,
        "known_impulse_patterns": ["开盘追涨", "浮亏加仓摊平", "无催化追高"]
    }


def build_final_guard(positions, data_status, cooling_active):
    """构建最终守护判定"""
    hard_blocks = []
    soft_warnings = []

    if cooling_active:
        hard_blocks.append({"type": "cooling", "rule": "冷却期禁止开新仓", "detail": "当前处于冷却期"})
    if data_status in ("missing", "conflict"):
        hard_blocks.append({"type": "data", "rule": "数据不可用", "detail": f"数据状态: {data_status}"})

    total_pos_pct = sum(p.get("position_pct", 0) for p in positions)
    if total_pos_pct > 70:
        hard_blocks.append({"type": "position", "rule": "总仓位超70%上限", "detail": f"总仓位{total_pos_pct:.1f}%"})

    for p in positions:
        if p.get("position_pct", 0) > 30:
            hard_blocks.append({"type": "position", "rule": f"{p['name']}单票超30%上限",
                                "detail": f"{p['name']}仓位{p['position_pct']:.1f}%"})
        if p.get("stop_loss_conflict"):
            soft_warnings.append({"type": "stop_conflict", "rule": "止损口径冲突>3%",
                                  "detail": p.get("stop_loss_conflict_detail", "")})
        if p.get("unrealized_pnl_pct", 0) < 0:
            hard_blocks.append({"type": "loss_averaging", "rule": "浮亏加仓禁止",
                                "detail": f"{p['name']}浮亏{p['unrealized_pnl_pct']:.1f}%，禁止加仓"})

    if data_status == "stale":
        soft_warnings.append({"type": "data", "rule": "数据过期", "detail": "快照数据超过10分钟"})

    default_action = "等"
    if any(b["type"] in ("cooling", "missing", "conflict") for b in hard_blocks
           if isinstance(b, dict) and "type" in b):
        default_action = "否" if data_status in ("missing", "conflict") else "强制冷却"

    return {
        "hard_blocks": hard_blocks,
        "soft_warnings": soft_warnings,
        "default_action": default_action,
        "required_user_inputs_before_trade": ["金额或股数", "操作理由", "止损依据"],
        "yaozi_conclusion": "",
        "yaozi_reasoning": ""
    }


def build_account_snapshot(ledger, risk_params):
    """从持仓账本构建real_account段"""
    total_capital = 36000.0
    positions_raw = ledger.get("positions", []) if isinstance(ledger, dict) else []
    stats = ledger.get("stats", {}) if isinstance(ledger, dict) else {}

    total_market_value = 0.0
    for p in positions_raw:
        price = float(p.get("current_price", p.get("buy_price", 0)) or 0)
        shares = int(p.get("shares", 0) or 0)
        total_market_value += price * shares

    cash = total_capital - total_market_value
    total_pos_pct = round(total_market_value / total_capital * 100, 2) if total_capital > 0 else 0
    consecutive_losses = stats.get("loss_trades", 0)

    cooling_active = False
    cooling_reason = ""
    if consecutive_losses >= 3:
        cooling_active = True
        cooling_reason = f"连续{consecutive_losses}笔止损"

    return {
        "total_capital": total_capital,
        "cash": round(cash, 2),
        "total_position_pct": total_pos_pct,
        "daily_realized_pnl": 0,
        "daily_unrealized_pnl": 0,
        "daily_pnl_limit": risk_params["daily_loss_limit_amount"],
        "daily_pnl_limit_hit": False,
        "consecutive_losses": consecutive_losses,
        "cooling_period_active": cooling_active,
        "cooling_reason": cooling_reason,
        "cooling_until": str(date.today() + timedelta(days=5)) if cooling_active else ""
    }


def main():
    sources = {}
    start_time = time.time()

    # 1. 读持仓账本
    try:
        ledger = load_json(LEDGER_PATH)
        sources["ledger"] = {"status": "fresh", "age_seconds": 0}
    except Exception as e:
        ledger = {}
        sources["ledger"] = {"status": "missing", "age_seconds": 9999, "detail": str(e)}

    # 2. 读风控参数
    try:
        risk_params = parse_risk_params(RISK_PARAMS_PATH)
        sources["risk_params"] = {"status": "fresh", "age_seconds": 0}
    except Exception as e:
        risk_params = parse_risk_params.__defaults__[0] if False else {}
        sources["risk_params"] = {"status": "missing", "age_seconds": 9999, "detail": str(e)}

    # 3. 构建各段
    real_account = build_account_snapshot(ledger, risk_params)
    positions = build_positions(ledger, risk_params)
    market = build_market_guard()
    events = build_event_guard()
    behavior = build_behavior_guard(cooling_active=real_account["cooling_period_active"],
                                     cooling_reason=real_account["cooling_reason"])

    # 4. 数据质量
    quality = check_data_quality(sources)

    # 5. 最终守护
    final = build_final_guard(positions, quality["data_status"], real_account["cooling_period_active"])

    elapsed = round(time.time() - start_time, 2)
    today = date.today().isoformat()

    snapshot = {
        "meta": {
            "generated_at": now_iso(),
            "trading_date": today,
            "snapshot_version": "1.0.0",
            "source_files": [str(LEDGER_PATH), str(RISK_PARAMS_PATH)],
            "stale_seconds": quality["stale_seconds"],
            "data_status": quality["data_status"],
            "data_quality_flags": quality["flags"],
            "warnings": quality["warnings"]
        },
        "real_account": real_account,
        "positions": positions,
        "market_guard": market,
        "event_guard": events,
        "behavior_guard": behavior,
        "final_guard": final
    }

    # 写入
    os.makedirs(SNAPSHOT_PATH.parent, exist_ok=True)
    with open(SNAPSHOT_PATH, 'w', encoding='utf-8') as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)

    print(f"✓ 保护快照已生成: {SNAPSHOT_PATH}")
    print(f"  交易日: {today}  状态: {quality['data_status']}  耗时: {elapsed}s")
    print(f"  持仓数: {len(positions)}  硬阻断: {len(final['hard_blocks'])}  默认动作: {final['default_action']}")

    return snapshot


if __name__ == "__main__":
    main()
