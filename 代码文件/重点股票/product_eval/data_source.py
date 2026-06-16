"""
data_source - 本地数据源读取模块。

从本地缓存读取 K 线、daily_basic、moneyflow 数据。
不写任何生产目录，不接入任何新 API/token/cookie。

只读路径：
  - 代码文件/数据/kline_cache/{code}.json
  - 代码文件/数据/tushare/daily_basic/{code}.json
  - 代码文件/数据/tushare/moneyflow/{code}.json
"""

import json
import os
import re
from datetime import datetime, timedelta
from typing import Any, List, Optional, Tuple

from .inventory import PROJECT_ROOT


def _resolve(path: str) -> str:
    if os.path.isabs(path):
        return path
    return os.path.normpath(os.path.join(PROJECT_ROOT, path))


# ---------------------------------------------------------------------------
# 日期归一化
# ---------------------------------------------------------------------------

_DATE_PATTERN_YYYYMMDD = re.compile(r"^\d{8}$")
_DATE_PATTERN_DASH = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def normalize_date(value: Any) -> Optional[str]:
    """将多种日期格式归一化为 YYYYMMDD。

    支持：
      - "2026-06-12"（YYYY-MM-DD）
      - "20260612"  （YYYYMMDD）
      - 20260612     (int)
    """
    if value is None:
        return None
    s = str(value).strip()
    if _DATE_PATTERN_YYYYMMDD.match(s):
        return s
    if _DATE_PATTERN_DASH.match(s):
        return s.replace("-", "")
    return None


def parse_dash_date(value: str) -> Optional[str]:
    """YYYYMMDD → datetime，用于排序"""
    try:
        return datetime.strptime(value, "%Y%m%d")
    except (ValueError, TypeError):
        return None


def row_date(row: dict) -> Optional[str]:
    """从一行 K 线数据中提取归一化日期。"""
    for key in ("trade_date", "date"):
        val = row.get(key)
        if val is not None:
            nd = normalize_date(val)
            if nd:
                return nd
    return None


# ---------------------------------------------------------------------------
# 加载函数
# ---------------------------------------------------------------------------

def load_kline_rows(code: str) -> List[dict]:
    """从 kline_cache 加载 K 线行。

    返回按日期升序排列的行列表。
    每行会额外注入 `_date_norm`（YYYYMMDD）和 `_dt`（datetime）。
    """
    path = f"代码文件/数据/kline_cache/{code}.json"
    full = _resolve(path)
    if not os.path.exists(full):
        return []

    with open(full, "r", encoding="utf-8") as f:
        raw = json.load(f)

    rows = []
    for row in raw:
        nd = row_date(row)
        if nd is None:
            continue
        dt = parse_dash_date(nd)
        if dt is None:
            continue
        enriched = dict(row)
        enriched["_date_norm"] = nd
        enriched["_dt"] = dt
        rows.append(enriched)

    rows.sort(key=lambda r: r["_dt"])
    return rows


def get_kline_until(code: str, as_of_date: str) -> List[dict]:
    """返回 <= as_of_date 的所有 K 线行。

    as_of_date 格式：YYYYMMDD。
    """
    cutoff = int(as_of_date)
    result = []
    for r in load_kline_rows(code):
        nd = r.get("_date_norm", "")
        if nd and int(nd) <= cutoff:
            result.append(r)
    return result


def get_trade_row(rows: List[dict], trade_date: str, as_of_date: str) -> Tuple[Optional[dict], bool]:
    """获取精确交易日行或最近可用交易日行。

    1. 若有精确 trade_date 行，返回该行 + used_last_available=False。
    2. 若没有精确行，取最近一个 <= as_of_date 的行，返回该行 + used_last_available=True。
    3. 若完全无可用数据，返回 (None, False)。

    返回: (row_or_None, used_last_available)
    """
    cutoff = int(as_of_date)
    date_int = int(trade_date)

    exact = None
    last_available = None

    for r in rows:
        nd = r.get("_date_norm", "")
        if not nd:
            continue
        nd_int = int(nd)
        if nd_int > cutoff:
            continue

        if nd_int == date_int:
            exact = r
        if last_available is None or nd_int > int(last_available.get("_date_norm", "0")):
            last_available = r

    if exact is not None:
        return exact, False
    if last_available is not None:
        return last_available, True
    return None, False


