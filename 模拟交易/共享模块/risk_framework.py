#!/usr/bin/env python3
"""risk_framework.py — 组合级别风控共享模块

Replaces risk_framework.ps1.
四级预警体系: 黄旗 → 红旗 → 黑旗 → 连败
Shared by both sim trading tracks.
Code level: L2
"""
from datetime import datetime, timedelta


def get_daily_drawdown_risk(current_value, prev_value, yellow_threshold=3.0, red_threshold=5.0):
    """Single-day drawdown detection."""
    if prev_value <= 0:
        return {"Level": "none", "DailyDD": 0, "Action": ""}
    daily_dd = round((current_value / prev_value - 1) * 100, 2)
    if daily_dd <= -red_threshold:
        return {"Level": "red", "DailyDD": daily_dd, "Action": "当日减仓50%+停开仓3日"}
    if daily_dd <= -yellow_threshold:
        return {"Level": "yellow", "DailyDD": daily_dd, "Action": "次日不开新仓"}
    return {"Level": "none", "DailyDD": daily_dd, "Action": ""}


def get_cumulative_drawdown_risk(current_value, initial_capital, black_threshold=10.0, peak_value=0):
    """Cumulative drawdown detection."""
    if initial_capital <= 0:
        return {"Level": "none", "TotalDD": 0, "Action": ""}
    total_dd = round((current_value / initial_capital - 1) * 100, 2)
    if total_dd <= -black_threshold:
        return {"Level": "black", "TotalDD": total_dd, "Action": "暂停系统，全面审查"}
    peak_dd = 0
    if peak_value > 0:
        peak_dd = round((current_value / peak_value - 1) * 100, 2)
    return {"Level": "none", "TotalDD": total_dd, "PeakDD": peak_dd, "Action": ""}


def get_consecutive_loss_risk(consecutive_losses, max_allowed=6):
    """Consecutive loss detection."""
    if consecutive_losses >= max_allowed:
        return {"Level": "yellow", "Consecutive": consecutive_losses, "Action": "停开仓，审视信号有效性"}
    return {"Level": "none", "Consecutive": consecutive_losses, "Action": ""}


def get_portfolio_risk_decision(current_value, prev_value, initial_capital, peak_value,
                                 consecutive_losses, config):
    """Aggregate all risk signals into a unified decision."""
    decisions = []

    daily_risk = get_daily_drawdown_risk(
        current_value, prev_value,
        config.get("YellowFlagDD", 3.0), config.get("RedFlagDD", 5.0)
    )
    if daily_risk["Level"] != "none":
        decisions.append({
            "Source": "单日回撤", "Level": daily_risk["Level"],
            "Detail": f"日回撤 {daily_risk['DailyDD']}%", "Action": daily_risk["Action"]
        })

    cum_risk = get_cumulative_drawdown_risk(
        current_value, initial_capital,
        config.get("BlackFlagDD", 10.0), peak_value
    )
    if cum_risk["Level"] != "none":
        decisions.append({
            "Source": "累计回撤", "Level": cum_risk["Level"],
            "Detail": f"累计亏损 {cum_risk['TotalDD']}%", "Action": cum_risk["Action"]
        })

    loss_risk = get_consecutive_loss_risk(
        consecutive_losses, config.get("MaxConsecutiveLosses", 6)
    )
    if loss_risk["Level"] != "none":
        decisions.append({
            "Source": "连续亏损", "Level": loss_risk["Level"],
            "Detail": f"连败 {loss_risk['Consecutive']} 笔", "Action": loss_risk["Action"]
        })

    max_level = "none"
    skip_open = False
    force_reduce = False
    force_suspend = False

    for d in decisions:
        if d["Level"] == "black":
            max_level = "black"
            force_suspend = True
            break
        if d["Level"] == "red":
            max_level = "red"
            force_reduce = True
            skip_open = True
        if d["Level"] == "yellow" and max_level == "none":
            max_level = "yellow"
            skip_open = True

    return {
        "MaxLevel": max_level,
        "SkipOpen": skip_open,
        "ForceReduce": force_reduce,
        "ForceSuspend": force_suspend,
        "Decisions": decisions,
        "DailyDD": daily_risk["DailyDD"],
    }


