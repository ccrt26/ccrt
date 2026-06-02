#!/usr/bin/env python3
# ⚠️ SPLIT_PENDING (2026-05-29): 788行超500行红线，待情墨拆分评审。
#    建议: 撮合逻辑/持仓管理/订单执行分离为独立模块。
"""sim_trading.py — 重点股票模拟交易引擎 v1.6

Replaces sim_trading.ps1.
Daily-frequency sim trading for 6 key stocks based on evaluation data.
Exit priority: P1止损 → P2趋势恶化 → 腰子指令 → P3预判转空 → P4全部止盈 → P5止盈减仓
Code level: L2
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

# ── Project root ────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = str(SCRIPT_DIR.parent.parent)
sys.path.insert(0, str(SCRIPT_DIR.parent))

# ── Imports from shared modules ─────────────────────────
sys.path.insert(0, str(Path(ROOT) / "模拟交易" / "共享模块"))
from quote_engine import get_quote_map, get_quote_map_with_retry, get_benchmark_value, save_quote_cache  # noqa: E402
from risk_framework import (  # noqa: E402
    get_portfolio_risk_decision, get_risk_cooldown_state,
    get_market_circuit_breaker, get_sector_phase_alerts,
)
from trade_utils import (  # noqa: E402
    calc_commission, get_sell_proceeds, get_buy_cost, get_position_size,
    is_limit_up, is_limit_down, get_cooling_days, is_trading_day,
    get_board_limit, assert_write_success,
)

# ── Stock code map (loaded from key_stocks.json) ────────
def load_code_map(root_dir):
    """Load stock code map from authoritative key_stocks.json config."""
    config_path = os.path.join(root_dir, "代码文件", "数据", "key_stocks.json")
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {s["code"]: {"Market": s["market"], "Name": s["name"], "Board": s["board"]}
                for s in data["stocks"]}
    # Fallback: minimal default (should never be used)
    return {
        "601689": {"Market": "sh", "Name": "拓普集团", "Board": "main"},
        "600114": {"Market": "sh", "Name": "东睦股份", "Board": "main"},
    }

HOLIDAYS_2026 = {
    "20260101",
    "20260217", "20260218", "20260219",
    "20260404", "20260405", "20260406",
    "20260501", "20260502", "20260503",
    "20260619", "20260620", "20260621",
    "20261001", "20261002", "20261003", "20261004", "20261005", "20261006", "20261007",
}


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def main():
    parser = argparse.ArgumentParser(description="Key Stock Sim Trading Engine")
    parser.add_argument("--date", default=datetime.now().strftime("%Y%m%d"), help="Trading date (yyyyMMdd)")
    parser.add_argument("--data-file", default="", help="Evaluation data JSON path")
    parser.add_argument("--root-dir", default=ROOT, help="Project root directory")
    parser.add_argument("--dry-run", action="store_true", help="Dry run mode")
    parser.add_argument("--force", action="store_true", help="Bypass 09:45 time check")
    parser.add_argument("--instruction-file", default="", help="Yaozi instruction file path")
    args = parser.parse_args()

    date_str = args.date
    root_dir = args.root_dir
    sim_dir = os.path.join(root_dir, "模拟交易")
    canon_base = os.path.join(root_dir, "历史数据")

    config_file = os.path.join(sim_dir, "sim_config.json")
    positions_file = os.path.join(canon_base, "00_核心交易", "positions.json")
    txn_file = os.path.join(canon_base, "00_核心交易", "transactions.csv")
    snapshot_file = os.path.join(canon_base, "01_交易快照", f"snapshot_{date_str}.json")
    perf_file = os.path.join(canon_base, "00_核心交易", "perf_summary.json")
    log_dir = os.path.join(sim_dir, "日志")
    quotes_cache_file = os.path.join(sim_dir, "quotes_cache.json")

    if not args.dry_run:
        os.makedirs(log_dir, exist_ok=True)

    log_lines = []

    def log(msg, level="INFO"):
        line = f"[{level}] {msg}"
        log_lines.append(line)
        print(line)

    log(f"===== 模拟交易引擎 v1.6 | Date {date_str} =====")
    if args.dry_run:
        log("[DRY RUN MODE - 不会写入文件]", "WARN")

    # Load CODE_MAP from authoritative config
    CODE_MAP = load_code_map(root_dir)
    log(f"重点股票名单已加载: {len(CODE_MAP)}只")

    script_date = datetime.strptime(date_str, "%Y%m%d")

    # ── Step 0: Non-trading day check ────────────────────
    if script_date.weekday() >= 5:
        log("非交易日，跳过")
        if not args.dry_run:
            return
    if date_str in HOLIDAYS_2026:
        log("法定节假日，跳过")
        if not args.dry_run:
            return

    # ── Step 1: Load config ──────────────────────────────
    skip_open_new = False  # 24h mode: cron controls timing, not engine
    log("读取配置...")
    config = load_json(config_file)

    # ── Step 2: Load positions ───────────────────────────
    log("读取持仓...")
    if os.path.exists(positions_file):
        positions = load_json(positions_file)
    else:
        log("持仓文件不存在，初始化默认持仓", "WARN")
        positions = {
            "Cash": config.get("InitialCapital", 1000000),
            "TotalValue": config.get("InitialCapital", 1000000),
            "LastUpdated": date_str,
            "Positions": {},
            "Cooldowns": {},
            "Watchlist": {},
        }

    stock_map = positions.get("Positions", {})
    cooldowns = positions.get("Cooldowns", {})
    watchlist = positions.get("Watchlist", {})

    # ── Step 3: Load evaluation data ────────────────────
    if not args.data_file:
        args.data_file = os.path.join(root_dir, "重点股票", "次日评估", f"评估数据_{date_str}.json")
    data_file = args.data_file
    if not os.path.exists(data_file):
        eval_dir = os.path.join(root_dir, "重点股票", "次日评估")
        candidates = sorted(
            [f for f in os.listdir(eval_dir) if f.startswith("评估数据_") and f.endswith(".json")],
            reverse=True,
        )
        if candidates:
            data_file = os.path.join(eval_dir, candidates[0])
            log(f"当日评估数据不存在，回退至: {candidates[0]}", "WARN")
        else:
            log(f"评估数据不存在: {args.data_file}", "ERROR")
            sys.exit(1)

    log("读取评估数据...")
    eval_data = load_json(data_file)

    # ── Format detection: "Stocks" (compatible) vs "stocks" (report format) ─
    eval_dir_fb = os.path.join(root_dir, "重点股票", "次日评估")
    if "Stocks" not in eval_data and "stocks" in eval_data:
        fmt_source = eval_data.get("meta", {}).get("generated_by", "unknown")
        log(f"评估数据格式不兼容(Format B, 来源={fmt_source})，尝试回退...", "WARN")
        all_eval_files = sorted(
            [f for f in os.listdir(eval_dir_fb)
             if f.startswith("评估数据_") and f.endswith(".json") and "_parsed" not in f],
            reverse=True,
        )
        found_fb = False
        for f in all_eval_files[:5]:
            fb_path = os.path.join(eval_dir_fb, f)
            try:
                fb_data = load_json(fb_path)
                if "Stocks" in fb_data and fb_data.get("Stocks"):
                    data_file = fb_path
                    eval_data = fb_data
                    log(f"回退至兼容格式: {f}", "WARN")
                    found_fb = True
                    break
            except Exception:
                continue
        if not found_fb:
            log("FATAL: 连续5日无兼容格式(Stocks)评估数据，引擎终止", "FATAL")
            sys.exit(1)

    if "Stocks" not in eval_data:
        log("FATAL: 评估数据格式未知(缺少Stocks键)，引擎终止", "FATAL")
        sys.exit(1)

    # Build stocks_eval with case-insensitive Code/code compatibility
    raw_stocks = eval_data.get("Stocks", [])
    stocks_eval = {}
    for s in raw_stocks:
        code = s.get("Code") or s.get("code", "")
        if code:
            stocks_eval[code] = s

    # Coverage gate: require >= 50% of tracked stocks have eval data
    matched_count = sum(1 for c in CODE_MAP if c in stocks_eval)
    if matched_count < len(CODE_MAP) * 0.5:
        log(f"FATAL: 评估数据覆盖率过低({matched_count}/{len(CODE_MAP)})，低于50%，引擎终止", "FATAL")
        sys.exit(1)
    log(f"评估数据加载: {matched_count}/{len(CODE_MAP)}只, 文件={os.path.basename(data_file)}")

    # ── Step 4: Data quality check ──────────────────────
    log("执行数据质量检查...")
    for code in CODE_MAP:
        s = stocks_eval.get(code)
        if not s:
            log(f"  {code} 无评估数据，跳过", "WARN")
            continue
        price = s.get("Price", 0)
        if not price or price <= 0:
            log(f"  {code} Price异常: {price}", "WARN")
            continue
        scores = s.get("Scores", {})
        composite = scores.get("Composite", -1)
        if composite < 0 or composite > 100:
            log(f"  {code} CompositeScore异常: {composite}", "WARN")
            continue
    log("数据质量检查完成")

    # ── Step 4.5: Load Yaozi instructions (current day only) ─
    yaozi_sells = {}
    yaozi_buys = {}
    yaozi_holds = {}
    yaozi_executed = {}
    instruction_file = args.instruction_file or os.path.join(sim_dir, "交易决策", f"交易指令_{date_str}.json")

    yaozi_active = False
    if os.path.exists(instruction_file):
        try:
            yaozi_raw = load_json(instruction_file)
            for d in yaozi_raw.get("decisions", []):
                if d.get("status") != "pending":
                    continue
                code = d["code"]
                action = d.get("action", "")
                if action in ("SELL", "SELL_HALF"):
                    yaozi_sells[code] = d
                elif action == "BUY":
                    yaozi_buys[code] = d
                elif action == "HOLD":
                    yaozi_holds[code] = d
            if yaozi_sells or yaozi_buys or yaozi_holds:
                yaozi_active = True
                log(f"腰子指令已加载: SELL={len(yaozi_sells)} BUY={len(yaozi_buys)} HOLD={len(yaozi_holds)}")
        except Exception as e:
            log(f"腰子指令文件解析失败: {e}", "WARN")

    strict_mode = config.get("InstructionMode") == "strict" and yaozi_active
    safety_net_mode = not yaozi_active
    if strict_mode:
        log("模式=strict: 腰子指令全覆盖(买入+卖出)")
    elif safety_net_mode:
        log("模式=safety_net: 无当日指令，只执行风控出场(P1-P5)，不开新仓")

    # ── Step 5: Fetch quotes ────────────────────────────
    log("获取实时行情(退避重试模式, deadline=09:45)...")
    stock_list = [{"Code": c, "Market": m["Market"], "Name": m["Name"]} for c, m in CODE_MAP.items()]
    quote_result = get_quote_map_with_retry(stock_list, quotes_cache_file, sim_dir, deadline_str="09:45")
    quotes = quote_result["Quotes"]
    if not quotes:
        log("行情API全部不可用", "WARN")
    time.sleep(0.3)

    bench_data = get_benchmark_value()
    if bench_data:
        log(f"沪深300: {bench_data['Price']}")

    # ── Step 5.5: Market circuit breaker ────────────────
    csi300_chg = bench_data.get("ChangePct", 0) if bench_data else 0
    market_turnover = bench_data.get("Turnover", 10000) if bench_data else 10000
    market_cb = get_market_circuit_breaker(csi300_chg, market_turnover)
    if market_cb["Level"] != "none":
        log(f"MARKET CB: level={market_cb['Level']} | {market_cb['Action']}", "WARN")
        if market_cb.get("SkipOpen"):
            skip_open_new = True
            log("  -> New positions blocked by market circuit breaker", "WARN")

    # ── Step 6: Dividend adjustment (placeholder) ────────
    log("检查除权除息... (placeholder)")

    # ── Step 7: Exit checks (P1→P5 priority) ────────────
    log("执行出场检查...")
    txns = []
    exit_reasons = {}

    for code, pos in list(stock_map.items()):
        if pos.get("Shares", 0) <= 0:
            continue
        quote = quotes.get(code, {})
        eval_stock = stocks_eval.get(code, {})
        info = CODE_MAP.get(code, {})

        # Determine current price (L1→L2→L3 fallback)
        current_price = 0
        quote_source = "[评估数据]"
        if quote.get("Price", 0) > 0:
            current_price = quote["Price"]
            quote_source = quote.get("DataSource", "[1]")
        elif eval_stock.get("Price", 0) > 0:
            current_price = eval_stock["Price"]
        else:
            conservative = quote.get("PrevClose", 0)
            if os.path.exists(quotes_cache_file):
                try:
                    cache = load_json(quotes_cache_file)
                    if code in cache and cache[code].get("Price", 0) > 0:
                        cp = cache[code]["Price"]
                        conservative = min(conservative, cp) if conservative > 0 else cp
                except Exception:
                    pass
            if conservative > 0:
                current_price = conservative
                log(f"  {code} 使用保守估计价(L3): {current_price}", "WARN")
            else:
                current_price = pos.get("StopLoss", 0)
                log(f"  {code} 无价格数据，使用止损价兜底(L3c): {current_price}", "WARN")

        adj_stop_loss = pos.get("StopLoss", 0)
        adj_support = pos.get("Support", 0)
        adj_resistance = pos.get("Resistance", 0)

        # R2/R3 calculation
        avg_cost = pos.get("AvgCost", 0)
        r2 = avg_cost * (1 + config.get("TakeProfit", {}).get("FixedPct1", 10) / 100)
        r3 = avg_cost * (1 + config.get("TakeProfit", {}).get("FixedPct2", 20) / 100)

        board = info.get("Board", "main")

        # P1: Stop loss
        if current_price <= adj_stop_loss:
            if quote and is_limit_down(quote.get("ChangePct", 0), code):
                log(f"  {code} 触发止损但跌停，标记未成交", "WARN")
                continue
            shares = int(pos["Shares"])
            sp = get_sell_proceeds(current_price, shares)
            txns.append({
                "Date": date_str, "Code": code, "Name": pos.get("Name", ""),
                "Action": "SELL", "Price": current_price, "Shares": shares,
                "Amount": sp["Amount"], "Commission": sp["Commission"],
                "StampTax": sp["StampTax"], "TotalCost": sp["NetProceeds"],
                "Reason": "止损_StopLoss", "EntryPrediction": pos.get("EntryShortPrediction", ""),
                "DataSource": quote_source,
            })
            exit_reasons[code] = "P1止损"
            log(f"  {code} P1止损: {current_price} <= {adj_stop_loss}, 卖出{shares}股")
            continue

        # P2 pre: Warning watchlist
        if eval_stock.get("TrendHealth", {}).get("Label") == "警戒":
            if code in watchlist:
                watchlist[code]["LastWarnDate"] = date_str
                watchlist[code]["ConsecutiveDays"] = watchlist[code].get("ConsecutiveDays", 0) + 1
                log(f"  {code} 黄旗: TrendHealth警戒第{watchlist[code]['ConsecutiveDays']}天", "WARN")
            else:
                watchlist[code] = {
                    "Code": code, "Name": pos.get("Name", ""), "WarnLevel": "警戒",
                    "FirstWarnDate": date_str, "LastWarnDate": date_str, "ConsecutiveDays": 1,
                }
                log(f"  {code} 黄旗: 新增关注, TrendHealth警戒", "WARN")
            continue
        if eval_stock.get("TrendHealth", {}).get("Label") == "健康" and code in watchlist:
            log(f"  {code} 趋势恢复健康，移出关注名单")
            watchlist.pop(code, None)

        # P2: Trend breakdown
        if eval_stock.get("TrendHealth", {}).get("Label") == "危险":
            if code in watchlist:
                watchlist.pop(code, None)
                log(f"  {code} 警戒→危险升级", "WARN")
            shares = int(pos["Shares"])
            sp = get_sell_proceeds(current_price, shares)
            txns.append({
                "Date": date_str, "Code": code, "Name": pos.get("Name", ""),
                "Action": "SELL", "Price": current_price, "Shares": shares,
                "Amount": sp["Amount"], "Commission": sp["Commission"],
                "StampTax": sp["StampTax"], "TotalCost": sp["NetProceeds"],
                "Reason": "趋势恶化_危险", "EntryPrediction": pos.get("EntryShortPrediction", ""),
                "DataSource": quote_source,
            })
            exit_reasons[code] = "P2趋势恶化"
            log(f"  {code} P2趋势恶化: TrendHealth=危险, 卖出{shares}股")
            continue

        # Yaozi SELL instructions
        if code in yaozi_sells:
            yd = yaozi_sells[code]
            target_shares = int(pos["Shares"] // 2 // 100 * 100) if yd.get("action") == "SELL_HALF" else int(pos["Shares"])
            if target_shares >= 100:
                sp = get_sell_proceeds(current_price, target_shares)
                reason = yd.get("reason", "")
                override = ""
                if yd.get("risk_override") and yd.get("risk_override_reason"):
                    reason = f"{reason} | [风险覆盖]{yd['risk_override_reason']}"
                    override = "_override"
                txns.append({
                    "Date": date_str, "Code": code, "Name": pos.get("Name", ""),
                    "Action": yd.get("action", "SELL"), "Price": current_price, "Shares": target_shares,
                    "Amount": sp["Amount"], "Commission": sp["Commission"],
                    "StampTax": sp["StampTax"], "TotalCost": sp["NetProceeds"],
                    "Reason": reason, "Source": f"manual{override}",
                    "EntryPrediction": pos.get("EntryShortPrediction", ""),
                    "DataSource": quote_source,
                })
                exit_reasons[code] = "腰子指令"
                yaozi_executed[code] = True
                log(f"  {code} 腰子指令: {yd.get('action')} {target_shares}股")
            continue

        # Yaozi HOLD protection (strict mode only; safety_net always checks exits)
        skip_auto_sell = strict_mode and (code in yaozi_holds or (code not in yaozi_sells and code not in yaozi_buys))

        # P3: Prediction reversal
        if not skip_auto_sell and eval_stock and pos.get("EntryShortPrediction"):
            current_short = eval_stock.get("Prediction", {}).get("Short", "")
            if current_short in ("中性", "看空"):
                shares = int(pos["Shares"])
                sp = get_sell_proceeds(current_price, shares)
                txns.append({
                    "Date": date_str, "Code": code, "Name": pos.get("Name", ""),
                    "Action": "SELL", "Price": current_price, "Shares": shares,
                    "Amount": sp["Amount"], "Commission": sp["Commission"],
                    "StampTax": sp["StampTax"], "TotalCost": sp["NetProceeds"],
                    "Reason": f"预判转空_{current_short}",
                    "EntryPrediction": pos.get("EntryShortPrediction", ""),
                    "DataSource": quote_source,
                })
                exit_reasons[code] = "P3预判转空"
                log(f"  {code} P3预判转空, 卖出{shares}股")
                continue

        # P4: Full take profit (R3)
        if not skip_auto_sell and current_price >= r3:
            shares = int(pos["Shares"])
            sp = get_sell_proceeds(current_price, shares)
            txns.append({
                "Date": date_str, "Code": code, "Name": pos.get("Name", ""),
                "Action": "SELL", "Price": current_price, "Shares": shares,
                "Amount": sp["Amount"], "Commission": sp["Commission"],
                "StampTax": sp["StampTax"], "TotalCost": sp["NetProceeds"],
                "Reason": "全部止盈_R3", "EntryPrediction": pos.get("EntryShortPrediction", ""),
                "DataSource": quote_source,
            })
            exit_reasons[code] = "P4全部止盈"
            log(f"  {code} P4全部止盈: {current_price} >= R3({r3:.2f})")
            continue

        # P5: Half take profit (R2)
        if not skip_auto_sell and current_price >= r2:
            sell_shares = int(pos["Shares"]) // 2 // 100 * 100
            if sell_shares < 100:
                sell_shares = int(pos["Shares"])
            sp = get_sell_proceeds(current_price, sell_shares)
            txns.append({
                "Date": date_str, "Code": code, "Name": pos.get("Name", ""),
                "Action": "SELL_HALF", "Price": current_price, "Shares": sell_shares,
                "Amount": sp["Amount"], "Commission": sp["Commission"],
                "StampTax": sp["StampTax"], "TotalCost": sp["NetProceeds"],
                "Reason": "止盈减仓_R2", "EntryPrediction": pos.get("EntryShortPrediction", ""),
                "DataSource": quote_source,
            })
            log(f"  {code} P5止盈减仓: {current_price} >= R2({r2:.2f})")

    # ── Step 8: Apply exit transactions ─────────────────
    for txn in txns:
        code = txn["Code"]
        if code not in stock_map:
            continue
        pos = stock_map[code]
        positions["Cash"] = round(positions.get("Cash", 0) + txn["TotalCost"], 2)

        if txn["Action"] == "SELL_HALF":
            pos["Shares"] = int(pos.get("Shares", 0)) - txn["Shares"]
            pos["CurrentPrice"] = txn["Price"]
            pos["UnrealizedPnL"] = round((pos["CurrentPrice"] - pos.get("AvgCost", 0)) * pos["Shares"], 2)
            pos["UnrealizedPnLPct"] = round((pos["CurrentPrice"] / pos.get("AvgCost", 1) - 1) * 100, 2)
        else:
            pos["Shares"] = 0
            pos["CurrentPrice"] = txn["Price"]
            pos["UnrealizedPnL"] = 0
            pos["UnrealizedPnLPct"] = 0
            if "止损" in txn.get("Reason", "") or "趋势恶化" in txn.get("Reason", "") or "预判转空" in txn.get("Reason", ""):
                pos["LastStopLossDate"] = date_str
                cooldowns.setdefault(code, {}).update({"Code": code, "Name": pos.get("Name", ""), "LastStopLossDate": date_str})
            elif "全部止盈" in txn.get("Reason", ""):
                pos["LastFullTakeProfitDate"] = date_str
                cooldowns.setdefault(code, {}).update({"Code": code, "Name": pos.get("Name", ""), "LastFullTakeProfitDate": date_str})

    # ── Step 9: Open new positions ──────────────────────
    log("执行开仓检查...")
    block_auto_open = strict_mode or safety_net_mode

    if strict_mode:
        # Yaozi BUY instructions first
        for code, yd in yaozi_buys.items():
            eval_stock = stocks_eval.get(code)
            if not eval_stock:
                continue
            if stock_map.get(code, {}).get("Shares", 0) > 0:
                log(f"  {code} 腰子BUY指令但已有持仓，跳过", "WARN")
                continue
            cool = cooldowns.get(code, {})
            if cool.get("LastStopLossDate"):
                cool_days = get_cooling_days(cool["LastStopLossDate"], date_str)
                if cool_days < config.get("CooloffPeriodDays", 3):
                    log(f"  {code} 腰子BUY但止损冷却期({cool_days}/{config.get('CooloffPeriodDays', 3)}日)", "WARN")
                    continue
            quote = quotes.get(code, {})
            if quote and quote.get("ChangePct", 999) != 999 and is_limit_up(quote["ChangePct"], code):
                log(f"  {code} 腰子BUY指令但涨停", "WARN")
                continue
            if not eval_stock.get("KeyLevels") or eval_stock["KeyLevels"].get("StopLoss", 0) >= eval_stock.get("Price", 0):
                continue

            pos_pct = get_position_size(eval_stock["Scores"]["Composite"], config.get("PositionSizing", {}).get("Tiers", []))
            if pos_pct <= 0:
                pos_pct = 10
            pos_amount = round(positions["Cash"] * pos_pct / 100, 2)
            max_amount = round(positions.get("TotalValue", positions["Cash"]) * config.get("SingleStockLimitPct", 20) / 100, 2)
            pos_amount = min(pos_amount, max_amount)

            entry_price = quote.get("Price", eval_stock.get("Price", 0)) if quote else eval_stock.get("Price", 0)
            bc = get_buy_cost(entry_price, 100, slippage_pct=config.get("SlippagePct", 0.1))
            shares = int(pos_amount / bc["Price"] // 100 * 100)
            if shares < 100:
                continue
            actual_amount = round(bc["Price"] * shares, 2)
            commission = calc_commission(actual_amount)
            total_cost = actual_amount + commission

            if total_cost > positions["Cash"]:
                shares = int(positions["Cash"] * 0.98 / bc["Price"] // 100 * 100)
                if shares < 100:
                    continue
                actual_amount = round(bc["Price"] * shares, 2)
                commission = calc_commission(actual_amount)
                total_cost = actual_amount + commission

            txn_quote_src = quote.get("DataSource", "[评估数据]") if quote else "[评估数据]"
            reason = yd.get("reason", "")
            override = "_override" if yd.get("risk_override") and yd.get("risk_override_reason") else ""
            if yd.get("risk_override") and yd.get("risk_override_reason"):
                reason = f"{reason} | [风险覆盖]{yd['risk_override_reason']}"

            txns.append({
                "Date": date_str, "Code": code, "Name": CODE_MAP[code]["Name"],
                "Action": "BUY", "Price": bc["Price"], "Shares": shares,
                "Amount": -actual_amount, "Commission": commission, "StampTax": 0,
                "TotalCost": -total_cost, "Reason": reason,
                "Source": f"manual{override}", "EntryPrediction": eval_stock.get("Prediction", {}).get("Short", ""),
                "DataSource": txn_quote_src,
            })
            positions["Cash"] = round(positions["Cash"] - total_cost, 2)
            avg_cost = round(total_cost / shares, 2)
            stock_map[code] = {
                "Code": code, "Name": CODE_MAP[code]["Name"],
                "Shares": shares, "AvgCost": avg_cost, "CurrentPrice": entry_price,
                "EntryDate": date_str, "EntryScore": eval_stock["Scores"]["Composite"],
                "EntryShortPrediction": eval_stock.get("Prediction", {}).get("Short", ""),
                "StopLoss": eval_stock["KeyLevels"]["StopLoss"],
                "Support": eval_stock["KeyLevels"]["Support"],
                "Resistance": eval_stock["KeyLevels"]["Resistance"],
                "UnrealizedPnL": 0, "UnrealizedPnLPct": 0,
                "ShadowEntryPrice": quote.get("PrevClose", 0) if quote.get("PrevClose", 0) > 0 else None,
            }
            yaozi_executed[code] = True
            log(f"  {code} 腰子BUY: {shares} x {bc['Price']} = {actual_amount}")

        # Auto open (non-strict mode)
        if not block_auto_open:
            candidates = []
            for code, info in CODE_MAP.items():
                eval_stock = stocks_eval.get(code)
                if not eval_stock:
                    continue
                if stock_map.get(code, {}).get("Shares", 0) > 0:
                    continue
                pred_short = eval_stock.get("Prediction", {}).get("Short", "")
                if pred_short not in ("看多", "偏多"):
                    continue
                th_label = eval_stock.get("TrendHealth", {}).get("Label", "")
                if th_label in ("危险", "数据不足"):
                    continue
                cool = cooldowns.get(code, {})
                if cool.get("LastStopLossDate"):
                    cd = get_cooling_days(cool["LastStopLossDate"], date_str)
                    if cd < config.get("CooloffPeriodDays", 3):
                        continue
                if cool.get("LastFullTakeProfitDate"):
                    cd = get_cooling_days(cool["LastFullTakeProfitDate"], date_str)
                    if cd < config.get("FullTakeProfitCooldownDays", 5):
                        continue
                quote = quotes.get(code, {})
                if quote and quote.get("ChangePct", 999) != 999 and is_limit_up(quote["ChangePct"], code):
                    continue
                if not eval_stock.get("KeyLevels") or eval_stock["KeyLevels"].get("StopLoss", 0) >= eval_stock.get("Price", 0):
                    continue
                candidates.append({
                    "Code": code, "Name": info["Name"],
                    "CompositeScore": eval_stock["Scores"]["Composite"],
                    "Confidence": eval_stock.get("Prediction", {}).get("Confidence", ""),
                    "ShortBull": eval_stock.get("Prediction", {}).get("ShortBull", 0),
                })

            if candidates:
                conf_map = {"高(>70%)": 3, "中(50-70%)": 2, "低(<50%)": 1}
                candidates.sort(key=lambda c: (-c["CompositeScore"], -conf_map.get(c["Confidence"], 0), -c.get("ShortBull", 0)))

                current_pos_count = sum(1 for p in stock_map.values() if p.get("Shares", 0) > 0)
                slots = config.get("MaxPositions", 6) - current_pos_count
                if slots <= 0:
                    log(f"持仓已满({current_pos_count}/{config.get('MaxPositions', 6)})，不开新仓")
                else:
                    candidates = candidates[:slots]
                    for cand in candidates:
                        code = cand["Code"]
                        eval_stock = stocks_eval[code]
                        quote = quotes.get(code, {})

                        entry_price = 0
                        buy_source = "[评估数据]"
                        if quote.get("OpenPrice", 0) > 0:
                            entry_price = quote["OpenPrice"]
                            buy_source = quote.get("DataSource", "[1]")
                        elif quote.get("PrevClose", 0) > 0:
                            entry_price = quote["PrevClose"]
                            buy_source = "[昨收价]"
                        elif eval_stock.get("Price", 0) > 0:
                            entry_price = eval_stock["Price"]
                        else:
                            continue

                        bc = get_buy_cost(entry_price, 100, slippage_pct=config.get("SlippagePct", 0.1))
                        pos_pct = get_position_size(eval_stock["Scores"]["Composite"], config.get("PositionSizing", {}).get("Tiers", []))
                        pos_amount = round(positions["Cash"] * pos_pct / 100, 2)
                        max_amount = round(positions.get("TotalValue", positions["Cash"]) * config.get("SingleStockLimitPct", 20) / 100, 2)
                        pos_amount = min(pos_amount, max_amount)

                        shares = int(pos_amount / bc["Price"] // 100 * 100)
                        if shares < 100:
                            continue
                        actual_amount = round(bc["Price"] * shares, 2)
                        commission = calc_commission(actual_amount)
                        total_cost = actual_amount + commission
                        if total_cost > positions["Cash"]:
                            continue

                        txns.append({
                            "Date": date_str, "Code": code, "Name": cand["Name"],
                            "Action": "BUY", "Price": bc["Price"], "Shares": shares,
                            "Amount": -actual_amount, "Commission": commission, "StampTax": 0,
                            "TotalCost": -total_cost,
                            "Reason": f"开仓_{eval_stock.get('Prediction', {}).get('Short', '')}_{eval_stock.get('TrendHealth', {}).get('Label', '')}",
                            "EntryPrediction": eval_stock.get("Prediction", {}).get("Short", ""),
                            "DataSource": buy_source,
                        })
                        positions["Cash"] = round(positions["Cash"] - total_cost, 2)
                        stock_map[code] = {
                            "Code": code, "Name": cand["Name"],
                            "Shares": shares, "AvgCost": round(total_cost / shares, 2),
                            "CurrentPrice": entry_price,
                            "EntryDate": date_str,
                            "EntryShortPrediction": eval_stock.get("Prediction", {}).get("Short", ""),
                            "LastStopLossDate": None, "LastFullTakeProfitDate": None,
                            "Support": eval_stock["KeyLevels"]["Support"],
                            "Resistance": eval_stock["KeyLevels"]["Resistance"],
                            "StopLoss": eval_stock["KeyLevels"]["StopLoss"],
                            "UnrealizedPnL": 0, "UnrealizedPnLPct": 0,
                            "ShadowEntryPrice": quote.get("PrevClose", 0) if quote.get("PrevClose", 0) > 0 else None,
                        }
                        log(f"  {code} 开仓: {shares} x {bc['Price']} = {actual_amount}, 仓位{pos_pct}%")

    # ── Step 9.5: Shadow PnL post-processing ─────────────
    for txn in txns:
        code = txn["Code"]
        if txn["Action"] in ("SELL", "SELL_HALF"):
            pos = stock_map.get(code, {})
            shadow_entry = pos.get("ShadowEntryPrice")
            if shadow_entry and shadow_entry > 0:
                txn["ShadowEntryPrice"] = round(shadow_entry, 2)
                txn["ShadowRealizedPnL"] = round((txn["Price"] / shadow_entry - 1) * txn["Shares"] * shadow_entry, 2)
            else:
                txn["ShadowEntryPrice"] = ""
                txn["ShadowRealizedPnL"] = ""
        else:
            txn["ShadowEntryPrice"] = ""
            txn["ShadowRealizedPnL"] = ""

    # ── Step 10: Write transactions (idempotent) ────────
    if txns and not args.dry_run:
        existing_txns = []
        existing_fingerprints = set()
        if os.path.exists(txn_file):
            with open(txn_file, "r", encoding="utf-8") as f:
                lines = f.read().strip().split("\n")
            for line in lines[1:]:  # skip header
                parts = line.split(",")
                if len(parts) >= 5:
                    fp = f"{parts[0]}|{parts[1]}|{parts[3]}|{parts[4]}"
                    existing_fingerprints.add(fp)
                    existing_txns.append(line)

        header = "date,code,name,action,price,shares,amount,commission,stamp_tax,total_cost,reason,entry_prediction,data_source,source,analysis_summary,shadow_entry_price,shadow_realized_pnl"
        new_lines = []
        dup_count = 0
        for t in txns:
            fp = f"{t['Date']}|{t['Code']}|{t['Action']}|{t['Shares']}"
            if fp in existing_fingerprints:
                dup_count += 1
            else:
                src = t.get("Source", "auto")
                analysis = t.get("AnalysisSummary", "")
                shadow_ep = t.get("ShadowEntryPrice", "")
                shadow_pnl = t.get("ShadowRealizedPnL", "")
                line = f"{t['Date']},{t['Code']},{t['Name']},{t['Action']},{t['Price']},{t['Shares']},{t['Amount']},{t['Commission']},{t['StampTax']},{t['TotalCost']},{t['Reason']},{t.get('EntryPrediction', '')},{t.get('DataSource', '[评估数据]')},{src},{analysis},{shadow_ep},{shadow_pnl}"
                new_lines.append(line)

        if new_lines:
            os.makedirs(os.path.dirname(txn_file), exist_ok=True)
            with open(txn_file, "w", encoding="utf-8") as f:
                f.write(header + "\n")
                for line in existing_txns:
                    f.write(line + "\n")
                for line in new_lines:
                    f.write(line + "\n")
            log(f"交易流水已写入: {txn_file} (新增{len(new_lines)}条, 去重{dup_count}条)")

    # ── Step 11: Update positions & snapshot ────────────
    total_stock_value = 0
    total_shadow_unrealized = 0
    for code, pos in stock_map.items():
        if pos.get("Shares", 0) > 0:
            pos["CurrentPrice"] = quotes.get(code, {}).get("Price", pos.get("CurrentPrice", 0))
            pos["UnrealizedPnL"] = round((pos["CurrentPrice"] - pos["AvgCost"]) * pos["Shares"], 2)
            pos["UnrealizedPnLPct"] = round((pos["CurrentPrice"] / pos["AvgCost"] - 1) * 100, 2) if pos["AvgCost"] > 0 else 0
            shadow_ep = pos.get("ShadowEntryPrice")
            if shadow_ep and shadow_ep > 0:
                pos["ShadowUnrealizedPnL"] = round((pos["CurrentPrice"] - shadow_ep) * pos["Shares"], 2)
                total_shadow_unrealized += pos["ShadowUnrealizedPnL"]
            else:
                pos["ShadowUnrealizedPnL"] = None
            total_stock_value += pos["CurrentPrice"] * pos["Shares"]

    total_value = round(positions["Cash"] + total_stock_value, 2)
    positions["TotalValue"] = total_value
    positions["LastUpdated"] = date_str
    positions["Positions"] = stock_map
    positions["Cooldowns"] = cooldowns
    positions["Watchlist"] = watchlist

    if not args.dry_run:
        save_json(positions_file, positions)
        save_json(quotes_cache_file, {code: {"Price": q.get("Price", 0), "Name": q.get("Name", "")}
                                      for code, q in quotes.items()})

        total_real_unrealized = sum(
            (p.get("UnrealizedPnL") or 0) for p in stock_map.values() if p.get("Shares", 0) > 0)
        snapshot = {
            "Date": date_str,
            "TotalValue": total_value,
            "Cash": positions["Cash"],
            "StockValue": total_stock_value,
            "Positions": {code: pos for code, pos in stock_map.items() if pos.get("Shares", 0) > 0},
            "ShadowBenchmark": {
                "TotalRealUnrealizedPnL": round(total_real_unrealized, 2),
                "TotalShadowUnrealizedPnL": round(total_shadow_unrealized, 2),
                "DeltaNote": "影子基准正=昨日收盘入场更优(开盘正向跳空)，负=开盘入场更优" if total_shadow_unrealized != 0 else "",
            },
        }
        save_json(snapshot_file, snapshot)

    log(f"===== 净值: {total_value:.2f} | 现金: {positions['Cash']:.2f} | 持仓市值: {total_stock_value:.2f} =====")
    log("模拟交易完成")


if __name__ == "__main__":
    main()