def get_close_volume(row: Optional[dict]) -> Tuple[Optional[float], Optional[float]]:
    """从一行获取 close 和 volume（兼容不同字段名）。"""
    if row is None:
        return None, None
    close = row.get("close")
    # volume 可能叫 volume 或 vol
    vol = row.get("volume") or row.get("vol")
    if close is not None:
        close = float(close)
    if vol is not None:
        vol = float(vol)
    return close, vol


# ---------------------------------------------------------------------------
# DailyBasic
# ---------------------------------------------------------------------------

def load_daily_basic_rows(code: str) -> List[dict]:
    """加载 daily_basic JSON（数组），返回按日期升序的行。"""
    path = f"代码文件/数据/tushare/daily_basic/{code}.json"
    full = _resolve(path)
    if not os.path.exists(full):
        return []
    with open(full, "r", encoding="utf-8") as f:
        raw = json.load(f)
    rows = []
    for row in raw:
        td = normalize_date(row.get("trade_date"))
        if td is None:
            continue
        dt = parse_dash_date(td)
        if dt is None:
            continue
        enriched = dict(row)
        enriched["_date_norm"] = td
        enriched["_dt"] = dt
        rows.append(enriched)
    rows.sort(key=lambda r: r["_dt"])
    return rows


def get_daily_basic_row(rows: List[dict], trade_date: str, as_of_date: str) -> Optional[dict]:
    """获取精确或最近 daily_basic 行。"""
    cutoff = int(as_of_date)
    date_int = int(trade_date)

    exact = None
    last_available = None
    for r in rows:
        nd = r.get("_date_norm", "")
        if not nd or int(nd) > cutoff:
            continue
        nd_int = int(nd)
        if nd_int == date_int:
            exact = r
        if last_available is None or nd_int > int(last_available.get("_date_norm", "0")):
            last_available = r
    return exact or last_available


# ---------------------------------------------------------------------------
# 技术指标计算
# ---------------------------------------------------------------------------

def calc_sma(values: List[float], period: int) -> Optional[float]:
    """简单移动平均。样本不足返回 None。"""
    if len(values) < period:
        return None
    return sum(values[-period:]) / period


def calc_rsi(close_prices: List[float], period: int = 14) -> Optional[float]:
    """标准 RSI 计算。样本不足返回 None。"""
    if len(close_prices) < period + 1:
        return None
    gains, losses = 0.0, 0.0
    for i in range(-period, 0):
        diff = close_prices[i] - close_prices[i - 1]
        if diff > 0:
            gains += diff
        else:
            losses -= diff
    if losses == 0:
        return 100.0
    rs = gains / losses
    return 100.0 - (100.0 / (1.0 + rs / period * (period - 1) + rs / period))


def calc_macd(close_prices: List[float]) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    """计算 MACD (dif, dea, hist)。

    样本不足返回 (None, None, None)。
    """
    if len(close_prices) < 26:
        return None, None, None

    # EMA-12
    ema12 = _ema(close_prices, 12)
    # EMA-26
    ema26 = _ema(close_prices, 26)

    dif = ema12[-1] - ema26[-1] if ema12 and ema26 else None
    # For dea, we need dif history
    dif_list = [e12 - e26 for e12, e26 in zip(ema12, ema26)]
    if len(dif_list) < 9:
        return dif, None, None
    dea = sum(dif_list[-9:]) / 9
    hist = 2 * (dif - dea) if dif is not None and dea is not None else None
    return dif, dea, hist


def _ema(values: List[float], period: int) -> List[float]:
    """EMA 计算，返回所有有效 EMA 值列表。"""
    if len(values) < period:
        return []
    multiplier = 2 / (period + 1)
    ema_values = []
    # SMA for first value
    ema = sum(values[:period]) / period
    ema_values.append(ema)
    for v in values[period:]:
        ema = (v - ema) * multiplier + ema
        ema_values.append(ema)
    return ema_values


def compute_lineage_refs(code: str) -> list:
    """计算数据血缘引用。"""
    return [
        f"kline_cache:{code}",
        f"daily_basic:{code}",
    ]


# ---------------------------------------------------------------------------
# 数据质量检查
# ---------------------------------------------------------------------------

def quality_check_kline(row: dict) -> list:
    """检查 K 线数据质量。"""
    flags = []
    close = row.get("close")
    high = row.get("high")
    low = row.get("low")
    open_ = row.get("open")
    if close is not None and float(close) <= 0:
        flags.append("CLOSE_NON_POSITIVE")
    if high is not None and low is not None and float(high) < float(low):
        flags.append("HIGH_LOW_INVERSION")
    if open_ is not None and float(open_) <= 0:
        flags.append("OPEN_NON_POSITIVE")
    return flags
