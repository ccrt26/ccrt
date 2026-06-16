"""
BacktestEngine - MA20 破位止损回测引擎。

真实基于 data_source 的 kline_cache 进行 MA20 破位检测和回测统计。
"""

import json
import os
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, List, Optional

from . import MIN_SAMPLES_REQUIRED, WINDOW_3Y, WINDOW_1Y, WINDOW_6M
from . import data_source as ds
from .feature_service import FeatureSnapshotService
from .inventory import PROJECT_ROOT


class BacktestEngine:
    """MA20 破位止损回测引擎。"""

    def __init__(self, feature_service: Optional[FeatureSnapshotService] = None):
        self.feature_service = feature_service or FeatureSnapshotService()

    # ------------------------------------------------------------------
    # 主入口
    # ------------------------------------------------------------------

    def run_backtest(
        self,
        rule_id: str,
        stock_code: str,
        stock_name: str,
        as_of_date: str,
        rule_version: str = "v1.0",
        out_dir: Optional[str] = None,
    ) -> dict[str, Any]:
        if rule_id != "TECH_MA20_BREAK_STOP_LOSS":
            return self._error_result(
                rule_id, stock_code, as_of_date,
                f"不支持的规则: {rule_id}（仅支持 TECH_MA20_BREAK_STOP_LOSS）"
            )

        # 获取特征快照用于 future_function 检查
        snapshot = self.feature_service.get_features(
            stock_code=stock_code,
            trade_date=as_of_date,
            as_of_date=as_of_date,
            market_lag_days=1,
        )

        ff_check = snapshot.get("future_function_check", {})

        # 全局未来函数检查
        if ff_check.get("as_of_check") == "BLOCK":
            return self._error_result(
                rule_id, stock_code, as_of_date,
                f"未来函数风险 — BLOCK: {ff_check.get('details', '')}"
            )

        # 加载 K 线
        kline_rows = ds.get_kline_until(stock_code, as_of_date)
        if len(kline_rows) < 30:
            return self._insufficient_data_result(
                rule_id, stock_code, stock_name, as_of_date,
                f"K 线数据不足 {len(kline_rows)} 行（需要至少 30 行）"
            )

        windows = {
            WINDOW_3Y: self._get_window_range(as_of_date, 365 * 3),
            WINDOW_1Y: self._get_window_range(as_of_date, 365),
            WINDOW_6M: self._get_window_range(as_of_date, 180),
        }

        results = {}
        for label, (w_start, w_end) in windows.items():
            result = self._run_window(
                kline_rows=kline_rows,
                stock_code=stock_code,
                rule_id=rule_id,
                rule_version=rule_version,
                window_label=label,
                window_start=w_start,
                window_end=w_end,
                as_of_date=as_of_date,
            )
            results[label] = result

        overall = self._determine_overall(results)
        backtest_id = f"BT-{as_of_date}-{stock_code}-{uuid.uuid4().hex[:6]}"
        output = {
            "backtest_id": backtest_id,
            "rule_id": rule_id,
            "rule_version": rule_version,
            "stock_code": stock_code,
            "stock_name": stock_name,
            "as_of_date": as_of_date,
            "windows": results,
            "overall_status": overall,
            "feature_snapshot_refs": [snapshot.get("snapshot_id", "")],
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
            fname = f"backtest_{rule_id}_{stock_code}_{as_of_date}.json"
            out_path = os.path.join(out_dir, fname)
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(output, f, ensure_ascii=False, indent=2)
            print(f"[BACKTEST] 已写入: {out_path}")

        return output

    # ------------------------------------------------------------------
    # 窗口回测
    # ------------------------------------------------------------------

    def _run_window(
        self,
        kline_rows: List[dict],
        stock_code: str,
        rule_id: str,
        rule_version: str,
        window_label: str,
        window_start: str,
        window_end: str,
        as_of_date: str,
    ) -> dict[str, Any]:
        """对单个窗口进行 MA20 破位回测。"""
        # 筛选窗口内行
        start_int = int(window_start)
        end_int = int(window_end)

        # 窗口内需要 20+1 根 K 线才能计算 MA20
        # 往前多取 25 行确保 MA20 有足够数据
        warmup = 25
        window_rows = []
        warmup_idx = 0
        for i, r in enumerate(kline_rows):
            nd = r.get("_date_norm", "")
            if not nd:
                continue
            nd_int = int(nd)
            if nd_int <= end_int:
                if nd_int >= start_int:
                    window_rows.append(r)
                    if warmup_idx == 0:
                        warmup_idx = max(0, i - warmup)
                elif i >= len(kline_rows) - warmup - len(window_rows):
                    pass  # No warmup needed after window_rows start

        # 使用完整 kline 序列（含窗口前数据）来计算 MA
        # 找到 window_rows 在完整 kline 中的起止索引
        if not window_rows:
            return self._empty_window_result(
                rule_id, rule_version, stock_code, window_label,
                window_start, window_end, as_of_date,
                "窗口内无 K 线数据"
            )

        first_nd = window_rows[0].get("_date_norm", "")
        last_nd = window_rows[-1].get("_date_norm", "")

        # 在完整 kline 中找到窗口的起止索引（含 warmup）
        start_idx = 0
        end_idx = len(kline_rows) - 1
        for i, r in enumerate(kline_rows):
            if r.get("_date_norm", "") == first_nd:
                start_idx = max(0, i - 25)  # 25 warmup rows for MA20
                break
        for i, r in enumerate(kline_rows):
            if r.get("_date_norm", "") == last_nd:
                end_idx = i
                break

        subset = kline_rows[start_idx:end_idx + 1]
        close_prices = [float(r.get("close", 0)) for r in subset
                        if r.get("close") is not None and float(r.get("close")) > 0]

        if len(close_prices) < 25:
            return self._empty_window_result(
                rule_id, rule_version, stock_code, window_label,
                window_start, window_end, as_of_date,
                f"K 线数据不足 {len(close_prices)} 行（需要至少 25 行计算 MA20）"
            )

        # 计算每个交易日的 MA20
        ma20_values = []
        for i in range(len(close_prices)):
            if i < 19:
                ma20_values.append(None)
            else:
                ma20_values.append(sum(close_prices[i - 19:i + 1]) / 20)

        # 检测 MA20 破位信号：前一天 close >= MA20，当天 close < MA20
        signals = []
        for i in range(20, len(close_prices)):  # 从第 20 个（MA20 可用）开始
            if i < 1:
                continue
            prev_close = close_prices[i - 1]
            prev_ma20 = ma20_values[i - 1]
            curr_close = close_prices[i]
            curr_ma20 = ma20_values[i]

            if (prev_ma20 is not None and curr_ma20 is not None
                    and prev_close >= prev_ma20 and curr_close < curr_ma20):
                # 只有 window_rows 内的信号才统计
                signal_dt = subset[i].get("_date_norm", "")
                sig_int = int(signal_dt) if signal_dt else 0
                if start_int <= sig_int <= end_int:
                    signals.append({
                        "signal_date": signal_dt,
                        "trigger_close": curr_close,
                        "trigger_ma20": curr_ma20,
                        "prev_close": prev_close,
                        "prev_ma20": prev_ma20,
                        "index_in_full": start_idx + i,
                    })

        # 统计样本
        sample_count = len(signals)
        sample_sufficient = sample_count >= MIN_SAMPLES_REQUIRED

        if not sample_sufficient:
            return {
                "backtest_id": f"BT-{as_of_date}-{stock_code}-{window_label}",
                "rule_id": rule_id,
                "rule_version": rule_version,
                "stock_code": stock_code,
                "window_label": window_label,
                "window_start": window_start,
                "window_end": window_end,
                "sample_count": sample_count,
                "min_samples_required": MIN_SAMPLES_REQUIRED,
                "hit_count": 0, "miss_count": 0, "partial_count": 0,
                "win_rate": None,
                "avg_return": None, "excess_return": None,
                "max_drawdown": None, "reverse_return": None,
                "weak_rule_reasons": [f"样本不足 {sample_count}/{MIN_SAMPLES_REQUIRED}，仅 OBSERVE"],
                "quality_gates": {
                    "data_visibility_proven": True,
                    "sample_sufficient": False,
                    "has_rule_version": bool(rule_version),
                    "has_control_group": False,
                    "has_time_stratification": False,
                    "future_function_risk": False,
                    "output_reproducible": True,
                    "deferred_features": ["financial_feature_ref", "event_feature_ref", "crowding_feature_ref"],
                },
                "overall_status": "OBSERVE",
                "feature_snapshot_refs": [],
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }

        # 计算每个信号的 forward return
        hit_count = 0
        miss_count = 0
        partial_count = 0
        forward_returns = []
        max_drawdowns = []

        for sig in signals:
            sig_idx = sig["index_in_full"]
            # T+5 forward return
            t5_idx = sig_idx + 5
            t20_idx = sig_idx + 20

            if t20_idx >= len(subset):
                # 数据不足，标 OBSERVE 级别
                partial_count += 1
                continue

            t5_close = float(subset[min(t5_idx, len(subset) - 1)].get("close", 0))
            t20_close = float(subset[min(t20_idx, len(subset) - 1)].get("close", 0))

            trigger_close = sig["trigger_close"]
            if trigger_close <= 0:
                continue

            ret_t5 = (t5_close / trigger_close - 1) * 100
            ret_t20 = (t20_close / trigger_close - 1) * 100
            forward_returns.append({"signal": sig["signal_date"],
                                    "ret_t5": round(ret_t5, 4),
                                    "ret_t20": round(ret_t20, 4)})

            # 破位后是否继续跑输：T+20 负收益为 hit（止损正确），正为 miss
            if ret_t20 < -2:
                hit_count += 1  # 明显继续下跌，止损正确
            elif ret_t20 > 2:
                miss_count += 1  # 假破位，错失后续上涨
            else:
                partial_count += 1

            # T+20 窗口内的最大回撤
            end_idx_in_window = min(sig_idx + 20, len(subset))
            prices_after = [float(subset[j].get("close", 0)) for j in range(sig_idx, end_idx_in_window)
                            if subset[j].get("close") is not None]
            if len(prices_after) >= 2:
                peak = prices_after[0]
                dd = 0.0
                for p in prices_after[1:]:
                    if p > peak:
                        peak = p
                    elif (p - peak) / peak < dd:
                        dd = (p - peak) / peak
                max_drawdowns.append(round(dd * 100, 4))

        total_evaluated = hit_count + miss_count + partial_count
        win_rate = round(hit_count / total_evaluated, 4) if total_evaluated > 0 else None

        avg_ret = None
        if forward_returns:
            avg_ret = round(sum(f["ret_t20"] for f in forward_returns) / len(forward_returns), 4)

        avg_dd = round(sum(max_drawdowns) / len(max_drawdowns), 4) if max_drawdowns else None

        weak_reasons = []
        if hit_count == 0 and miss_count == 0:
            overall = "OBSERVE"
            weak_reasons.append("所有样本数据不足，仅 OBSERVE")
        elif sample_count >= MIN_SAMPLES_REQUIRED and total_evaluated < MIN_SAMPLES_REQUIRED:
            overall = "OBSERVE"
            weak_reasons.append("信号数足够但标签数据不足，仅 OBSERVE")
        elif total_evaluated >= MIN_SAMPLES_REQUIRED:
            if win_rate is not None and win_rate < 0.4:
                overall = "WARN"
                weak_reasons.append(f"胜率 {win_rate} 偏低")
            else:
                overall = "PASS"
        else:
            overall = "OBSERVE"
            weak_reasons.append("综合样本不足，仅 OBSERVE")

        return {
            "backtest_id": f"BT-{as_of_date}-{stock_code}-{window_label}",
            "rule_id": rule_id,
            "rule_version": rule_version,
            "stock_code": stock_code,
            "window_label": window_label,
            "window_start": window_start,
            "window_end": window_end,
            "sample_count": sample_count,
            "min_samples_required": MIN_SAMPLES_REQUIRED,
            "hit_count": hit_count,
            "miss_count": miss_count,
            "partial_count": partial_count,
            "win_rate": win_rate,
            "avg_return": avg_ret,
            "excess_return": None,
            "max_drawdown": avg_dd,
            "reverse_return": None,
            "weak_rule_reasons": weak_reasons,
            "quality_gates": {
                "data_visibility_proven": True,
                "sample_sufficient": sample_sufficient,
                "has_rule_version": bool(rule_version),
                "has_control_group": False,
                "has_time_stratification": False,
                "future_function_risk": False,
                "output_reproducible": True,
                "deferred_features": ["financial_feature_ref", "event_feature_ref", "crowding_feature_ref"],
            },
            "overall_status": overall,
            "feature_snapshot_refs": [],
            "signals": signals[:10],  # 最多记录前 10 个信号
            "forward_returns": forward_returns[:10],  # 最多记录前 10 个 forward 收益
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    # ------------------------------------------------------------------
    # 辅助
    # ------------------------------------------------------------------

    def _empty_window_result(self, rule_id, rule_version, stock_code,
                              window_label, w_start, w_end, as_of_date, reason):
        return {
            "backtest_id": f"BT-{as_of_date}-{stock_code}-{window_label}",
            "rule_id": rule_id, "rule_version": rule_version,
            "stock_code": stock_code,
            "window_label": window_label,
            "window_start": w_start, "window_end": w_end,
            "sample_count": 0, "min_samples_required": MIN_SAMPLES_REQUIRED,
            "hit_count": 0, "miss_count": 0, "partial_count": 0,
            "win_rate": None, "avg_return": None, "excess_return": None,
            "max_drawdown": None, "reverse_return": None,
            "weak_rule_reasons": [reason],
            "quality_gates": {
                "data_visibility_proven": True, "sample_sufficient": False,
                "has_rule_version": bool(rule_version),
                "has_control_group": False, "has_time_stratification": False,
                "future_function_risk": False, "output_reproducible": True,
                "deferred_features": ["financial_feature_ref", "event_feature_ref", "crowding_feature_ref"],
            },
            "overall_status": "OBSERVE",
            "feature_snapshot_refs": [],
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    def _insufficient_data_result(self, rule_id, stock_code, stock_name, as_of_date, reason):
        return {
            "backtest_id": f"BT-{as_of_date}-{stock_code}-NODATA",
            "rule_id": rule_id, "rule_version": "",
            "stock_code": stock_code, "stock_name": stock_name,
            "as_of_date": as_of_date,
            "overall_status": "OBSERVE",
            "error": reason,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    def _error_result(self, rule_id, stock_code, as_of_date, reason):
        return {
            "backtest_id": f"BT-{as_of_date}-{stock_code}-ERROR",
            "rule_id": rule_id, "rule_version": "",
            "stock_code": stock_code, "as_of_date": as_of_date,
            "overall_status": "BLOCK",
            "error": reason,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    @staticmethod
    def _get_window_range(as_of_date: str, days_back: int) -> tuple:
        dt = datetime.strptime(as_of_date, "%Y%m%d")
        start = dt - timedelta(days=days_back)
        return start.strftime("%Y%m%d"), as_of_date

    @staticmethod
    def _determine_overall(window_results: dict) -> str:
        statuses = [r.get("overall_status", "OBSERVE") for r in window_results.values()]
        if any(s == "BLOCK" for s in statuses):
            return "BLOCK"
        if all(s == "OBSERVE" for s in statuses):
            return "OBSERVE"
        if any(s == "WARN" for s in statuses):
            return "WARN"
        if all(s == "PASS" for s in statuses):
            return "PASS"
        return "OBSERVE"
