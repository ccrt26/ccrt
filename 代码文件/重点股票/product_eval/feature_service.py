"""
FeatureSnapshot - 特征快照服务（真实 K 线计算版）。

从 data_source 读取本地 kline_cache，计算真实技术特征。
不再返回占位 None 值。

所有 label_values 标明 label_status 和 label_visibility。
"""

import os
import uuid
from datetime import datetime, timezone
from typing import Any, List, Optional

from . import data_source as ds


class FeatureSnapshotService:
    """特征快照服务。"""

    def __init__(self, data_root: Optional[str] = None):
        self.data_root = data_root or ds.PROJECT_ROOT

    # ------------------------------------------------------------------
    # 核心入口
    # ------------------------------------------------------------------

    def get_features(
        self,
        stock_code: str,
        trade_date: str,
        as_of_date: str,
        market_lag_days: int = 0,
    ) -> dict[str, Any]:
        cutoff = self._compute_cutoff(as_of_date, market_lag_days)

        # 加载 K 线
        kline_rows = ds.get_kline_until(stock_code, cutoff)
        db_rows = ds.load_daily_basic_rows(stock_code)

        # 获取交易日行
        trade_row, used_last = ds.get_trade_row(kline_rows, trade_date, cutoff)

        # 未来函数检查
        ff_check = self._check_future_function(kline_rows, cutoff)

        # 技术特征计算
        tech_features, tech_quality_flags = self._compute_technical(
            kline_rows, trade_row, trade_date, cutoff, used_last
        )

        # Baseline 特征
        baseline_features = self._get_baseline_features(stock_code, trade_date)

        # 风险标签
        risk_flags = self._get_risk_flags(stock_code, trade_date, cutoff)

        # 标签值（后验，不进入 feature_values）
        label_values, label_quality = self._compute_labels(
            kline_rows, trade_row, trade_date, cutoff
        )

        quality_flags = list(tech_quality_flags)

        # Freshness
        if used_last:
            quality_flags.append("TRADE_DATE_ROLLBACK_TO_LAST_AVAILABLE")

        freshness_status = self._check_freshness(quality_flags, used_last)

        if ff_check["as_of_check"] != "PASS":
            quality_flags.append(f"FUTURE_FUNCTION_{ff_check['as_of_check']}")

        actual_trade_date = trade_row.get("_date_norm", "") if trade_row else None
        source_row_date = trade_row.get("_date_norm", "") if trade_row else None

        snapshot: dict[str, Any] = {
            "snapshot_id": self._generate_snapshot_id(stock_code, trade_date),
            "stock_code": stock_code,
            "stock_name": self._get_stock_name(stock_code),
            "trade_date": trade_date,
            "as_of_date": as_of_date,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "feature_values": {
                "technical": tech_features,
                "baseline": baseline_features,
                "risk_flags": risk_flags,
            },
            "label_values": label_values,
            "baseline_id": baseline_features.get("baseline_id", ""),
            "data_lineage_refs": ds.compute_lineage_refs(stock_code),
            "quality_flags": quality_flags,
            "freshness_status": freshness_status,
            "reconstructed_snapshot": self._is_reconstructed(trade_date, as_of_date),
            "future_function_check": ff_check,
            "deferred_feature_refs": {
                "financial_feature_ref": "DEFERRED_PHASE_2",
                "event_feature_ref": "DEFERRED_PHASE_2",
                "crowding_feature_ref": "DEFERRED_PHASE_3",
            },
        }
        return snapshot

    # ------------------------------------------------------------------
    # 技术特征计算
    # ------------------------------------------------------------------

    def _compute_technical(
        self,
        kline_rows: List[dict],
        trade_row: Optional[dict],
        trade_date: str,
        cutoff: str,
        used_last: bool,
    ) -> tuple:
        """计算技术特征。若 kline 完全无可用数据，返回 None 特征 + MARKET_DATA_MISSING。"""
        quality_flags = []
        if not kline_rows or trade_row is None:
            quality_flags.append("MARKET_DATA_MISSING")
            return {
                "actual_trade_date": None,
                "source_row_date": None,
                "close": None, "volume": None,
                "ma5": None, "ma20": None, "ma60": None,
                "rsi14": None,
                "macd": None,
                "turnover_rate": None,
                "volume_ratio": None,
                "used_last_available_trade_date": used_last,
            }, quality_flags

        # 基础数据
        close, volume = ds.get_close_volume(trade_row)
        nd = trade_row.get("_date_norm", "")
        actual_trade_date = nd

        # 技术指标需要的收盘价序列
        close_prices = [float(r.get("close", 0)) for r in kline_rows
                        if r.get("close") is not None and float(r.get("close")) > 0]

        # 计算 MA
        ma5 = self._calc_ma(close_prices, 5)
        ma20 = self._calc_ma(close_prices, 20)
        ma60 = self._calc_ma(close_prices, 60)

        # RSI
        rsi14 = ds.calc_rsi(close_prices, 14)
        if rsi14 is None:
            quality_flags.append("RSI14_INSUFFICIENT_HISTORY")

        # MACD
        macd_dif, macd_dea, macd_hist = ds.calc_macd(close_prices)
        if macd_dif is None:
            quality_flags.append("MACD_INSUFFICIENT_HISTORY")
        macd_output = None
        if macd_dif is not None:
            macd_output = {"dif": macd_dif, "dea": macd_dea, "hist": macd_hist}

        # 从 daily_basic 读取 turnover_rate 和 volume_ratio
        db_rows = ds.load_daily_basic_rows(trade_row.get("stock_code", "")[:6])
        if not db_rows:
            db_rows = ds.load_daily_basic_rows(trade_date[:6])

        db_row = ds.get_daily_basic_row(db_rows, nd, cutoff)
        turnover_rate = None
        volume_ratio = None
        if db_row:
            turnover_rate = db_row.get("turnover_rate")
            volume_ratio = db_row.get("volume_ratio")
            if turnover_rate is not None:
                turnover_rate = float(turnover_rate)
            if volume_ratio is not None:
                volume_ratio = float(volume_ratio)

        # 数据质量检查
        quality_flags.extend(ds.quality_check_kline(trade_row))

        tech = {
            "actual_trade_date": actual_trade_date,
            "source_row_date": actual_trade_date,
            "close": close,
            "volume": volume,
            "ma5": ma5,
            "ma20": ma20,
            "ma60": ma60,
            "rsi14": rsi14,
            "macd": macd_output,
            "turnover_rate": turnover_rate,
            "volume_ratio": volume_ratio,
            "used_last_available_trade_date": used_last,
        }
        return tech, quality_flags

    @staticmethod
    def _calc_ma(prices: List[float], period: int) -> Optional[float]:
        return ds.calc_sma(prices, period)

    # ------------------------------------------------------------------
    # 标签值（后验）
    # ------------------------------------------------------------------

    def _compute_labels(
        self,
        kline_rows: List[dict],
        trade_row: Optional[dict],
        trade_date: str,
        cutoff: str,
    ) -> tuple:
        """计算后验标签值。

        Labels 只能用于 backtest/evaluation，不得进入 feature_values。
        若 forward 数据不足，label_status=INSUFFICIENT_FORWARD_DATA。
        """
        if not kline_rows or trade_row is None:
            return {
                "ret_t1": None, "ret_t5": None, "ret_t20": None, "ret_t60": None,
                "max_drawdown": None, "relative_return": None,
                "label_status": "INSUFFICIENT_FORWARD_DATA",
                "label_visibility": "POST_OUTCOME_NOT_FEATURE",
            }, []

        # 找到 trade_row 在 kline_rows 中的位置
        nrm = trade_row.get("_date_norm", "")
        idx = None
        for i, r in enumerate(kline_rows):
            if r.get("_date_norm", "") == nrm:
                idx = i
                break
        if idx is None:
            return {
                "ret_t1": None, "ret_t5": None, "ret_t20": None, "ret_t60": None,
                "max_drawdown": None, "relative_return": None,
                "label_status": "INSUFFICIENT_FORWARD_DATA",
                "label_visibility": "POST_OUTCOME_NOT_FEATURE",
            }, []

        close_at_trade = float(kline_rows[idx].get("close", 0))

        forward_windows = {"ret_t1": 1, "ret_t5": 5, "ret_t20": 20, "ret_t60": 60}
        labels = {}
        max_available = len(kline_rows) - 1
        label_ok = True

        for name, offset in forward_windows.items():
            target_idx = idx + offset
            if target_idx > max_available:
                labels[name] = None
                label_ok = False
            else:
                forward_close = float(kline_rows[target_idx].get("close", 0))
                if forward_close > 0 and close_at_trade > 0:
                    labels[name] = round((forward_close / close_at_trade - 1) * 100, 4)
                else:
                    labels[name] = None
                    label_ok = False

        # max_drawdown in T+20 window
        end_idx = min(idx + 20, len(kline_rows))
        window_prices = [float(r.get("close", 0)) for r in kline_rows[idx:end_idx]
                         if r.get("close") is not None]
        if len(window_prices) >= 2:
            peak = window_prices[0]
            max_dd = 0.0
            for p in window_prices[1:]:
                if p > peak:
                    peak = p
                dd = (p - peak) / peak
                if dd < max_dd:
                    max_dd = dd
            labels["max_drawdown"] = round(max_dd * 100, 4)
        else:
            labels["max_drawdown"] = None
            label_ok = False

        labels["relative_return"] = None  # Phase 1 暂不计算相对基准

        label_status = "AVAILABLE" if label_ok else "INSUFFICIENT_FORWARD_DATA"
        labels["label_status"] = label_status
        labels["label_visibility"] = "POST_OUTCOME_NOT_FEATURE"

        return labels, []

    # ------------------------------------------------------------------
    # 未来函数检查
    # ------------------------------------------------------------------

    def _check_future_function(
        self, kline_rows: List[dict], cutoff: str
    ) -> dict:
        """检查未来函数风险。

        检查 kline_rows 中最大的日期是否 > cutoff。
        任何特征输入数据日期 > cutoff 必须 BLOCK。
        """
        if not kline_rows:
            return {
                "passed": True,
                "max_data_date": cutoff,
                "as_of_check": "PASS",
                "details": "无可用 K 线数据，跳过未来函数检查",
            }

        max_date = max(r.get("_date_norm", "") for r in kline_rows if r.get("_date_norm"))
        max_int = int(max_date)
        cutoff_int = int(cutoff)

        if max_int > cutoff_int:
            return {
                "passed": False,
                "max_data_date": max_date,
                "as_of_check": "BLOCK",
                "details": f"kline 中存在数据日期({max_date}) > cutoff({cutoff})，未来函数风险 — BLOCK",
            }

        return {
            "passed": True,
            "max_data_date": max_date,
            "as_of_check": "PASS",
            "details": f"最大 kline 日期({max_date}) <= cutoff({cutoff})，PASS",
        }

    # ------------------------------------------------------------------
    # 辅助方法
    # ------------------------------------------------------------------

    def _compute_cutoff(self, as_of_date: str, lag_days: int) -> str:
        if lag_days <= 0:
            return as_of_date
        dt = datetime.strptime(as_of_date, "%Y%m%d")
        from datetime import timedelta
        cutoff = dt - timedelta(days=lag_days)
        return cutoff.strftime("%Y%m%d")

    def _get_baseline_features(self, stock_code: str, trade_date: str) -> dict:
        return {
            "baseline_id": "",
            "support": None,
            "pressure": None,
            "stop_loss": None,
            "valid_until": None,
        }

    def _get_risk_flags(self, stock_code: str, trade_date: str, cutoff: str) -> dict:
        return {
            "overall_risk_level": "UNKNOWN",
            "pledge": None,
            "unlock": None,
            "margin": None,
            "northbound": None,
        }

    def _check_freshness(self, quality_flags: list, used_last: bool = False) -> dict:
        if "MARKET_DATA_MISSING" in quality_flags:
            return {"overall": "MISSING", "details": {}}
        if used_last or "TRADE_DATE_ROLLBACK_TO_LAST_AVAILABLE" in quality_flags:
            return {"overall": "STALE", "details": {"reason": "最近可用交易日"}}
        return {"overall": "FRESH", "details": {}}

    def _is_reconstructed(self, trade_date: str, as_of_date: str) -> bool:
        return trade_date != as_of_date

    def _get_stock_name(self, code: str) -> str:
        name_map = {"600114": "东睦股份", "600519": "贵州茅台", "000858": "五粮液"}
        return name_map.get(code, f"STOCK_{code}")

    def _generate_snapshot_id(self, stock_code: str, trade_date: str) -> str:
        uid = uuid.uuid4().hex[:6]
        return f"FS-{trade_date}-{stock_code}-{uid}"
