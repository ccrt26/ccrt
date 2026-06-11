#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统一数据访问层 — 本地优先，5级降级
=====================================
优先级: ①Tushare本地 → ②PS缓存 → ③管线快照 → ④API → ⑤过期兜底 → ⑥null

用法:
    from cached_data_source import CachedDataSource
    ds = CachedDataSource()
    result = ds.get_financial("600114")
    if result["data"]:
        for row in result["data"]:
            print(row)
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


class CachedDataSource:
    """统一数据访问层 — 所有数据获取走此入口"""

    def __init__(self):
        self.stats = {"tushare_hit": 0, "cache_hit": 0, "pipeline_hit": 0,
                      "api_call": 0, "stale_fallback": 0, "miss": 0}

    # ---- 内部方法 ----

    def _load_tushare(self, api_type, code):
        """① Tushare本地历史"""
        path = TUSHARE_DIR / api_type / f"{code}.json"
        data = _safe_read_json(str(path))
        if data and isinstance(data, list) and len(data) > 0:
            self.stats["tushare_hit"] += 1
            return data
        return None

    def _load_ps_cache(self, cache_key):
        """② Power​Shell缓存层"""
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

    def _build_result(self, data, source, freshness, ttl_hours, cached_at=None):
        return {
            "data": data if data else [],
            "source": source,
            "freshness": freshness,
            "cached_at": cached_at or _now_iso(),
            "ttl_hours": ttl_hours,
            "rows": len(data) if data else 0,
        }

    @staticmethod
    def _resolve_target_date(target_date=None):
        """解析目标日期。优先参数，次优环境变量 DAILY_TARGET_DATE。返回 YYYYMMDD。"""
        if target_date:
            return str(target_date).replace("-", "")
        env = os.environ.get("DAILY_TARGET_DATE", "")
        if env:
            return env.replace("-", "")
        return ""

    @staticmethod
    def _has_target_date(data_list, target_date_compact, *date_fields):
        """检查数据列表中是否包含目标日期（任一字段匹配即可）。"""
        if not target_date_compact or not data_list:
            return None  # 未指定目标日期 → 不判断
        if not isinstance(data_list, list):
            data_list = [data_list]
        for row in data_list:
            for field in date_fields:
                val = row.get(field, "")
                if str(val).replace("-", "") == target_date_compact:
                    return True
        return False

    # ---- 公开数据获取方法 ----

    def get_financial(self, code):
        """财务指标 — fina_indicator, TTL=168h(7d)"""
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

    def get_daily_basic(self, code, target_date=None):
        """每日指标 — daily_basic, TTL=24h

        当指定 target_date 时，数据必须包含目标 trade_date 才返回 fresh。
        """
        data = self._load_tushare("daily_basic", code)
        target = self._resolve_target_date(target_date)
        if data:
            if target:
                has = self._has_target_date(data, target, "trade_date", "date")
                if has is False:
                    return self._build_result(None, "tushare-local-no-target",
                                              "stale", 24)
            return self._build_result(data, "tushare-local", "fresh", 24)
        data, ts = self._load_ps_cache(f"daily_basic_{code}")
        if data and _is_fresh(ts, 24):
            if target:
                has = self._has_target_date(data, target, "trade_date", "date")
                if has is False:
                    return self._build_result(None, "ps-cache-no-target",
                                              "stale", 24, ts)
            return self._build_result(data, "ps-cache", "fresh", 24, ts)
        if data:
            self.stats["stale_fallback"] += 1
            return self._build_result(data, "ps-cache-stale", "stale", 24, ts)
        self.stats["miss"] += 1
        return self._build_result(None, "unavailable", "stale", 24)

    def get_moneyflow(self, code, target_date=None):
        """资金流向 — moneyflow, TTL=24h

        当指定 target_date 时，数据必须包含目标 trade_date 才返回 fresh。
        """
        data = self._load_tushare("moneyflow", code)
        target = self._resolve_target_date(target_date)
        if data:
            if target:
                has = self._has_target_date(data, target, "trade_date", "date")
                if has is False:
                    return self._build_result(None, "tushare-local-no-target",
                                              "stale", 24)
            return self._build_result(data, "tushare-local", "fresh", 24)
        data, ts = self._load_ps_cache(f"fundflow_{code}")
        if data and _is_fresh(ts, 24):
            if target:
                has = self._has_target_date(data, target, "trade_date", "date")
                if has is False:
                    return self._build_result(None, "ps-cache-no-target",
                                              "stale", 24, ts)
            return self._build_result(data, "ps-cache", "fresh", 24, ts)
        if data:
            self.stats["stale_fallback"] += 1
            return self._build_result(data, "ps-cache-stale", "stale", 24, ts)
        self.stats["miss"] += 1
        return self._build_result(None, "unavailable", "stale", 24)

    def get_margin(self, code, target_date=None):
        """融资融券 — margin_detail, TTL=24h

        当指定 target_date 时，数据必须包含目标 trade_date 才返回 fresh。
        margin 允许 T+1，但不允许无日期匹配时伪装 fresh。
        """
        data = self._load_tushare("margin_detail", code)
        target = self._resolve_target_date(target_date)
        if data:
            if target:
                # margin 允许 T+1 宽松匹配
                has = self._has_target_date(data, target, "trade_date", "date")
                if has is False:
                    # 尝试 T+1
                    import datetime as dt
                    d = dt.datetime.strptime(target, "%Y%m%d")
                    next_day = (d + dt.timedelta(days=1)).strftime("%Y%m%d")
                    has_next = self._has_target_date(data, next_day, "trade_date", "date")
                    if not has_next:
                        return self._build_result(None, "tushare-local-no-target",
                                                  "stale", 24)
            return self._build_result(data, "tushare-local", "fresh", 24)
        data, ts = self._load_ps_cache(f"margin_{code}")
        if data and _is_fresh(ts, 24):
            if target:
                has = self._has_target_date(data, target, "trade_date", "date")
                if has is False:
                    import datetime as dt
                    d = dt.datetime.strptime(target, "%Y%m%d")
                    next_day = (d + dt.timedelta(days=1)).strftime("%Y%m%d")
                    has_next = self._has_target_date(data, next_day, "trade_date", "date")
                    if not has_next:
                        return self._build_result(None, "ps-cache-no-target",
                                                  "stale", 24, ts)
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
        total = sum(self.stats.values())
        if total == 0:
            return "CachedDataSource: no requests"
        tushare_pct = self.stats["tushare_hit"] / total * 100
        cache_pct = (self.stats["tushare_hit"] + self.stats["cache_hit"] + self.stats["pipeline_hit"]) / total * 100
        return (f"CachedDataSource: {total}请求, "
                f"Tushare命中{tushare_pct:.0f}%, "
                f"本地总命中{cache_pct:.0f}%, "
                f"API调用{self.stats['api_call']}, "
                f"过期兜底{self.stats['stale_fallback']}, "
                f"未命中{self.stats['miss']}")
