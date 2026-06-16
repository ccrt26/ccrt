"""
AnalysisRunState - 分析运行状态模块。

记录每只股票每日分析运行状态。用于回答：
- 这只股票今天有没有完成分析？
- 当前结论是否可用？
- 失败在哪里？
- 数据是否过期？
- 用户是否需要重跑？
"""

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from .inventory import PROJECT_ROOT


class AnalysisRunStateService:
    """分析运行状态服务。"""

    def __init__(self, data_root: Optional[str] = None):
        self.data_root = data_root or PROJECT_ROOT

    def build_run_state(
        self,
        stock_code: str,
        stock_name: str,
        trade_date: str,
        run_status: str = "PENDING",
        data_status: str = "UNKNOWN",
        decision_status: str = "UNKNOWN",
        evidence_status: str = "UNKNOWN",
        rule_health_status: str = "UNKNOWN",
        stale_flags: Optional[list] = None,
        blocking_reasons: Optional[list] = None,
        warning_reasons: Optional[list] = None,
    ) -> dict:
        run_id = f"RS-{trade_date}-{stock_code}-{uuid.uuid4().hex[:6]}"
        return {
            "stock_code": stock_code,
            "stock_name": stock_name,
            "trade_date": trade_date,
            "run_id": run_id,
            "run_status": run_status,
            "data_status": data_status,
            "decision_status": decision_status,
            "evidence_status": evidence_status,
            "rule_health_status": rule_health_status,
            "stale_flags": stale_flags or [],
            "blocking_reasons": blocking_reasons or [],
            "warning_reasons": warning_reasons or [],
            "last_success_at": "",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    def derive_from_inventory(self, stock_code: str, trade_date: str,
                                inventory_path: Optional[str] = None,
                                gate_override: Optional[dict] = None) -> dict:
        """派生运行状态。若传入 gate_override，使用状态闸门结果覆盖。"""
        if gate_override:
            return self.build_run_state(
                stock_code=stock_code,
                stock_name=gate_override.get("stock_name", ""),
                trade_date=trade_date,
                run_status=gate_override.get("user_visible_status", "BLOCK"),
                data_status=gate_override.get("data_status", "UNKNOWN"),
                decision_status=gate_override.get("decision_status", "UNKNOWN"),
                evidence_status=gate_override.get("status_gate_source_refs", {}).get(
                    "evidence_status", "UNKNOWN"),
                stale_flags=gate_override.get("decision_blockers", []),
                blocking_reasons=gate_override.get("blocking_reasons", []),
                warning_reasons=gate_override.get("warning_reasons", []),
            )
        try:
            if inventory_path and os.path.exists(inventory_path):
                with open(inventory_path, encoding="utf-8") as f:
                    inv = json.load(f)
                sc = inv.get("daily_report_sidecars", {}).get("count", 0)
                state = self.build_run_state(
                    stock_code=stock_code,
                    stock_name="",
                    trade_date=trade_date,
                    run_status="PASS" if sc > 0 else "WARN",
                    data_status="FRESH",
                    decision_status="AVAILABLE" if sc > 0 else "UNKNOWN",
                    evidence_status="COMPLETE" if sc > 0 else "PARTIAL",
                    warning_reasons=[] if sc > 0 else ["无有效 sidecar"],
                )
                return state
        except Exception:
            pass
        return self.build_run_state(
            stock_code=stock_code, stock_name="", trade_date=trade_date,
            run_status="WARN", blocking_reasons=["无法读取 inventory"],
        )
