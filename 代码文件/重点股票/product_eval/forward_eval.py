"""
ForwardEval - 前向到期扫描。

自动发现到期判断，基于特征服务评估结果，更新账本状态。
不删除历史账本（只能 supersede），不生成投资结论。

Phase 1 占位 assertion 判定为 OBSERVE（attribution=prediction_assertion_placeholder）。
"""

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from .prediction_ledger import PredictionLedger
from .feature_service import FeatureSnapshotService
from .inventory import PROJECT_ROOT


# 占位 assertion 前缀
_PLACEHOLDER_PREFIX = "Phase 1 占位记录"


class ForwardEval:
    """前向评估扫描器。"""

    def __init__(
        self,
        ledger: PredictionLedger,
        feature_service: Optional[FeatureSnapshotService] = None,
    ):
        self.ledger = ledger
        self.feature_service = feature_service or FeatureSnapshotService()

    # ------------------------------------------------------------------
    # 主入口
    # ------------------------------------------------------------------

    def scan_due_predictions(
        self,
        as_of_date: str,
        out_dir: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """扫描到期判断并评估。"""
        due = self.ledger.find_due(as_of_date)
        if not due:
            print(f"[FORWARD_EVAL] {as_of_date}: 无到期判断")
            return []

        results = []
        for record in due:
            eval_result = self._evaluate_outcome(record, as_of_date)
            # 传递 fixture 标记
            if record.get("fixture_only"):
                eval_result["fixture_only"] = True
                eval_result["source_fixture_ref"] = record.get("ledger_id", "")
            results.append(eval_result)

            self.ledger.update_status(
                record["ledger_id"],
                eval_result["outcome"],
                evidence_ref=eval_result.get("eval_id", ""),
            )

        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
            out_path = os.path.join(out_dir, f"forward_eval_{as_of_date}.json")
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
            print(f"[FORWARD_EVAL] 已写入: {out_path} ({len(results)} 条)")

        return results

    # ------------------------------------------------------------------
    # 占位检测
    # ------------------------------------------------------------------

    @staticmethod
    def _is_placeholder_assertion(record: dict) -> bool:
        """检查 assertion 是否为 Phase 1 占位记录。"""
        assertion = record.get("assertion", "")
        return assertion.startswith(_PLACEHOLDER_PREFIX)

    # ------------------------------------------------------------------
    # 单条评估
    # ------------------------------------------------------------------

    def _evaluate_outcome(
        self, record: dict, eval_date: str
    ) -> dict[str, Any]:
        """评估单条判断的结果。"""
        stock_code = record.get("stock_code", "")
        trade_date = record.get("trade_date", "")

        # 获取特征快照
        snapshot = self.feature_service.get_features(
            stock_code=stock_code,
            trade_date=eval_date,
            as_of_date=eval_date,
            market_lag_days=0,
        )

        ff_check = snapshot.get("future_function_check", {})
        label_values = snapshot.get("label_values", {})
        label_status = label_values.get("label_status", "NOT_REQUESTED")

        eval_id = f"EV-{eval_date}-{record.get('ledger_id', 'UNKNOWN')[-12:]}"

        # 1) 未来函数 BLOCK 优先
        if ff_check.get("as_of_check") == "BLOCK":
            return {
                "eval_id": eval_id,
                "ledger_id": record.get("ledger_id", ""),
                "stock_code": stock_code,
                "stock_name": record.get("stock_name", ""),
                "trade_date": trade_date,
                "eval_date": eval_date,
                "prediction_type": record.get("prediction_type", "directional"),
                "assertion": record.get("assertion", ""),
                "horizon": record.get("horizon", 0),
                "outcome": "BLOCK",
                "outcome_detail": f"未来函数风险 — 无法评估: {ff_check.get('details', '')}",
                "attribution": {
                    "primary": "future_function_risk",
                    "secondary": [],
                    "detail": ff_check.get("details", ""),
                },
                "feature_snapshot_id": snapshot.get("snapshot_id", ""),
                "actual_metrics": {
                    "actual_return": None,
                    "max_drawdown": None,
                    "relative_return": None,
                },
                "data_gap_reason": "",
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }

        # 2) 占位 assertion → OBSERVE
        if self._is_placeholder_assertion(record):
            return self._evaluate_placeholder_assertion(record, eval_date, snapshot)

        # 3) forward label 不足
        if label_status == "INSUFFICIENT_FORWARD_DATA":
            return {
                "eval_id": eval_id,
                "ledger_id": record.get("ledger_id", ""),
                "stock_code": stock_code,
                "stock_name": record.get("stock_name", ""),
                "trade_date": trade_date,
                "eval_date": eval_date,
                "prediction_type": record.get("prediction_type", "directional"),
                "assertion": record.get("assertion", ""),
                "horizon": record.get("horizon", 0),
                "outcome": "INSUFFICIENT_DATA",
                "outcome_detail": "T+20 或更远期行情数据不足，无法完整判定 HIT/MISS",
                "attribution": {
                    "primary": "sample_insufficient",
                    "secondary": [],
                    "detail": f"label_status={label_status}",
                },
                "feature_snapshot_id": snapshot.get("snapshot_id", ""),
                "actual_metrics": {
                    "actual_return": label_values.get("ret_t5"),
                    "max_drawdown": label_values.get("max_drawdown"),
                    "relative_return": label_values.get("relative_return"),
                },
                "data_gap_reason": "",
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }

        # 4) 可正常评估（Phase 2+: 填入真实判定逻辑）
        return {
            "eval_id": eval_id,
            "ledger_id": record.get("ledger_id", ""),
            "stock_code": stock_code,
            "stock_name": record.get("stock_name", ""),
            "trade_date": trade_date,
            "eval_date": eval_date,
            "prediction_type": record.get("prediction_type", "directional"),
            "assertion": record.get("assertion", ""),
            "horizon": record.get("horizon", 0),
            "outcome": "OBSERVE",
            "outcome_detail": "Phase 1 占位通路 — 完整判定逻辑待 Phase 2 实现",
            "attribution": {
                "primary": "prediction_assertion_placeholder",
                "secondary": [],
                "detail": "完整判定逻辑待实现",
            },
            "feature_snapshot_id": snapshot.get("snapshot_id", ""),
            "actual_metrics": {
                "actual_return": label_values.get("ret_t5"),
                "max_drawdown": label_values.get("max_drawdown"),
                "relative_return": label_values.get("relative_return"),
            },
            "data_gap_reason": "",
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    # ------------------------------------------------------------------
    # 占位 assertion 专用评估
    # ------------------------------------------------------------------

    def _evaluate_placeholder_assertion(
        self, record: dict, eval_date: str, snapshot: dict
    ) -> dict[str, Any]:
        """对 Phase 1 占位 assertion 的评估。

        占位 assertion 缺少可判定方向/阈值/目标，输出 OBSERVE。
        """
        stock_code = record.get("stock_code", "")
        label_values = snapshot.get("label_values", {})

        eval_id = f"EV-{eval_date}-{record.get('ledger_id', 'UNKNOWN')[-12:]}"

        return {
            "eval_id": eval_id,
            "ledger_id": record.get("ledger_id", ""),
            "stock_code": stock_code,
            "stock_name": record.get("stock_name", ""),
            "trade_date": record.get("trade_date", ""),
            "eval_date": eval_date,
            "prediction_type": record.get("prediction_type", "directional"),
            "assertion": record.get("assertion", ""),
            "horizon": record.get("horizon", 0),
            "outcome": "OBSERVE",
            "outcome_detail": (
                "Phase 1 账本记录为占位 assertion，缺少可判定方向/阈值/目标，"
                "暂不判 HIT/MISS"
            ),
            "attribution": {
                "primary": "prediction_assertion_placeholder",
                "secondary": [],
                "detail": "占位 assertion 缺少可判定方向/阈值/目标",
            },
            "feature_snapshot_id": snapshot.get("snapshot_id", ""),
            "actual_metrics": {
                "actual_return": label_values.get("ret_t5"),
                "max_drawdown": label_values.get("max_drawdown"),
                "relative_return": label_values.get("relative_return"),
            },
            "data_gap_reason": "",
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