def get_risk_cooldown_state(risk_cooldowns, date_str):
    """Check if currently in a risk cooldown period."""
    if not risk_cooldowns or "RedFlagDate" not in risk_cooldowns:
        return {"InCooldown": False, "DaysRemaining": 0}
    red_date = risk_cooldowns.get("RedFlagDate")
    if not red_date:
        return {"InCooldown": False, "DaysRemaining": 0}
    d1 = datetime.strptime(date_str, "%Y%m%d")
    d2 = datetime.strptime(red_date, "%Y%m%d")
    days = 0
    current = d2 + timedelta(days=1)
    while current <= d1:
        if current.weekday() < 5:
            days += 1
        current += timedelta(days=1)
    cooldown_days = 3
    remaining = cooldown_days - days
    if remaining <= 0:
        return {"InCooldown": False, "DaysRemaining": 0}
    return {"InCooldown": True, "DaysRemaining": remaining}


def get_market_circuit_breaker(csi300_change_pct, market_turnover, low_turnover_days=0):
    """Market-level circuit breaker (macro risk)."""
    result = {"Level": "none", "Action": "", "SkipOpen": False, "ForceReduce": False}
    if csi300_change_pct <= -5.0:
        result["Level"] = "meltdown"
        result["Action"] = "大盘暴跌>5%: 强制减仓50%+停开仓3日"
        result["SkipOpen"] = True
        result["ForceReduce"] = True
    elif csi300_change_pct <= -3.0:
        result["Level"] = "warn"
        result["Action"] = "大盘跌>3%: 当日不开新仓"
        result["SkipOpen"] = True
    elif market_turnover < 5000 and low_turnover_days >= 2:
        result["Level"] = "warn"
        result["Action"] = "流动性枯竭(成交<5000亿连续2日): 开仓金额减半"
    return result


def get_sector_phase_alerts(positions, current_phases, confidence_map):
    """Sector phase-based position alerts."""
    warnings = []
    force_reduce = []
    for code, pos in positions.items():
        sector = pos.get("EntryIndustry") or pos.get("EntrySector", "")
        if not sector:
            continue
        entry_phase = pos.get("EntrySectorPhase", "")
        current_phase = current_phases.get(sector, "")
        current_conf = confidence_map.get(sector)

        if current_phase == "衰退期" and entry_phase != "衰退期":
            warnings.append({
                "Code": code, "Reason": f"板块恶化: {sector} {entry_phase}→衰退期", "Level": "yellow"
            })
        if current_conf is not None and current_conf < 40:
            force_reduce.append({
                "Code": code, "Reason": f"主线置信度崩塌: {sector} 当前置信度={current_conf}<40", "Level": "red"
            })
    return {"Warnings": warnings, "ForceReduce": force_reduce}


def get_industry_concentration(positions, max_per_industry=2):
    """Check industry concentration limits."""
    industry_count = {}
    for code, pos in positions.items():
        if pos.get("Shares", 0) <= 0:
            continue
        ind = pos.get("EntryIndustry", "未知")
        industry_count.setdefault(ind, []).append(code)
    violations = {ind: codes for ind, codes in industry_count.items() if len(codes) > max_per_industry}
    return {"Counts": industry_count, "Violations": violations}


def test_recovery_condition(daily_dd, threshold=1.0):
    """Check if drawdown has recovered enough to resume trading."""
    return abs(daily_dd) < threshold


def get_c8_breakthrough_risk(stock_data):
    """C8突破性质风控: 纯动量突破禁止开新仓+紧止损, RSI>80不加仓.

    消费评分引擎输出中的 _C8_BlockNewPosition / _C8_TightStopPct / _C8_RSI_Block 标记。
    设计来源: design_scoring_methodology_v1.0 §3.2 (2026-05-29 P0修复)

    Args:
        stock_data: dict, 评分后的股票数据(含C8标记字段)
    Returns:
        dict: {BlockNew, TightStopPct, RSIBlock, Reason}
    """
    block_new = (stock_data.get("_C8_BlockNewPosition", False) or
                 stock_data.get("c8_block_new_position", False))
    tight_stop = (stock_data.get("_C8_TightStopPct") or
                  stock_data.get("c8_tight_stop_pct"))
    rsi_block = (stock_data.get("_C8_RSI_Block", False) or
                 stock_data.get("c8_rsi_block", False))

    reasons = []
    if block_new:
        reasons.append("C8纯动量突破: 禁止开新仓")
    if tight_stop is not None:
        reasons.append(f"C8紧止损: {tight_stop}%")
    if rsi_block:
        reasons.append("C8 RSI>80: 不加仓")

    return {
        "BlockNew": block_new,
        "TightStopPct": tight_stop,
        "RSIBlock": rsi_block,
        "Reason": "; ".join(reasons) if reasons else "",
    }
