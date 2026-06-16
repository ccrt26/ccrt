"""
ConclusionStatusService — 状态闸门服务。

统一确定 dashboard / today_decisions / run_state 的结论状态。
确保 DATA_STALE / DATA_DATE_DIVERGENCE / RULE_HEALTH_WARN / POSITION_UNAVAILABLE
不被包装为 FORMAL 或 COMPLETE。
"""

from datetime import datetime, timezone
from typing import Optional


# 结论分层
FORMAL = "FORMAL"           # 正式结论，数据完整新鲜
OBSERVATION = "OBSERVATION"  # 观察期结论，存在非阻断预警
SHADOW = "SHADOW"            # 影子模式，仅供预览
BLOCKED = "BLOCKED"          # 数据阻断，不可输出正式结论

# 用户可见状态
VISIBLE_COMPLETE = "COMPLETE"
VISIBLE_AUTO_REPAIRING = "AUTO_REPAIRING"
VISIBLE_BLOCK = "BLOCK"

# 数据状态
DATA_FRESH = "FRESH"
DATA_STALE = "STALE"
DATA_MISSING = "MISSING"
DATA_DIVERGED = "DIVERGED"

# 决策状态
DECISION_AVAILABLE = "AVAILABLE"
DECISION_OBSERVATION_ONLY = "OBSERVATION_ONLY"
DECISION_BLOCKED = "BLOCKED"


class ConclusionStatusService:
    """结论状态闸门服务。"""

    def __init__(self, run_mode: str = "shadow"):
        self.run_mode = run_mode  # "shadow" | "formal"

    def evaluate(
        self,
        stock_code: str,
        stock_name: str,
        trade_date: str,
        freshness_status: str = "UNKNOWN",
        data_date_divergence: bool = False,
        source_last_date: str = "",
        feature_snapshot_actual_date: str = "",
        rule_health_status: str = "UNKNOWN",
        evidence_status: str = "UNKNOWN",
        position_status: str = "UNAVAILABLE",
    ) -> dict:
        """评估并返回完整状态闸门结果。"""
        blockers = []
        warnings = []

        # ── 数据新鲜度 ──
        data_status = DATA_FRESH
        if freshness_status != "FRESH":
            data_status = DATA_STALE
            blockers.append("DATA_STALE")

        # ── 日期分歧 ──
        if data_date_divergence:
            data_status = DATA_DIVERGED
            blockers.append("DATA_DATE_DIVERGENCE")

        # ── 规则健康 ──
        if rule_health_status in ("WARN", "DEGRADED", "BLOCKED"):
            blockers.append("RULE_HEALTH_WARN")

        # ── 持仓不可用 ──
        if position_status == "UNAVAILABLE":
            blockers.append("POSITION_UNAVAILABLE")

        # ── 结论分层 ──
        if blockers:
            conclusion_status = BLOCKED
            decision_status = DECISION_BLOCKED
            user_visible_status = VISIBLE_BLOCK
        elif warnings:
            conclusion_status = OBSERVATION
            decision_status = DECISION_OBSERVATION_ONLY
            user_visible_status = VISIBLE_AUTO_REPAIRING
        elif self.run_mode == "shadow":
            conclusion_status = SHADOW
            decision_status = DECISION_OBSERVATION_ONLY
            user_visible_status = VISIBLE_AUTO_REPAIRING
        else:
            conclusion_status = FORMAL
            decision_status = DECISION_AVAILABLE
            user_visible_status = VISIBLE_COMPLETE

        return {
            "stock_code": stock_code,
            "stock_name": stock_name,
            "trade_date": trade_date,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "run_mode": self.run_mode,
            "conclusion_status": conclusion_status,
            "user_visible_status": user_visible_status,
            "data_status": data_status,
            "decision_status": decision_status,
            "decision_blockers": blockers,
            "warning_reasons": warnings,
            "blocking_reasons": blockers,
            "status_gate_source_refs": {
                "freshness_status": freshness_status,
                "data_date_divergence": data_date_divergence,
                "source_last_date": source_last_date,
                "feature_snapshot_actual_date": feature_snapshot_actual_date,
                "rule_health_status": rule_health_status,
                "evidence_status": evidence_status,
                "position_status": position_status,
            },
        }
