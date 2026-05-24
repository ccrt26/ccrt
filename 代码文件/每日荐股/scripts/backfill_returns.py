#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
铁律量化 · 收益回填脚本 v2.0
=============================
路线二 阶段A — 用K线历史数据回填 score_history.jsonl 中目标变量 (ret_t1/t3/t5)

架构原则（应对电脑不天天开机）:
  - 回填不依赖"当日实时价格"，改用新浪K线历史数据
  - K线返回最近60-100个交易日，覆盖任意长度关机窗口
  - 按股票批量取K线(每只1次请求)，填充该股票所有null记录
  - 自动跳过周末/节假日（K线只有交易日，天然对齐）

用法:
  python backfill_returns.py                        # 回填所有 null 记录
  python backfill_returns.py --date 2026-05-22      # 仅回填指定日期
  python backfill_returns.py --catch-up             # 追赶模式：含T+0当天(收盘后)
  python backfill_returns.py --dry-run              # 预览，不写入
  python backfill_returns.py --stats                # 仅打印覆盖率统计

执行时机: 每日 15:30 后（收盘），或 20:00 评分流水线之前
依赖: 新浪K线 money.finance.sina.com.cn（数据源[2]）
"""
import json, os, sys, time, argparse, urllib.request, urllib.error
from datetime import date, timedelta
from collections import defaultdict

ROOT = r"C:\Users\34269\Documents\Claude\股票分析"
HISTORY_FILE = os.path.join(ROOT, "代码文件", "数据", "score_history.jsonl")

# ---------- 新浪K线 (数据源[2]) ----------
def fetch_kline_bars(code, days=100):
    """获取个股日K线。返回 [{day, open, high, low, close, volume}, ...] 按日期升序。
    关机后重新调用仍返回最近 `days` 根K线，覆盖历史窗口。
    """
    prefix = "sh" if code.startswith("6") else "sz"
    url = (f"https://money.finance.sina.com.cn/quotes_service/api/"
           f"json_v2.php/CN_MarketData.getKLineData?"
           f"symbol={prefix}{code}&scale=240&ma=no&datalen={days}")

    bars = []
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0",
                "Referer": "https://finance.sina.com.cn"
            })
            with urllib.request.urlopen(req, timeout=15) as resp:
                text = resp.read().decode("gbk", errors="replace")
            # 新浪返回格式: [{day:"2026-05-22", open:"10.50", ...}, ...]
            raw = json.loads(text)
            for b in raw:
                try:
                    bars.append({
                        "day": b.get("day", ""),
                        "close": float(b.get("close", 0)),
                        "open": float(b.get("open", 0)),
                        "high": float(b.get("high", 0)),
                        "low": float(b.get("low", 0)),
                        "volume": float(b.get("volume", 0))
                    })
                except (ValueError, TypeError):
                    continue
            break
        except (urllib.error.URLError, OSError, json.JSONDecodeError) as e:
            if attempt < 2:
                time.sleep(2.0)
            else:
                # 静默失败，返回空列表
                pass
    return bars


def build_date_index(bars):
    """从K线bars构建 {date_str: close_price} 和排序后的交易日列表。"""
    date_to_close = {}
    trading_dates = []
    for b in bars:
        d = b["day"]
        if d and b["close"] > 0:
            date_to_close[d] = b["close"]
            trading_dates.append(d)
    trading_dates.sort()
    return date_to_close, trading_dates


def get_future_close(trading_dates, date_to_close, from_date, offset_days):
    """获取 from_date 之后第 offset_days 个交易日的收盘价。
    offset_days=1 → T+1, offset_days=3 → T+3, offset_days=5 → T+5
    如果 from_date 不在 trading_dates 中或超出范围，返回 None。
    """
    try:
        idx = trading_dates.index(from_date)
        target_idx = idx + offset_days
        if target_idx < len(trading_dates):
            target_date = trading_dates[target_idx]
            return date_to_close.get(target_date)
    except (ValueError, IndexError):
        pass
    return None


# ---------- 核心逻辑 ----------
def backfill(target_date=None, dry_run=False, catch_up=False):
    """读取 score_history.jsonl，用K线历史数据回填 null 目标变量。"""
    if not os.path.exists(HISTORY_FILE):
        print(f"[backfill] {HISTORY_FILE} 不存在，无需回填")
        return

    # 读取全部记录
    records = []
    with open(HISTORY_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    if not records:
        print("[backfill] 无记录")
        return

    # 筛选需回填的记录
    today = date.today().strftime("%Y-%m-%d")
    pending_by_code = defaultdict(list)  # code → [(idx, rec), ...]
    for i, rec in enumerate(records):
        rec_date = rec.get("date", "")
        if target_date and rec_date != target_date:
            continue
        # catch_up模式允许回填当天(收盘后T+0→T+1价格已知)
        if not catch_up and rec_date >= today:
            continue
        if rec.get("ret_t1") is None:
            pending_by_code[rec.get("code", "")].append((i, rec))

    total_pending = sum(len(v) for v in pending_by_code.values())
    if total_pending == 0:
        print(f"[backfill] 无需回填 (target={target_date or 'all'}, today={today}, "
              f"catch_up={catch_up})")
        show_stats(records)
        return

    print(f"[backfill] 回填 {total_pending} 条记录 ({len(pending_by_code)} 只股票)...")

    # 按股票批量取K线
    updated = 0
    failed_codes = []
    for code, pending_list in pending_by_code.items():
        bars = fetch_kline_bars(code, days=100)
        if not bars:
            failed_codes.append(code)
            continue

        date_to_close, trading_dates = build_date_index(bars)
        if not trading_dates:
            failed_codes.append(code)
            continue

        for idx, rec in pending_list:
            rec_date = rec.get("date", "")
            t_close = date_to_close.get(rec_date)

            # 如果K线中有记录日的收盘价，用它修正 price 字段
            if t_close and t_close > 0:
                rec["price"] = round(t_close, 2)

            # ret_t1
            t1_close = get_future_close(trading_dates, date_to_close, rec_date, 1)
            if t1_close and t_close and t_close > 0:
                rec["ret_t1"] = round((t1_close - t_close) / t_close * 100, 2)

            # ret_t3
            t3_close = get_future_close(trading_dates, date_to_close, rec_date, 3)
            if t3_close and t_close and t_close > 0:
                rec["ret_t3"] = round((t3_close - t_close) / t_close * 100, 2)

            # ret_t5
            t5_close = get_future_close(trading_dates, date_to_close, rec_date, 5)
            if t5_close and t_close and t_close > 0:
                rec["ret_t5"] = round((t5_close - t_close) / t_close * 100, 2)

            # ret_t1_vs_market: 暂存原始值，市场超额待数据积累后批量计算
            if rec.get("ret_t1") is not None:
                rec["ret_t1_vs_market"] = rec["ret_t1"]
                updated += 1

        # 请求间隔（新浪限速）
        time.sleep(0.4)

    if failed_codes:
        print(f"  [WARN] {len(failed_codes)} 只股票K线获取失败，下次运行重试")

    if dry_run:
        print(f"[backfill] DRY RUN: 将更新 {updated} 条 (共 {total_pending} 条待处理)")
        for code, pending_list in list(pending_by_code.items())[:3]:
            for idx, rec in pending_list[:2]:
                print(f"  {rec['date']} {rec['code']} {rec['name']}: "
                      f"price={rec.get('price')} → ret_t1={rec.get('ret_t1')}, "
                      f"ret_t3={rec.get('ret_t3')}, ret_t5={rec.get('ret_t5')}")
        return

    # 写回
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    print(f"[backfill] 完成: 更新 {updated}/{total_pending} 条 "
          f"(共 {len(records)} 条总记录, {len(failed_codes)} 只股票K线失败)")
    show_stats(records)


def show_stats(records):
    """打印覆盖率统计。"""
    total = len(records)
    filled_t1 = sum(1 for r in records if r.get("ret_t1") is not None)
    filled_t3 = sum(1 for r in records if r.get("ret_t3") is not None)
    filled_t5 = sum(1 for r in records if r.get("ret_t5") is not None)

    if total == 0:
        return

    # 按日期统计覆盖
    dates = defaultdict(lambda: {"total": 0, "filled": 0})
    for r in records:
        d = r.get("date", "?")
        dates[d]["total"] += 1
        if r.get("ret_t1") is not None:
            dates[d]["filled"] += 1

    print(f"[backfill] 覆盖率: ret_t1={filled_t1}/{total} ({filled_t1/total*100:.0f}%), "
          f"ret_t3={filled_t3}/{total}, ret_t5={filled_t5}/{total}")

    # 标注有缺口的日期
    gap_dates = [d for d, v in dates.items() if v["filled"] < v["total"]]
    if gap_dates:
        gap_dates.sort()
        print(f"[backfill] 数据缺口: {len(gap_dates)} 个日期 ret_t1 不完整 "
              f"({' '.join(gap_dates[-5:])}{'...' if len(gap_dates) > 5 else ''})")

    # ret_t1 分布
    rets = [r["ret_t1"] for r in records if r.get("ret_t1") is not None]
    if rets:
        win_rate = sum(1 for x in rets if x > 0) / len(rets) * 100
        print(f"[backfill] ret_t1 分布: n={len(rets)}, "
              f"mean={sum(rets)/len(rets):+.2f}%, "
              f"win_rate={win_rate:.0f}%, "
              f"range=[{min(rets):+.2f}%, {max(rets):+.2f}%]")


# ---------- CLI ----------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="回填 score_history.jsonl 目标变量 (K线历史数据)")
    parser.add_argument("--date", type=str, default=None,
                        help="仅回填指定日期 (YYYY-MM-DD)")
    parser.add_argument("--catch-up", action="store_true",
                        help="追赶模式：允许回填T+0当天记录（收盘后K线已包含今日）")
    parser.add_argument("--dry-run", action="store_true",
                        help="预览模式，不写入")
    parser.add_argument("--stats", action="store_true",
                        help="仅打印覆盖率统计，不回填")
    args = parser.parse_args()

    if args.stats:
        if os.path.exists(HISTORY_FILE):
            records = []
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            records.append(json.loads(line))
                        except json.JSONDecodeError:
                            pass
            show_stats(records)
        else:
            print(f"[backfill] {HISTORY_FILE} 不存在")
    else:
        backfill(target_date=args.date, dry_run=args.dry_run, catch_up=args.catch_up)
