#!/usr/bin/env python3
"""trade_utils.py — 交易工具函数共享模块

Replaces trade_utils.ps1.
Commission/stamp tax calc, trading day counting, limit up/down detection,
position sizing, MA crossover detection.
Shared by both sim trading tracks.
Code level: L1
"""
from datetime import datetime, timedelta


def calc_commission(amount, rate=0.00025, min_fee=5.0):
    """Calculate trading commission."""
    fee = abs(amount) * rate
    if fee < min_fee:
        fee = min_fee
    return round(fee, 2)


def calc_stamp_tax(amount, rate=0.001, is_sell=True, on_sell_only=True):
    """Calculate stamp tax (only on sells for A-shares)."""
    if on_sell_only and not is_sell:
        return 0
    return round(amount * rate, 2)


def get_trading_days_between(start_date, end_date):
    """Count trading days (Mon-Fri) between two dates, exclusive of start."""
    count = 0
    current = start_date + timedelta(days=1)
    while current <= end_date:
        if current.weekday() < 5:
            count += 1
        current += timedelta(days=1)
    return count


def get_cooling_days(date_str, today_str):
    """Calculate trading days since a given date."""
    if not date_str:
        return 999
    d1 = datetime.strptime(today_str, "%Y%m%d")
    d2 = datetime.strptime(date_str, "%Y%m%d")
    return get_trading_days_between(d2, d1)


def get_board_limit(code):
    """Get price limit percentage based on board."""
    if code.startswith("30") or code.startswith("68"):
        return 19.4
    return 9.4


def is_limit_up(change_pct, code=""):
    """Check if stock hit limit up."""
    limit = get_board_limit(code)
    return change_pct >= limit


def is_limit_down(change_pct, code=""):
    """Check if stock hit limit down."""
    limit = get_board_limit(code)
    return change_pct <= -limit


def get_sell_proceeds(price, shares, commission_rate=0.00025, min_commission=5.0,
                      stamp_tax_rate=0.001, on_sell_only=True):
    """Calculate net proceeds from a sell order."""
    amount = round(price * shares, 2)
    commission = calc_commission(amount, commission_rate, min_commission)
    stamp_tax = calc_stamp_tax(amount, stamp_tax_rate, True, on_sell_only)
    return {
        "Amount": amount,
        "Commission": commission,
        "StampTax": stamp_tax,
        "NetProceeds": amount - commission - stamp_tax,
    }


def get_buy_cost(price, shares, commission_rate=0.00025, min_commission=5.0, slippage_pct=0.1):
    """Calculate total cost of a buy order (including slippage)."""
    slipped_price = round(price * (1 + slippage_pct / 100), 2)
    amount = round(slipped_price * shares, 2)
    commission = calc_commission(amount, commission_rate, min_commission)
    return {
        "Price": slipped_price,
        "Amount": amount,
        "Commission": commission,
        "TotalCost": amount + commission,
    }


def get_position_size(score, tiers):
    """Determine position size from score against tier config."""
    for tier in tiers:
        if score >= tier.get("MinScore", 0):
            return float(tier.get("Ratio", 0))
    return 0


def is_trading_day(date_str):
    """Check if a date is a trading day (excludes weekends and known holidays)."""
    dt = datetime.strptime(date_str, "%Y%m%d")
    if dt.weekday() >= 5:
        return False
    holidays_2026 = {
        "20260101",
        "20260217", "20260218", "20260219",
        "20260404", "20260405", "20260406",
        "20260501", "20260502", "20260503",
        "20260619", "20260620", "20260621",
        "20261001", "20261002", "20261003", "20261004", "20261005", "20261006", "20261007",
    }
    return date_str not in holidays_2026


def test_ma_crossover(ma5, ma20, prev_ma5, prev_ma20):
    """Detect MA5 crossing below MA20 (trend break)."""
    if ma5 <= 0 or ma20 <= 0 or prev_ma5 <= 0 or prev_ma20 <= 0:
        return False
    return (ma5 < ma20) and (prev_ma5 >= prev_ma20)


def test_rsi_persistent(current_rsi, prev_rsi, threshold=80):
    """Check if RSI has been persistently above threshold."""
    if current_rsi <= 0 or prev_rsi <= 0:
        return False
    return (current_rsi > threshold) and (prev_rsi > threshold)


def assert_write_success(path, before_write=None):
    """Verify a file write succeeded (exists + timestamp updated)."""
    import os as _os
    if not _os.path.exists(path):
        raise IOError(f"写入失败(文件不存在): {path}")
    if before_write:
        actual_mtime = _os.path.getmtime(path)
        if actual_mtime <= before_write.timestamp():
            raise IOError(f"写入失败(时间戳未更新): {path}")
