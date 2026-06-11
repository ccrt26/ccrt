#!/usr/bin/env python3
"""
UnifiedDataSource — D04 统一数据访问接口（Shadow/Dual-Write 阶段）

10 个查询接口，L1/L2/L3 自动降级。
默认只读已有数据，不做任何分析计算。

l2_cache.db 不存在时严格按两类口径返回：
  A. 普通数据缺口 → _l2_degraded() → data_source="degraded", status="SKIP"
  B. STEP3 边界外   → _not_available_in_step3() → data_source="not_available_in_step3", status="SKIP"

Code level: L0
"""
import json
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path


# ── 根目录检测 ─────────────────────────────────────────────

def detect_root():
    """向上查找 CLAUDE.md 标记文件定位项目根目录"""
    p = Path(__file__).resolve()
    while not (p / "CLAUDE.md").exists():
        p = p.parent
        if p == p.parent:
            return Path.cwd()
    return p


ROOT = detect_root()
DEFAULT_DB_PATH = ROOT / "代码文件" / "数据" / "l2_cache" / "l2_cache.db"
DEFAULT_L1_DIR = ROOT / "代码文件" / "数据"


# ── 工具函数 ──────────────────────────────────────────────

def _safe_read_json(path):
    """安全读取 JSON 文件，失败返回 None"""
    p = Path(path)
    if not p.exists():
        return None
    try:
        size = p.stat().st_size
        if size > 200 * 1024:
            try:
                import orjson
                with open(p, "rb") as f:
                    return orjson.loads(f.read())
            except ImportError:
                pass
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError, ValueError):
        return None


def _now_iso():
    return datetime.now().isoformat()


# ── 主类 ──────────────────────────────────────────────────

