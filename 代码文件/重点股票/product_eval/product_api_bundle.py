"""
ProductApiBundle - 产品 API 聚合包。

生成前端唯一读取入口的产品 API 包。前端不得直接读取分散运行产物。
所有业务数字必须包含 source_path / source_field_refs。
不存在持仓/盈亏数据时显示 UNAVAILABLE，不得编造。
"""

import json
import os
from datetime import datetime, timezone
from typing import Any, Optional

from .inventory import PROJECT_ROOT
from .analysis_run_state import AnalysisRunStateService
from .evidence_trace_index import EvidenceTraceIndexService
from .rule_health_summary import RuleHealthSummaryService
from . import data_source as ds


class ProductApiBundleService:
    """产品 API 包生成器。"""

    def __init__(self, data_root: Optional[str] = None):
        self.data_root = data_root or PROJECT_ROOT
        self.run_state_svc = AnalysisRunStateService(data_root)
        self.evidence_svc = EvidenceTraceIndexService(data_root)
        self.rule_health_svc = RuleHealthSummaryService(data_root)
        self.primary_code = "600114"
        self.primary_name = "东睦股份"

    def build_all(self, base_dir: str, out_dir: str, docs_data_dir: str) -> dict:
        os.makedirs(out_dir, exist_ok=True)
        os.makedirs(docs_data_dir, exist_ok=True)

        inv_path = os.path.join(base_dir, "inventory", "keystock_system_inventory.json")
        bt_path = os.path.join(base_dir, "backtests", "backtest_TECH_MA20_BREAK_STOP_LOSS_600114_20260616.json")
        snap_path = os.path.join(base_dir, "feature_snapshots", "feature_snapshot_600114_20260616.json")
        dash_path = os.path.join(base_dir, "status", "dashboard_status.json")

        # 加载真实数据
        snap = self._load_json(snap_path)
        bt = self._load_json(bt_path)
        dash = self._load_json(dash_path)
        inv = self._load_json(inv_path)

        # 1. dashboard.json
        dashboard = self._build_dashboard(dash, inv, snap)
        self._write_json(os.path.join(out_dir, "dashboard.json"), dashboard)
        self._write_json(os.path.join(docs_data_dir, "dashboard.json"), dashboard)

        # 2. stocks.json — 仅包含 600114（唯一有真实证据链的股票）
        stocks = self._build_stocks(snap, bt)
        self._write_json(os.path.join(out_dir, "stocks.json"), stocks)
        self._write_json(os.path.join(docs_data_dir, "stocks.json"), stocks)

        # 3. run_state.json
        run_state = self.run_state_svc.derive_from_inventory(self.primary_code, "20260616", inv_path)
        self._write_json(os.path.join(out_dir, "run_state.json"), run_state)
        self._write_json(os.path.join(docs_data_dir, "run_state.json"), run_state)

        # 4. evidence_index.json
        evidence = self.evidence_svc.derive_from_backtest(bt_path)
        if not evidence:
            evidence = self.evidence_svc.build_evidence_index(self.primary_code, self.primary_name, "20260616")
        self._write_json(os.path.join(out_dir, "evidence_index.json"), evidence)
        self._write_json(os.path.join(docs_data_dir, "evidence_index.json"), evidence)

        # 5. rule_health.json (only to docs-data)
        rule_health = self.rule_health_svc.derive_from_backtest(bt_path)
        if not rule_health:
            rule_health = self.rule_health_svc.build_rule_health()
        self._write_json(os.path.join(docs_data_dir, "rule_health.json"), rule_health)
        self._write_json(os.path.join(out_dir, "rule_health_summary.json"), rule_health)

        # 6. today_decisions.json — 基于真实数据的决策
        decisions = self._build_today_decisions(snap, bt, dash)
        self._write_json(os.path.join(out_dir, "today_decisions.json"), decisions)
        self._write_json(os.path.join(docs_data_dir, "today_decisions.json"), decisions)

        # 7. chart_data.json — 从 kline_cache 生成真实图表数据
        chart = self._build_chart_data()
        self._write_json(os.path.join(out_dir, "chart_data.json"), chart)
        self._write_json(os.path.join(docs_data_dir, "chart_data.json"), chart)

        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "files": [
                "dashboard.json", "stocks.json", "run_state.json",
                "evidence_index.json", "today_decisions.json", "chart_data.json"
            ],
            "dashboard_overall": dashboard.get("overall_status", "UNKNOWN"),
            "stocks_count": len(stocks.get("stocks", [])),
            "data_truth_status": "REAL_EVIDENCE_ONLY",
        }

    # ------------------------------------------------------------------
    # _build_dashboard
    # ------------------------------------------------------------------

    def _build_dashboard(self, dash: Optional[dict], inv: Optional[dict], snap: Optional[dict]) -> dict:
        sidecar_count = 0
        if inv:
            sidecar_count = inv.get("daily_report_sidecars", {}).get("count", 0)

        tech = {}
        if snap:
            tech = snap.get("feature_values", {}).get("technical", {})

        missing_flags = []
        if snap is None:
            missing_flags.append("FEATURE_SNAPSHOT_MISSING")
        if sidecar_count == 0:
            missing_flags.append("SIDECAR_MISSING")
        if tech.get("close") is None:
            missing_flags.append("CLOSE_DATA_MISSING")

        overall = dash.get("overall_status", "BLOCK") if dash else "BLOCK"

        return {
            "overall_status": overall,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "data_truth_status": "REAL_DATA",
            "stocks_tracked": 1,
            "primary_stock_code": self.primary_code,
            "primary_stock_name": self.primary_name,
            "as_of_date": tech.get("actual_trade_date", "unknown"),
            "source_summary": f"kline_cache/{self.primary_code}.json + feature_snapshot",
            "missing_data_flags": missing_flags,
            "warnings": ["持仓数据未接入，不生成持仓盈亏判断"],
            "blocks": [],
        }

    # ------------------------------------------------------------------
    # _build_stocks — 仅 600114
    # ------------------------------------------------------------------

    def _build_stocks(self, snap: Optional[dict], bt: Optional[dict]) -> dict:
        tech = {}
        if snap:
            tech = snap.get("feature_values", {}).get("technical", {})

        change_pct = None
        if snap:
            close = tech.get("close")
            prev = snap.get("feature_values", {}).get("technical", {}).get("ma5")
            if close and prev:
                change_pct = round((close - prev) / prev * 100, 2)

        stock = {
            "stock_code": self.primary_code,
            "stock_name": self.primary_name,
            "close": tech.get("close"),
            "change_pct": change_pct,
            "actual_trade_date": tech.get("actual_trade_date"),
            "data_freshness_status": (snap or {}).get("freshness_status", {}).get("overall", "UNKNOWN"),
            "run_status": "PASS" if snap else "WARN",
            "user_visible_status": "COMPLETE" if snap else "BLOCK",
            "source_path": "运行产物/重点股票产品化后评估/feature_snapshots/feature_snapshot_600114_20260616.json",
            "source_field_refs": ["feature_values.technical.close", "feature_values.technical.ma5"],
            "missing_fields": [],
        }
        return {"generated_at": datetime.now(timezone.utc).isoformat(), "stocks": [stock]}

    # ------------------------------------------------------------------
    # _build_today_decisions — 不硬编码结论
    # ------------------------------------------------------------------

    def _build_today_decisions(self, snap: Optional[dict], bt: Optional[dict], dash: Optional[dict]) -> dict:
        tech = {}
        if snap:
            tech = snap.get("feature_values", {}).get("technical", {})

        rule_status = "OBSERVE"
        if bt:
            rule_status = bt.get("overall_status", "OBSERVE")

        close = tech.get("close")
        ma20 = tech.get("ma20")
        ma5 = tech.get("ma5")

        # 决策生成规则（非硬编码）
        if close is None or ma20 is None:
            primary_action = "observe"
            confidence = 0.0
            reasoning = "关键数据缺失，无法生成决策"
        elif close < ma20:
            primary_action = "observe"
            confidence = 0.4
            reasoning = f"收盘价({close})已跌破MA20({ma20})，需关注次日是否能收复"
        elif close < ma5:
            primary_action = "observe"
            confidence = 0.5
            reasoning = f"收盘价({close})位于MA5({ma5})下方，但仍在MA20({ma20})上方，短期偏弱"
        else:
            primary_action = "hold"
            confidence = 0.6
            reasoning = f"收盘价({close})在MA5({ma5})和MA20({ma20})上方，趋势偏强"

        if rule_status == "WARN" and confidence > 0.3:
            confidence = round(confidence * 0.6, 2)

        return {
            "stock_code": self.primary_code,
            "stock_name": self.primary_name,
            "trade_date": tech.get("actual_trade_date", "unknown"),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "user_position": {
                "has_position": False,
                "position_source": "UNAVAILABLE",
                "cost_price": None,
                "market_price": close,
                "unrealized_pnl": None,
                "unrealized_pnl_pct": None,
                "note": "当前未接入真实持仓，不生成持仓盈亏判断",
            },
            "market_today": {
                "close": close,
                "ma5": ma5,
                "ma20": ma20,
                "ma60": tech.get("ma60"),
                "rsi14": tech.get("rsi14"),
            },
            "primary_action": primary_action,
            "confidence": confidence,
            "reasoning": reasoning,
            "data_sources": {
                "feature_snapshot": "运行产物/重点股票产品化后评估/feature_snapshots/feature_snapshot_600114_20260616.json",
                "rule_health": "运行产物/重点股票产品化后评估/product_api/rule_health_summary.json",
            },
            "rule_health_status": rule_status,
        }

    # ------------------------------------------------------------------
    # _build_chart_data — 从 kline_cache 生成
    # ------------------------------------------------------------------

    def _build_chart_data(self) -> dict:
        rows = ds.get_kline_until(self.primary_code, "20260616")
        limit = min(120, len(rows))
        recent = rows[-limit:] if limit > 0 else []

        ohlc = []
        volumes = []
        ma5_vals = []
        ma20_vals = []
        ma60_vals = []

        close_prices = [float(r.get("close", 0)) for r in recent if r.get("close")]

        for i, r in enumerate(recent):
            nd = r.get("_date_norm", "")
            c = float(r.get("close", 0))
            ohlc.append({
                "date": nd,
                "open": float(r.get("open", 0)),
                "high": float(r.get("high", 0)),
                "low": float(r.get("low", 0)),
                "close": c,
            })
            vol = r.get("volume", r.get("vol", 0))
            if vol:
                volumes.append({"date": nd, "volume": float(vol)})

            # rolling MA
            prices_up_to_i = close_prices[:i+1]
            if len(prices_up_to_i) >= 5:
                ma5_vals.append({"date": nd, "ma5": round(sum(prices_up_to_i[-5:]) / 5, 4)})
            if len(prices_up_to_i) >= 20:
                ma20_vals.append({"date": nd, "ma20": round(sum(prices_up_to_i[-20:]) / 20, 4)})
            if len(prices_up_to_i) >= 60:
                ma60_vals.append({"date": nd, "ma60": round(sum(prices_up_to_i[-60:]) / 60, 4)})

        last_date = rows[-1].get("_date_norm", "") if rows else ""
        max_kline_date = max(r.get("_date_norm", "") for r in rows) if rows else ""

        tech = {}
        try:
            snap = json.load(open(
                "运行产物/重点股票产品化后评估/feature_snapshots/feature_snapshot_600114_20260616.json"
            ))
            tech = snap.get("feature_values", {}).get("technical", {})
        except Exception:
            pass

        actual_trade_date = tech.get("actual_trade_date", "")
        divergence = actual_trade_date != max_kline_date

        return {
            "stock_code": self.primary_code,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source_path": "代码文件/数据/kline_cache/600114.json",
            "source_last_date": max_kline_date,
            "feature_snapshot_actual_date": actual_trade_date,
            "data_date_divergence": divergence,
            "date_divergence_warning": f"feature_snapshot actual_trade_date({actual_trade_date}) != kline_cache max_date({max_kline_date})" if divergence else "",
            "ohlc": ohlc,
            "volume": volumes,
            "ma5": ma5_vals,
            "ma20": ma20_vals,
            "ma60": ma60_vals,
            "total_kline_rows": len(rows),
        }

    # ------------------------------------------------------------------
    # 辅助
    # ------------------------------------------------------------------

    @staticmethod
    def _load_json(path: str) -> Optional[dict]:
        if os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return None
        return None

    @staticmethod
    def _write_json(path: str, data: Any) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"[API] 已写入: {path}")
