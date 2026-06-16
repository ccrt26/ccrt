"""
AnalysisResetWorkflow - 分析重置工作流模块。

支持 dry-run 模式的安全分析重置。禁止默认删除历史证据。
"""

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from .inventory import PROJECT_ROOT


class AnalysisResetWorkflowService:
    """分析重置工作流服务。"""

    def __init__(self, data_root: Optional[str] = None):
        self.data_root = data_root or PROJECT_ROOT

    def create_reset_request(
        self,
        stock_code: str,
        stock_name: str,
        trade_date: str,
        reason: str = "",
        dry_run: bool = True,
    ) -> dict:
        request_id = f"RW-{trade_date}-{stock_code}-{uuid.uuid4().hex[:6]}"
        steps = [
            {"step_name": "重新运行分析", "status": "PENDING" if dry_run else "QUEUED",
             "description": "重新生成该股票今日分析", "estimated_impact": "更新分析结论"},
            {"step_name": "刷新持仓/成本/盈亏", "status": "PENDING" if dry_run else "QUEUED",
             "description": "重新读取持仓数据", "estimated_impact": "更新盈亏计算"},
            {"step_name": "重建证据链", "status": "PENDING" if dry_run else "QUEUED",
             "description": "重新生成证据索引", "estimated_impact": "更新证据展示"},
            {"step_name": "重新生成产品 API", "status": "PENDING" if dry_run else "QUEUED",
             "description": "重新打包前端数据", "estimated_impact": "更新驾驶舱"},
            {"step_name": "提交规则候选", "status": "SKIPPED" if dry_run else "PENDING",
             "description": "如需修改规则则提交候选", "estimated_impact": "规则治理"},
        ]
        return {
            "request_id": request_id,
            "stock_code": stock_code,
            "stock_name": stock_name,
            "trade_date": trade_date,
            "reason": reason or f"Phase 2/3 产品化重置测试",
            "dry_run": dry_run,
            "workflow_status": "DRY_RUN" if dry_run else "QUEUED",
            "steps": steps,
            "blocking_reasons": [],
            "warning_reasons": ["dry-run 模式：不会实际修改任何数据"] if dry_run else [],
            "created_at": datetime.now(timezone.utc).isoformat(),
            "completed_at": "",
        }

    def execute_dry_run(
        self,
        stock_code: str,
        stock_name: str,
        trade_date: str,
        reason: str = "",
    ) -> dict:
        req = self.create_reset_request(stock_code, stock_name, trade_date, reason, dry_run=True)
        completed_steps = []
        for step in req["steps"]:
            if step["status"] == "PENDING":
                completed_steps.append({**step, "status": "PASS"})
            else:
                completed_steps.append(step)
        req["steps"] = completed_steps
        req["workflow_status"] = "DRY_RUN"
        req["completed_at"] = datetime.now(timezone.utc).isoformat()
        return req
