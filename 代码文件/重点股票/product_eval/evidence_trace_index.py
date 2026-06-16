"""
EvidenceTraceIndex - 证据链索引模块。

为每个决策/结论构建证据索引，支持 UI 展示证据链。
"""

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from .inventory import PROJECT_ROOT


class EvidenceTraceIndexService:
    """证据链索引服务。"""

    def __init__(self, data_root: Optional[str] = None):
        self.data_root = data_root or PROJECT_ROOT

    def build_evidence_index(
        self,
        stock_code: str,
        stock_name: str,
        trade_date: str,
        items: Optional[list] = None,
    ) -> dict:
        decision_id = f"DI-{trade_date}-{stock_code}-{uuid.uuid4().hex[:6]}"
        return {
            "decision_id": decision_id,
            "stock_code": stock_code,
            "stock_name": stock_name,
            "trade_date": trade_date,
            "evidence_items": items or self._default_evidence(stock_code),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

    def _default_evidence(self, stock_code: str) -> list:
        return [
            {
                "evidence_id": f"ev-{uuid.uuid4().hex[:6]}",
                "source_type": "market_data",
                "source_path": f"代码文件/数据/kline_cache/{stock_code}.json",
                "summary": "K 线行情数据",
                "chart_hint": "kline",
                "freshness_status": "FRESH",
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
            {
                "evidence_id": f"ev-{uuid.uuid4().hex[:6]}",
                "source_type": "technical",
                "source_path": f"运行产物/重点股票产品化后评估/feature_snapshots/",
                "summary": "MA20/RSI/MACD 技术特征",
                "chart_hint": "ma",
                "freshness_status": "FRESH",
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        ]

    def derive_from_backtest(self, backtest_path: str) -> Optional[dict]:
        if not os.path.exists(backtest_path):
            return None
        try:
            with open(backtest_path, encoding="utf-8") as f:
                bt = json.load(f)
            return self.build_evidence_index(
                stock_code=bt.get("stock_code", ""),
                stock_name=bt.get("stock_name", ""),
                trade_date=bt.get("as_of_date", ""),
                items=[{
                    "evidence_id": f"ev-{uuid.uuid4().hex[:6]}",
                    "source_type": "backtest",
                    "source_path": backtest_path,
                    "summary": f"MA20 破位回测: {bt.get('overall_status', '')}",
                    "chart_hint": "matrix",
                    "freshness_status": "FRESH",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }],
            )
        except Exception:
            return None