class UnifiedDataSource:
    """D04 统一数据访问接口（Shadow/Dual-Write 阶段）

    10 个查询接口，L1/L2/L3 自动降级。
    默认只读已有数据，不做任何分析计算。
    """

    def __init__(self, db_path=None, l1_data_dir=None):
        self._root = ROOT
        self._db_path = Path(db_path) if db_path else DEFAULT_DB_PATH
        self._l1_data_dir = Path(l1_data_dir) if l1_data_dir else DEFAULT_L1_DIR

        # L1 数据文件路径
        self._data_full_path = self._l1_data_dir / "data_full.json"
        self._kline_dir = self._l1_data_dir / "kline_cache"
        self._fund_flow_dir = self._l1_data_dir / "fund_flow_cache"

        # L2 连接（lazy open）
        self._l2_conn = None
        self._l2_available = self._check_l2_available()

        # 注册表（lazy）
        self._registry = None

        # 统计
        self._stats = {"l1_hit": 0, "l2_hit": 0, "l3_hit": 0,
                       "miss": 0, "degraded": 0, "not_available": 0}

    # ── 内部方法 ──────────────────────────────────────────

    def _load_registry(self) -> dict:
        """读取 capability_registry.json 获取 D04 能力边界"""
        if self._registry is not None:
            return self._registry
        reg = _safe_read_json(
            self._root / "00_项目地基" / "02_权威注册表" / "capability_registry.json"
        )
        self._registry = reg or {}
        return self._registry

    def _check_l2_available(self) -> bool:
        """检查 l2_cache.db 是否存在且可读"""
        if not self._db_path.exists():
            return False
        try:
            conn = sqlite3.connect(str(self._db_path))
            conn.execute("SELECT 1 FROM kline LIMIT 1")
            conn.close()
            return True
        except sqlite3.Error:
            return False

    def _table_status(self, table: str) -> str:
        """检查指定表的可用状态。

        Returns:
            'ok'        — 表存在且有条目
            'empty'     — 表存在但无数据
            'no_table'  — 表不存在
            'db_missing'— 数据库不存在或不可读
        """
        if not self._db_path.exists():
            return 'db_missing'
        try:
            conn = sqlite3.connect(str(self._db_path))
            try:
                rows = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                    (table,)
                ).fetchall()
                if not rows:
                    return 'no_table'
                cnt = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                if cnt == 0:
                    return 'empty'
                return 'ok'
            finally:
                conn.close()
        except sqlite3.Error:
            return 'db_missing'

    def _get_l2_conn(self):
        """lazy open L2 连接"""
        if self._l2_conn is None and self._l2_available:
            try:
                self._l2_conn = sqlite3.connect(str(self._db_path))
                self._l2_conn.row_factory = sqlite3.Row
            except sqlite3.Error:
                self._l2_available = False
        return self._l2_conn

    # ── 统一返回格式 ──────────────────────────────────────

    @staticmethod
    def _make_result(data_source, status, data, warnings=None, ttl_hours=24):
        return {
            "data_source": data_source,
            "requested_at": _now_iso(),
            "status": status,
            "data": data,
            "warnings": warnings or [],
            "ttl_hours": ttl_hours,
        }

    # ── 两类降级帮助方法 ──────────────────────────────────

    def _l2_degraded(self, interface_name: str, table: str = None) -> dict:
        """A. 普通数据缺口 — 按原因细分。

        根据 _table_status() 自动区分：
          db_missing → 'l2_cache.db 不存在'
          no_table   → 'L2 {table} 表不存在'
          empty      → 'L2 {table} 表为空'
          其他       → 笼统说明
        """
        self._stats["degraded"] += 1

        if table:
            status = self._table_status(table)
            if status == 'db_missing':
                reason = (f"l2_cache.db 不存在，接口 {interface_name} 跳过 L2 分支。"
                          f"创建 l2_cache.db 需用户单独授权（build_l2_cache.py --dry-run 先行）。")
            elif status == 'no_table':
                reason = f"L2 {table} 表不存在，接口 {interface_name} 跳过 L2 分支。"
            elif status == 'empty':
                reason = f"L2 {table} 表为空，接口 {interface_name} 跳过 L2 分支。"
            else:
                reason = f"L2 {table} 无可用数据，接口 {interface_name} 跳过 L2 分支。"
        elif not self._db_path.exists():
            reason = (f"l2_cache.db 不存在，接口 {interface_name} 跳过 L2 分支。"
                      f"创建 l2_cache.db 需用户单独授权（build_l2_cache.py --dry-run 先行）。")
        else:
            reason = f"L2 数据库不可用，接口 {interface_name} 跳过 L2 分支。"

        return self._make_result(
            data_source="degraded",
            status="SKIP",
            data=None,
            warnings=[reason],
            ttl_hours=0,
        )

    def _not_available_in_step3(self, interface_name: str, reason: str) -> dict:
        """B. STEP3 边界外 — 暂存接口无预计算结果时返回"""
        self._stats["not_available"] += 1
        return self._make_result(
            data_source="not_available_in_step3",
            status="SKIP",
            data=None,
            warnings=[reason],
            ttl_hours=0,
        )

    # =================================================================
    #  公共接口
    # =================================================================

    def get_quote(self, code: str) -> dict:
        """当前行情读取。

        L1: data_full.json Stocks[Code==code] 取内嵌 K 线最新日
        L2: 无（L2 不做实时行情）
        """
        df = _safe_read_json(str(self._data_full_path))
        if not df:
            return self._make_result("unavailable", "WARN", None,
                                     ["data_full.json 不可读"], 1)

        stocks = df.get("Stocks", df.get("stocks", []))
        for s in stocks:
            if str(s.get("Code", s.get("code", ""))) != code:
                continue
            kdates = s.get("KDate") or []
            if not kdates:
                continue
            idx = len(kdates) - 1  # 最新日
            quote = {
                "Code": code,
                "Name": s.get("Name", ""),
                "close": s.get("KClose", [None] * len(kdates))[idx] if idx < len(s.get("KClose", [])) else None,
                "open": s.get("KOpen", [None] * len(kdates))[idx] if idx < len(s.get("KOpen", [])) else None,
                "high": s.get("KHigh", [None] * len(kdates))[idx] if idx < len(s.get("KHigh", [])) else None,
                "low": s.get("KLow", [None] * len(kdates))[idx] if idx < len(s.get("KLow", [])) else None,
                "volume": s.get("KVolume", [None] * len(kdates))[idx] if idx < len(s.get("KVolume", [])) else None,
                "amount": s.get("KAmount", [None] * len(kdates))[idx] if idx < len(s.get("KAmount", [])) else None,
                "change_pct": s.get("ChangePct"),
                "trade_date": kdates[idx],
            }
            self._stats["l1_hit"] += 1
            return self._make_result("l1_live", "PASS", quote, [], 1)

        return self._make_result("unavailable", "WARN", None,
                                 [f"股票 {code} 未在 data_full.json 中找到"], 1)

    def get_kline(self, code: str, days: int = 120) -> dict:
        """K 线历史查询。

        L1: kline_cache/{code}.json 取最近 days 条
        L2: l2_cache.db kline 表（前复权）
        """
        kline_path = self._kline_dir / f"{code}.json"
        l1_data = _safe_read_json(str(kline_path))
        l1_count = len(l1_data) if l1_data else 0

        # L1 充足
        if l1_data and l1_count >= days:
            recent = sorted(l1_data, key=lambda r: r.get("date", ""), reverse=True)[:days]
            self._stats["l1_hit"] += 1
            return self._make_result("l1_live", "PASS", recent, [], 24)

        # L1 部分充足，尝试 L2
        if l1_data and self._l2_available:
            conn = self._get_l2_conn()
            if conn:
                try:
                    extra = conn.execute(
                        "SELECT trade_date as date, open, high, low, close, volume, amount "
                        "FROM kline WHERE code=? ORDER BY trade_date DESC LIMIT ?",
                        (code, days)
                    ).fetchall()
                    if extra:
                        merged = [dict(r) for r in extra]
                        self._stats["l2_hit"] += 1
                        return self._make_result("l2_cache", "PASS", merged, [], 24)
                except sqlite3.Error:
                    pass

        # 仅 L1 且不足
        if l1_data:
            recent = sorted(l1_data, key=lambda r: r.get("date", ""), reverse=True)[:days]
            self._stats["l1_hit"] += 1
            ws = [f"仅返回 L1 数据（{l1_count} 天），小于请求的 {days} 天"]
            if not self._l2_available:
                ws.append("L2 l2_cache.db 不存在")
                return self._make_result("degraded", "WARN", recent, ws, 24)
            return self._make_result("l1_live", "WARN", recent, ws, 24)

        # L2 兜底
        if self._l2_available:
            conn = self._get_l2_conn()
            if conn:
                try:
                    rows = conn.execute(
                        "SELECT trade_date as date, open, high, low, close, volume, amount "
                        "FROM kline WHERE code=? ORDER BY trade_date DESC LIMIT ?",
                        (code, days)
                    ).fetchall()
                    if rows:
                        self._stats["l2_hit"] += 1
                        return self._make_result("l2_cache", "PASS",
                                                 [dict(r) for r in rows], [], 24)
                except sqlite3.Error:
                    pass

        # L2 已检查不可用 → degraded
        if not self._l2_available:
            return self._l2_degraded("get_kline", "kline")

        return self._make_result("unavailable", "BLOCK", None,
                                 [f"股票 {code} 无 K 线数据"], 24)

    def get_score_history(self, code: str, from_date: str, to_date: str) -> dict:
        """评分历史追溯。

        L2: l2_cache.db score_history 表
        L3: 历史数据/04_原始数据/ 归档（兜底）
        """
        if self._l2_available:
            conn = self._get_l2_conn()
            if conn:
                try:
                    rows = conn.execute(
                        "SELECT trade_date, score, rank, bucket, score_type "
                        "FROM score_history WHERE code=? AND trade_date BETWEEN ? AND ? "
                        "ORDER BY trade_date",
                        (code, from_date, to_date)
                    ).fetchall()
                    if rows:
                        self._stats["l2_hit"] += 1
                        return self._make_result("l2_cache", "PASS",
                                                 [dict(r) for r in rows], [], 72)
                    else:
                        # L2 查询成功但该 code 在范围内无记录 → 非系统故障，WARN 不 BLOCK
                        self._stats["l2_hit"] += 1
                        return self._make_result(
                            "l2_cache", "WARN", [],
                            [f"L2 可用但 {code} 在 {from_date}~{to_date} 内无 score_history 记录"],
                            72)
                except sqlite3.Error:
                    pass

        # L3 归档兜底
        archive_root = self._root / "历史数据" / "04_原始数据"
        if archive_root.exists():
            try:
                years = sorted([d for d in archive_root.iterdir()
                                if d.is_dir() and d.name.isdigit()], reverse=True)
                for year_dir in years:
                    for f in sorted(year_dir.glob("*data_scored*.json")):
                        data = _safe_read_json(str(f))
                        if not data:
                            continue
                        bucket_keys = ["Recommendations", "AllStocks", "VetoedStocks"]
                        for bk in bucket_keys:
                            items = data.get(bk, [])
                            if not isinstance(items, list):
                                continue
                            for item in items:
                                if str(item.get("Code", "")) == code:
                                    self._stats["l3_hit"] += 1
                                    return self._make_result(
                                        "fallback_l3", "WARN",
                                        [{"trade_date": f.stem[-10:] if len(f.stem) >= 10 else "",
                                          "score": item.get("TotalScore"),
                                          "rank": item.get("Rank"),
                                          "bucket": bk,
                                          "score_type": "daily"}],
                                        [f"L2 不可用，从 L3 归档读取"],
                                        72
                                    )
            except OSError:
                pass

        if not self._l2_available:
            return self._l2_degraded("get_score_history", "score_history")
        return self._make_result("unavailable", "BLOCK", None,
                                 ["score_history 数据不可用"],
                                 72)

    def get_financials(self, code: str, quarters: int = 4) -> dict:
        """财务指标查询。

        L1: data_full.json Stock.Financials（当前季度）
        L2: l2_cache.db financials 表
        """
        # L1
        df = _safe_read_json(str(self._data_full_path))
        if df:
            stocks = df.get("Stocks", df.get("stocks", []))
            for s in stocks:
                if str(s.get("Code", s.get("code", ""))) != code:
                    continue
                fins = s.get("Financials")
                if fins:
                    self._stats["l1_hit"] += 1
                    result = self._make_result("l1_live", "PASS", fins, [], 168)
                    if not self._l2_available:
                        result["warnings"].append("L2 不存在，仅返回 L1 当前季度财务数据")
                        result["status"] = "WARN"
                    return result

        # L2（当 L1 无数据时）
        if self._l2_available:
            conn = self._get_l2_conn()
            if conn:
                try:
                    rows = conn.execute(
                        "SELECT report_period, metric, value, unit "
                        "FROM financials WHERE code=? ORDER BY report_period DESC LIMIT ?",
                        (code, quarters)
                    ).fetchall()
                    if rows:
                        self._stats["l2_hit"] += 1
                        return self._make_result("l2_cache", "PASS",
                                                 [dict(r) for r in rows], [], 168)
                except sqlite3.Error:
                    pass

        return self._l2_degraded("get_financials", "financials")

    def get_macro(self, indicator: str, months: int = 6) -> dict:
        """宏观数据查询。

        L1: 无
        L2: l2_cache.db macro 表
        """
        if self._l2_available:
            conn = self._get_l2_conn()
            if conn:
                try:
                    rows = conn.execute(
                        "SELECT trade_date, value, unit "
                        "FROM macro WHERE indicator=? ORDER BY trade_date DESC LIMIT ?",
                        (indicator, max(months, 1))
                    ).fetchall()
                    if rows:
                        self._stats["l2_hit"] += 1
                        return self._make_result("l2_cache", "PASS",
                                                 [dict(r) for r in rows], [], 720)
                except sqlite3.Error:
                    pass

        return self._l2_degraded("get_macro", "macro")

    def compare_current_vs_historical(self, code: str, field: str, window: int) -> dict:
        """历史对比查询（接口暂存 D04，Phase 3 迁移 D07）。

        STEP3 仅读取 L2 historical_percentiles 预计算结果。
        不得现场计算 mean/std/percentile，不得输出解读或建议。
        """
        if self._l2_available:
            conn = self._get_l2_conn()
            if conn:
                try:
                    rows = conn.execute(
                        "SELECT trade_date, percentile, metric, window "
                        "FROM historical_percentiles "
                        "WHERE code=? AND metric=? AND window=? "
                        "ORDER BY trade_date DESC LIMIT 1",
                        (code, field, window)
                    ).fetchall()
                    if rows:
                        self._stats["l2_hit"] += 1
                        return self._make_result("l2_cache", "PASS",
                                                 [dict(r) for r in rows], [], 24)
                except sqlite3.Error:
                    pass

        return self._not_available_in_step3(
            "compare_current_vs_historical",
            f"需要 L2 historical_percentiles 表读取预计算结果。"
            f"l2_cache.db 不存在或表不存在或无预计算结果。"
            f"STEP3 不现场计算 mean/std/percentile。"
        )

    def compute_factor_ic(self, factor: str, window: int = 20) -> dict:
        """因子 IC 查询（接口暂存 D04，Phase 3 迁移 D06）。

        STEP3 仅读取预计算结果，不现场计算 IC。
        仅限内置因子：TotalScore, Momentum, Volatility, Turnover, Size, Value, Growth, Quality
        """
        _BUILTIN_FACTORS = {"TotalScore", "Momentum", "Volatility", "Turnover",
                            "Size", "Value", "Growth", "Quality"}
        if factor not in _BUILTIN_FACTORS:
            return self._not_available_in_step3(
                "compute_factor_ic",
                f"因子 '{factor}' 不在内置因子列表中。自定义因子 IC 由 D06 完成。"
            )

        if self._l2_available:
            conn = self._get_l2_conn()
            if conn:
                try:
                    rows = conn.execute(
                        "SELECT trade_date, horizon, return_pct, benchmark_return_pct "
                        "FROM returns WHERE code=? AND horizon=? "
                        "ORDER BY trade_date DESC LIMIT 1",
                        ("_ic_" + factor, f"w{window}")
                    ).fetchall()
                    if rows:
                        self._stats["l2_hit"] += 1
                        return self._make_result("l2_cache", "PASS",
                                                 [dict(r) for r in rows], [], 24)
                except sqlite3.Error:
                    pass

        return self._not_available_in_step3(
            "compute_factor_ic",
            f"需要 L2 returns 表读取因子 '{factor}' 的预计算 IC。"
            f"l2_cache.db 不存在或无预计算结果。STEP3 不现场计算 IC。"
        )

    def get_max_drawdown(self, code: str) -> dict:
        """最大回撤查询（接口暂存 D04，Phase 3 迁移 D08）。

        STEP3 仅读取 L2 risk_metrics 预计算结果，不实时计算。
        """
        if self._l2_available:
            conn = self._get_l2_conn()
            if conn:
                try:
                    rows = conn.execute(
                        "SELECT trade_date, value, metric "
                        "FROM risk_metrics "
                        "WHERE code=? AND metric='max_drawdown' "
                        "ORDER BY trade_date DESC LIMIT 1",
                        (code,)
                    ).fetchall()
                    if rows:
                        self._stats["l2_hit"] += 1
                        return self._make_result("l2_cache", "PASS",
                                                 [dict(r) for r in rows], [], 24)
                except sqlite3.Error:
                    pass

        return self._not_available_in_step3(
            "get_max_drawdown",
            f"需要 L2 risk_metrics 表读取预计算最大回撤。"
            f"l2_cache.db 不存在或无预计算结果。STEP3 不实时计算。"
        )

    def get_volatility_percentile(self, code: str, window: int = 20) -> dict:
        """波动率分位数查询（接口暂存 D04）。

        STEP3 仅读取 L2 historical_percentiles 预计算结果，不计算。
        """
        if self._l2_available:
            conn = self._get_l2_conn()
            if conn:
                try:
                    rows = conn.execute(
                        "SELECT trade_date, percentile, metric, window "
                        "FROM historical_percentiles "
                        "WHERE code=? AND metric=? AND window=? "
                        "ORDER BY trade_date DESC LIMIT 1",
                        (code, f"volatility_{window}", window)
                    ).fetchall()
                    if rows:
                        self._stats["l2_hit"] += 1
                        return self._make_result("l2_cache", "PASS",
                                                 [dict(r) for r in rows], [], 24)
                except sqlite3.Error:
                    pass

        return self._not_available_in_step3(
            "get_volatility_percentile",
            f"需要 L2 historical_percentiles 表读取预计算波动率分位数。"
            f"l2_cache.db 不存在或无预计算结果。STEP3 不计算。"
        )

    def export_factor_panel(self, codes: list, from_date: str, to_date: str) -> dict:
        """因子面板导出（接口暂存 D04，Phase 3 迁移 D06）。

        STEP3 仅读取 L2 预计算面板，不做现场 JOIN 组装。
        不输出回测/交易/投资建议。
        """
        if self._l2_available:
            conn = self._get_l2_conn()
            if conn:
                try:
                    # 尝试读取预计算面板表
                    rows = conn.execute(
                        "SELECT code, trade_date, factor_name, factor_value "
                        "FROM factor_panel "
                        "WHERE trade_date BETWEEN ? AND ? "
                        "ORDER BY trade_date, code",
                        (from_date, to_date)
                    ).fetchall()
                    if rows:
                        self._stats["l2_hit"] += 1
                        return self._make_result("l2_cache", "PASS",
                                                 [dict(r) for r in rows], [], 24)
                except sqlite3.Error:
                    pass

        return self._not_available_in_step3(
            "export_factor_panel",
            f"需要 L2 factor_panel 表读取预计算面板。"
            f"l2_cache.db 不存在或无预计算面板。"
            f"STEP3 不现场 JOIN 组装，不输出回测/交易/投资建议。"
        )

    def report(self) -> str:
        """输出命中率统计"""
        total = sum(self._stats.values())
        if total == 0:
            return "UnifiedDataSource: no requests"
        l1_pct = self._stats["l1_hit"] / total * 100
        l2_pct = self._stats["l2_hit"] / total * 100
        return (f"UnifiedDataSource: {total} requests, "
                f"L1={l1_pct:.0f}%, L2={l2_pct:.0f}%, "
                f"degraded={self._stats['degraded']}, "
                f"not_available={self._stats['not_available']}, "
                f"miss={self._stats['miss']}")
