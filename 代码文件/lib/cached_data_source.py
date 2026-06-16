#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统一数据访问层 — 本地优先，5级降级
=====================================
优先级: ①Tushare本地 → ②PS缓存 → ③管线快照 → ④API → ⑤过期兜底 → ⑥null

用法:
    from cached_data_source import CachedDataSource
    ds = CachedDataSource(target_date="20260616")
    result = ds.get_financial("600114")
    if result["data"]:
        for row in result["data"]:
            print(row)

v2.0 — Freshness gate:
    日频数据（moneyflow/daily_basic/margin_detail）取到 tushare 本地后，
    校验 max(trade_date/date) >= target_date，
    不满足则返回 stale 并计 stale_count，不得阻断 fallback。
"""
import json
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path


def detect_root():
    p = Path(__file__).resolve()
    while not (p / "CLAUDE.md").exists():
        p = p.parent
        if p == p.parent:
            return Path.cwd()
    return p


ROOT = detect_root()
TUSHARE_DIR = ROOT / "代码文件" / "数据" / "tushare"
CACHE_DIR = ROOT / "代码文件" / "每日荐股" / "data_cache"
PIPELINE_SNAPSHOT = ROOT / "代码文件" / "数据" / "data_full.json"


def _safe_read_json(path):
    if os.path.exists(path):
        try:
            size = os.path.getsize(path)
            if size > 200 * 1024:  # >200KB → orjson
                try:
                    import orjson
                    with open(path, "rb") as f:
                        return orjson.loads(f.read())
                except ImportError:
                    pass
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return None


def _is_fresh(cached_at_str, ttl_hours):
    if not cached_at_str:
        return False
    try:
        cached_at = datetime.fromisoformat(cached_at_str)
        return (datetime.now() - cached_at) < timedelta(hours=ttl_hours)
    except Exception:
        return False


def _ts_code(code):
    return f"{code}.SH" if code.startswith(("6", "9")) else f"{code}.SZ"


def _now_iso():
    return datetime.now().isoformat()


def norm_date(value):
    """标准化日期：YYYY-MM-DD / YYYYMMDD → YYYYMMDD"""
    return str(value or "").replace("-", "").replace(" ", "").replace("/", "")[:8]


def _max_record_date(rows, fields=("trade_date", "date")):
    """从记录列表中找出最大日期（YYYYMMDD）。rows 为空返回空串。"""
    max_d = ""
    for row in rows if isinstance(rows, list) else []:
        for f in fields:
            v = row.get(f)
            if v:
                nd = norm_date(v)
                if nd and nd > max_d:
                    max_d = nd
    return max_d


class CachedDataSource:
    """统一数据访问层 — 所有数据获取走此入口

    target_date: 可选目标日期（YYYYMMDD）。日频数据将根据此日期判断 fresh/stale。
                 来源优先级：构造参数 > 环境变量 DAILY_TARGET_DATE > 不检查。
    """

    def __init__(self, target_date=""):
        self.target_date = norm_date(target_date or os.environ.get("DAILY_TARGET_DATE", ""))
        self.stats = {"tushare_hit": 0, "cache_hit": 0, "pipeline_hit": 0,
                      "api_call": 0, "stale_fallback": 0, "miss": 0,
                      "stale_count": 0, "fallback_hit": 0, "fallback_miss": 0}

    # ---- 内部方法 ----

    def _load_tushare(self, api_type, code):
        """① Tushare本地历史（基础版本，无日期校验）"""
        path = TUSHARE_DIR / api_type / f"{code}.json"
        data = _safe_read_json(str(path))
        if data and isinstance(data, list) and len(data) > 0:
            self.stats["tushare_hit"] += 1
            return data
        return None

    def _load_tushare_daily(self, api_type, code, target_date, date_fields=("trade_date", "date")):
        """① Tushare本地日频数据 — 带目标日新鲜度校验。

        返回 (data, freshness, stale_reason)
        - data: rows 列表或 None
        - freshness: "fresh" | "stale"
        - stale_reason: 空串（fresh/无target_date）或描述
        """
        path = TUSHARE_DIR / api_type / f"{code}.json"
        data = _safe_read_json(str(path))
        if data and isinstance(data, list) and len(data) > 0:
            max_d = _max_record_date(data, date_fields)
            if self.target_date and max_d and max_d < self.target_date:
                # 文件存在但最新记录早于目标日 — stale
                self.stats["stale_count"] += 1
                reason = f"max_date={max_d} < target_date={self.target_date}"
                return data, "stale", reason
            # fresh（含未设 target_date 的旧行为兼容）
            self.stats["tushare_hit"] += 1
            return data, "fresh", ""
        if data:
            # 文件存在但空列表
            self.stats["stale_count"] += 1
            return data, "stale", "empty_rows"
        return None, "miss", "no_file"

    def _load_ps_cache(self, cache_key):
        """② PowerShell缓存层"""
        path = CACHE_DIR / f"{cache_key}.json"
        data = _safe_read_json(str(path))
        if data:
            ts = data.get("Timestamp") if isinstance(data, dict) else None
            inner = data.get("Data") if isinstance(data, dict) else None
            if inner and isinstance(inner, list) and len(inner) > 0:
                self.stats["cache_hit"] += 1
                return inner, ts
        return None, None

    def _load_pipeline_snapshot(self, code):
        """③ 当日管线快照 data_full.json"""
        data = _safe_read_json(str(PIPELINE_SNAPSHOT))
        if data:
            stocks = data.get("Stocks", data.get("stocks", []))
            for s in stocks:
                if s.get("Code", s.get("code", "")) == code:
                    self.stats["pipeline_hit"] += 1
                    return s
        return None

    def _build_result(self, data, source, freshness, ttl_hours, cached_at=None,
                      stale_reason="", data_max_date=""):
        return {
            "data": data if data else [],
            "source": source,
            "freshness": freshness,
            "cached_at": cached_at or _now_iso(),
            "ttl_hours": ttl_hours,
            "rows": len(data) if data else 0,
            "target_date": self.target_date if self.target_date else "",
            "data_max_date": data_max_date,
            "stale_reason": stale_reason,
        }

    # ---- 公开数据获取方法 ----

    def get_financial(self, code):
        """财务指标 — fina_indicator, TTL=168h(7d)，非日频不过滤 target_date"""
        # ① Tushare本地
        data = self._load_tushare("fina_indicator", code)
        if data:
            return self._build_result(data, "tushare-local", "fresh", 168)
        # ② PS缓存
        data, ts = self._load_ps_cache(f"financial_{code}")
        if data and _is_fresh(ts, 168):
            return self._build_result(data, "ps-cache", "fresh", 168, ts)
        # ⑤ 过期兜底
        if data:
            self.stats["stale_fallback"] += 1
            return self._build_result(data, "ps-cache-stale", "stale", 168, ts)
        # ⑥ 不可获取
        self.stats["miss"] += 1
        return self._build_result(None, "unavailable", "stale", 168)

    def get_daily_basic(self, code):
        """每日指标 — daily_basic, TTL=24h，日频校验 target_date"""
        data, freshness, reason = self._load_tushare_daily("daily_basic", code, self.target_date)
        if data and freshness == "fresh":
            max_d = _max_record_date(data, ("trade_date", "date"))
            return self._build_result(data, "tushare-local", "fresh", 24,
                                      stale_reason=reason, data_max_date=max_d)
        if data:
            # stale — 不得计 tushare_hit，走后续降级
            max_d = _max_record_date(data, ("trade_date", "date"))
            return self._build_result(data, "tushare-local-stale", "stale", 24,
                                      stale_reason=reason, data_max_date=max_d)
        # ② PS缓存
        data, ts = self._load_ps_cache(f"daily_basic_{code}")
        if data and _is_fresh(ts, 24):
            return self._build_result(data, "ps-cache", "fresh", 24, ts)
        if data:
            self.stats["stale_fallback"] += 1
            return self._build_result(data, "ps-cache-stale", "stale", 24, ts)
        self.stats["miss"] += 1
        return self._build_result(None, "unavailable", "stale", 24)

    def get_moneyflow(self, code):
        """资金流向 — moneyflow, TTL=24h，日频校验 target_date。

        若 moneyflow 文件存在但 max_date < target_date，返回 freshness="stale"，
        source="tushare-local-stale"，不得阻断 batch_data_collector 的 THS fallback。
        """
        data, freshness, reason = self._load_tushare_daily("moneyflow", code, self.target_date)
        if data and freshness == "fresh":
            max_d = _max_record_date(data, ("trade_date", "date"))
            return self._build_result(data, "tushare-local", "fresh", 24,
                                      stale_reason=reason, data_max_date=max_d)
        if data:
            # stale — 不得计 tushare_hit，不得阻断 fallback
            max_d = _max_record_date(data, ("trade_date", "date"))
            return self._build_result(data, "tushare-local-stale", "stale", 24,
                                      stale_reason=reason, data_max_date=max_d)
        # ② PS缓存
        data, ts = self._load_ps_cache(f"fundflow_{code}")
        if data and _is_fresh(ts, 24):
            return self._build_result(data, "ps-cache", "fresh", 24, ts)
        if data:
            self.stats["stale_fallback"] += 1
            return self._build_result(data, "ps-cache-stale", "stale", 24, ts)
        self.stats["miss"] += 1
        return self._build_result(None, "unavailable", "stale", 24)

    def get_margin(self, code):
        """融资融券 — margin_detail, TTL=24h，日频校验 target_date"""
        data, freshness, reason = self._load_tushare_daily("margin_detail", code, self.target_date)
        if data and freshness == "fresh":
            max_d = _max_record_date(data, ("trade_date", "date"))
            return self._build_result(data, "tushare-local", "fresh", 24,
                                      stale_reason=reason, data_max_date=max_d)
        if data:
            max_d = _max_record_date(data, ("trade_date", "date"))
            return self._build_result(data, "tushare-local-stale", "stale", 24,
                                      stale_reason=reason, data_max_date=max_d)
        data, ts = self._load_ps_cache(f"margin_{code}")
        if data and _is_fresh(ts, 24):
            return self._build_result(data, "ps-cache", "fresh", 24, ts)
        if data:
            self.stats["stale_fallback"] += 1
            return self._build_result(data, "ps-cache-stale", "stale", 24, ts)
        self.stats["miss"] += 1
        return self._build_result(None, "unavailable", "stale", 24)

    def get_kline(self, code, days=120):
        """K线 — 暂无Tushare daily同步, TTL=24h, 返回null触发API降级"""
        data, ts = self._load_ps_cache(f"kline_{code}")
        if data and _is_fresh(ts, 24):
            return self._build_result(data, "ps-cache", "fresh", 24, ts)
        self.stats["miss"] += 1
        return self._build_result(None, "unavailable-needs-api", "stale", 24)

    def get_quote(self, code):
        """实时行情 — 无Tushare等价物, TTL=1h, 需API"""
        data, ts = self._load_ps_cache(f"quote_{code}")
        if data and _is_fresh(ts, 1):
            return self._build_result(data, "ps-cache", "fresh", 1, ts)
        if data:
            self.stats["stale_fallback"] += 1
            return self._build_result(data, "ps-cache-stale", "stale", 1, ts)
        self.stats["miss"] += 1
        return self._build_result(None, "unavailable-needs-api", "stale", 1)

    def get_northbound(self, code):
        """北向资金 — hk_hold, TTL=24h"""
        data = self._load_tushare("hk_hold", code)
        if data:
            return self._build_result(data, "tushare-local", "fresh", 24)
        self.stats["miss"] += 1
        return self._build_result(None, "unavailable", "stale", 24)

    def get_holder_number(self, code):
        """股东人数 — TTL=168h"""
        data = self._load_tushare("holder_number", code)
        if data:
            return self._build_result(data, "tushare-local", "fresh", 168)
        self.stats["miss"] += 1
        return self._build_result(None, "unavailable", "stale", 168)

    def get_pledge(self, code):
        """股权质押 — TTL=24h"""
        data = self._load_tushare("pledge", code)
        if data:
            return self._build_result(data, "tushare-local", "fresh", 24)
        self.stats["miss"] += 1
        return self._build_result(None, "unavailable", "stale", 24)

    def get_forecast(self, code):
        """业绩预告 — TTL=168h"""
        data = self._load_tushare("forecast", code)
        if data:
            return self._build_result(data, "tushare-local", "fresh", 168)
        self.stats["miss"] += 1
        return self._build_result(None, "unavailable", "stale", 168)

    def get_mainbz(self, code):
        """主营业务构成 — TTL=168h"""
        data = self._load_tushare("fina_mainbz", code)
        if data:
            return self._build_result(data, "tushare-local", "fresh", 168)
        self.stats["miss"] += 1
        return self._build_result(None, "unavailable", "stale", 168)

    def get_pipeline_snapshot(self, code):
        """读取管线快照中某只股票的完整数据"""
        snap = self._load_pipeline_snapshot(code)
        if snap:
            return self._build_result(snap, "pipeline-snapshot", "fresh", 24)
        return self._build_result(None, "unavailable", "stale", 24)

    def report(self):
        """输出命中率统计"""
        total = sum(v for k, v in self.stats.items() if k != "stale_count" and k != "fallback_hit" and k != "fallback_miss")
        if total == 0:
            return "CachedDataSource: no requests"
        tushare_pct = self.stats["tushare_hit"] / total * 100
        cache_pct = (self.stats["tushare_hit"] + self.stats["cache_hit"] + self.stats["pipeline_hit"]) / total * 100
        stale_info = f", stale_count={self.stats['stale_count']}" if self.stats["stale_count"] else ""
        fb_info = f", fallback_hit={self.stats['fallback_hit']}, fallback_miss={self.stats['fallback_miss']}"
        return (f"CachedDataSource: {total}请求, "
                f"Tushare命中{tushare_pct:.0f}%, "
                f"本地总命中{cache_pct:.0f}%, "
                f"API调用{self.stats['api_call']}, "
                f"过期兜底{self.stats['stale_fallback']}, "
                f"未命中{self.stats['miss']}"
                f"{stale_info}{fb_info}")
