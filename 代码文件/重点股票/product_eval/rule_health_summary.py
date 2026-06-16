"""
RuleHealthSummary - 规则健康摘要模块。

为每条规则构建健康状态和明细矩阵。
"""

import json
import os
from datetime import datetime, timezone
from typing import Any, Optional

from .inventory import PROJECT_ROOT


class RuleHealthSummaryService:
    """规则健康摘要服务。"""

    def __init__(self, data_root: Optional[str] = None):
        self.data_root = data_root or PROJECT_ROOT

    def build_rule_health(
        self,
        rule_id: str = "TECH_MA20_BREAK_STOP_LOSS",
        rule_name: str = "MA20 破位止损",
        rule_status: str = "WARN",
        sample_count: int = 0,
        hit_count: int = 0,
        miss_count: int = 0,
        observe_count: int = 0,
        decay_score: Optional[float] = None,
        future_leakage_risk: bool = False,
        affected_stocks: Optional[list] = None,
        recent_cells: Optional[list] = None,
    ) -> dict:
        return {
            "rule_id": rule_id,
            "rule_name": rule_name,
            "rule_status": rule_status,
            "sample_count": sample_count,
            "hit_count": hit_count,
            "miss_count": miss_count,
            "observe_count": observe_count,
            "decay_score": decay_score,
            "future_leakage_risk": future_leakage_risk,
            "affected_stocks": affected_stocks or [],
            "recent_cells": recent_cells or [],
            "explanation": self._explain_status(rule_status, sample_count, hit_count, miss_count),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    def derive_from_backtest(self, backtest_path: str) -> Optional[dict]:
        if not os.path.exists(backtest_path):
            return None
        try:
            with open(backtest_path, encoding="utf-8") as f:
                bt = json.load(f)
            windows = bt.get("windows", {})
            total_samples = sum(w.get("sample_count", 0) for w in windows.values())
            total_hits = sum(w.get("hit_count", 0) for w in windows.values())
            total_misses = sum(w.get("miss_count", 0) for w in windows.values())
            cells = []
            for label, w in windows.items():
                cells.append({
                    "sample_id": f"{label}-{bt.get('as_of_date', '')}",
                    "trade_date": bt.get("as_of_date", ""),
                    "stock_code": bt.get("stock_code", ""),
                    "state": "HIT" if w.get("hit_count", 0) > w.get("miss_count", 0) else "MISS" if w.get("miss_count", 0) > 0 else "OBS",
                    "reason": w.get("weak_rule_reasons", [None])[0] or "",
                    "evidence_ref": backtest_path,
                })
            return self.build_rule_health(
                sample_count=total_samples,
                hit_count=total_hits,
                miss_count=total_misses,
                observe_count=total_samples - total_hits - total_misses,
                affected_stocks=[bt.get("stock_code", "")],
                recent_cells=cells,
            )
        except Exception:
            return None

    @staticmethod
    def _explain_status(status: str, samples: int, hits: int, misses: int) -> str:
        if samples < 5:
            return "样本不足，仅作观察参考，不作为正式规则评估依据。"
        if status == "HEALTHY":
            return "规则运行正常，历史胜率在可接受范围内。"
        if status == "WARN":
            return f"规则存在衰减迹象（H/M={hits}/{misses}），建议关注但暂不停用。"
        if status == "DEGRADED":
            return "规则表现持续恶化，建议提交规则候选进行专项回测。"
        return f"状态: {status}, 样本: {samples}"
