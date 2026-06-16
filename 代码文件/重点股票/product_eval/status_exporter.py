"""
StatusExporter - 状态/告警 JSON 输出。

输出 dashboard_status.json 和 alert_center.json。
用户可见状态仅三类：COMPLETE / AUTO_REPAIRING / BLOCK。
"""

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any, List, Optional

from . import VISIBLE_COMPLETE, VISIBLE_AUTO_REPAIRING, VISIBLE_BLOCK
from .inventory import PROJECT_ROOT


class StatusExporter:
    """状态导出器。"""

    def __init__(self, data_root: Optional[str] = None):
        self.data_root = data_root or PROJECT_ROOT

    # ------------------------------------------------------------------
    # 实际状态推导
    # ------------------------------------------------------------------

    def derive_status_from_artifacts(
        self, output_dir: str = "运行产物/重点股票产品化后评估"
    ) -> tuple:
        """从产出物实际读取状态，推导 dashboard 状态。

        dashboard_status.json 和 alert_center.json 使用同一份 alerts 对象。
        """
        base = os.path.join(self.data_root, output_dir)
        task_statuses = []
        alerts = []

        # 1) Inventory
        inv_path = os.path.join(base, "inventory", "keystock_system_inventory.json")
        if not os.path.exists(inv_path):
            task_statuses.append({
                "task_id": "inventory", "task_type": "inventory",
                "status": "BLOCK", "detail": "inventory 缺失",
            })
        else:
            with open(inv_path, "r") as f:
                inv = json.load(f)
            sc = inv.get("daily_report_sidecars", {}).get("count", 0)
            if sc == 0:
                task_statuses.append({
                    "task_id": "sidecar_scan", "task_type": "inventory",
                    "status": "BLOCK",
                    "detail": "sidecar 扫描为 0（正则匹配失败或无文件）",
                })
                alerts.append(self._make_alert(
                    "sidecar_scan_empty", "WARN",
                    "日报 sidecar 扫描返回 0 条；Phase 1 无法从已有日报 sidecar 提取判断",
                    user_visible=False,
                ))
            else:
                task_statuses.append({
                    "task_id": "sidecar_scan", "task_type": "inventory",
                    "status": "PASS", "detail": f"sidecar {sc} 条",
                })

        # 2) Ledger
        ledger_status_path = os.path.join(base, "ledger", "ledger_status.json")
        if not os.path.exists(ledger_status_path):
            task_statuses.append({
                "task_id": "prediction_ledger", "task_type": "prediction_ledger",
                "status": "BLOCK", "detail": "ledger_status.json 缺失",
            })
        else:
            with open(ledger_status_path, "r") as f:
                ls = json.load(f)
            lstatus = ls.get("status", "BLOCK")
            lcount = ls.get("ledger_count", 0)
            detail = ls.get("reason", f"ledger_count={lcount}")
            task_statuses.append({
                "task_id": "prediction_ledger",
                "task_type": "prediction_ledger",
                "status": lstatus if lstatus in ("PASS", "WARN", "BLOCK") else "WARN",
                "detail": detail,
            })

        # 3) Feature Snapshot
        snap_dir = os.path.join(base, "feature_snapshots")
        snap_files = [f for f in os.listdir(snap_dir) if f.endswith(".json")] if os.path.isdir(snap_dir) else []
        if not snap_files:
            task_statuses.append({
                "task_id": "feature_snapshot", "task_type": "feature_snapshot",
                "status": "BLOCK", "detail": "feature_snapshot 未生成",
            })
        else:
            market_ok = False
            for sf in snap_files:
                sfp = os.path.join(snap_dir, sf)
                with open(sfp, "r") as f:
                    sd = json.load(f)
                qf = sd.get("quality_flags", [])
                tech = sd.get("feature_values", {}).get("technical", {})
                if "MARKET_DATA_MISSING" not in qf and tech.get("close") is not None:
                    market_ok = True
                    break
            if market_ok:
                task_statuses.append({
                    "task_id": "feature_snapshot", "task_type": "feature_snapshot",
                    "status": "PASS", "detail": f"{len(snap_files)} 个快照，行情正常",
                })
            else:
                task_statuses.append({
                    "task_id": "feature_snapshot", "task_type": "feature_snapshot",
                    "status": "BLOCK", "detail": "MARKET_DATA_MISSING — 无真实行情数据",
                })
                alerts.append(self._make_alert(
                    "market_data_missing", "BLOCK",
                    "FeatureSnapshot 无真实行情数据。回测和前向评估无法判定 HIT/MISS",
                    user_visible=False,
                    decision_impact="回测和前向评估无法判定 HIT/MISS",
                ))

        # 4) Backtest
        bt_dir = os.path.join(base, "backtests")
        bt_files = [f for f in os.listdir(bt_dir) if f.endswith(".json")] if os.path.isdir(bt_dir) else []
        if not bt_files:
            task_statuses.append({
                "task_id": "backtest", "task_type": "backtest",
                "status": "WARN", "detail": "回测未执行",
            })
        else:
            for bf in bt_files:
                bfp = os.path.join(bt_dir, bf)
                with open(bfp, "r") as f:
                    bt = json.load(f)
                bt_status = bt.get("overall_status", "OBSERVE")
                task_statuses.append({
                    "task_id": f"backtest_{bf}",
                    "task_type": "backtest",
                    "status": bt_status,
                    "stock_code": bt.get("stock_code", ""),
                    "detail": f"总体状态={bt_status}",
                })

        # 5) Forward Eval
        fe_dir = os.path.join(base, "forward_eval")
        fe_files = [f for f in os.listdir(fe_dir) if f.endswith(".json")] if os.path.isdir(fe_dir) else []
        if not fe_files:
            task_statuses.append({
                "task_id": "forward_eval", "task_type": "forward_eval",
                "status": "WARN", "detail": "前向评估未执行",
            })

        # 推导总体状态
        overall = self._resolve_overall(task_statuses, alerts)
        return overall, task_statuses, alerts

    # ------------------------------------------------------------------
    # 状态推导
    # ------------------------------------------------------------------

    def _resolve_overall(self, task_statuses: List[dict], alerts: List[dict]) -> str:
        status_order = {"BLOCK": 0, "ALERT": 1, "WARN": 2, "OBSERVE": 2, "PASS": 3, "PENDING": 4, "RUNNING": 4}
        worst = "PASS"
        for ts in task_statuses:
            s = ts.get("status", "PASS")
            if status_order.get(s, 5) < status_order.get(worst, 5):
                worst = s

        if worst == "BLOCK":
            return VISIBLE_BLOCK
        if any(a.get("severity") == "BLOCK" for a in alerts):
            return VISIBLE_BLOCK
        if worst in ("ALERT",):
            return VISIBLE_AUTO_REPAIRING
        if worst == "WARN":
            return VISIBLE_BLOCK if any(
                ts.get("status") == "WARN" and "sidecar" in ts.get("task_id", "")
                and ts.get("status") == "BLOCK" for ts in task_statuses
            ) else VISIBLE_COMPLETE
        return VISIBLE_COMPLETE

    # ------------------------------------------------------------------
    # Dashboard Status
    # ------------------------------------------------------------------

    def export_dashboard_status(
        self,
        overall_status: Optional[str] = None,
        task_statuses: Optional[List[dict]] = None,
        alerts: Optional[List[dict]] = None,
        out_dir: Optional[str] = None,
        auto_derive: bool = True,
    ) -> dict:
        """输出 dashboard_status.json。默认从产出物自动推导。"""
        if auto_derive:
            d_overall, d_tasks, d_alerts = self.derive_status_from_artifacts()
            overall_status = overall_status if overall_status is not None else d_overall
            task_statuses = task_statuses if task_statuses is not None else d_tasks
            alerts = alerts if alerts is not None else d_alerts

        if overall_status is None:
            overall_status = VISIBLE_COMPLETE
        if task_statuses is None:
            task_statuses = []
        if alerts is None:
            alerts = []

        block_items = []
        repair_items = []

        for a in alerts:
            sev = a.get("severity", "")
            if sev == "BLOCK":
                block_items.append({
                    "item_id": a.get("alert_id", ""),
                    "block_reason": a.get("technical_reason", ""),
                    "required_action": "人工处理",
                })
                overall_status = VISIBLE_BLOCK
            elif sev in ("ALERT", "WARN") and not block_items:
                repair_items.append({
                    "item_id": a.get("alert_id", ""),
                    "repair_action": "自动重试",
                    "retry_count": 0,
                    "status": "QUEUED",
                })

        next_action = self._derive_next_action(overall_status, block_items)

        status = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "overall_status": overall_status,
            "task_statuses": task_statuses,
            "alerts": alerts,  # 同一份 alerts 对象
            "auto_repairing_items": repair_items,
            "blocked_items": block_items,
            "evidence_refs": [],
            "next_required_action": next_action,
        }

        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
            d_path = os.path.join(out_dir, "dashboard_status.json")
            with open(d_path, "w", encoding="utf-8") as f:
                json.dump(status, f, ensure_ascii=False, indent=2)
            print(f"[STATUS] dashboard_status 已写入: {d_path} (overall={overall_status})")

        return status

    # ------------------------------------------------------------------
    # Alert Center（顶层数组）
    # ------------------------------------------------------------------

    def export_alert_center(
        self,
        alerts: Optional[List[dict]] = None,
        out_dir: Optional[str] = None,
        auto_derive: bool = True,
    ) -> list:
        """输出 alert_center.json（顶层数组）。

        与 dashboard_status.json 使用同一份 alerts 对象。
        """
        if auto_derive:
            _overall, _tasks, d_alerts = self.derive_status_from_artifacts()
            alerts = alerts if alerts is not None else d_alerts

        if alerts is None:
            alerts = []

        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
            a_path = os.path.join(out_dir, "alert_center.json")
            with open(a_path, "w", encoding="utf-8") as f:
                json.dump(alerts, f, ensure_ascii=False, indent=2)
            print(f"[STATUS] alert_center 已写入: {a_path} ({len(alerts)} 条)")

        return alerts

    # ------------------------------------------------------------------
    # 辅助
    # ------------------------------------------------------------------

    def _make_alert(self, category: str, severity: str,
                    reason: str, user_visible: bool = False,
                    decision_impact: str = "") -> dict:
        now = datetime.now(timezone.utc).isoformat()
        return {
            "alert_id": f"ALERT-P1-{uuid.uuid4().hex[:6]}",
            "stock_code": "000000",
            "stock_name": "SYSTEM",
            "trade_date": datetime.now(timezone.utc).strftime("%Y%m%d"),
            "severity": severity,
            "category": category,
            "technical_reason": reason,
            "decision_impact": decision_impact,
            "self_healing_action": "",
            "self_healing_status": "NOT_REQUIRED",
            "user_visible": user_visible,
            "user_message": "",
            "created_at": now,
            "updated_at": now,
        }

    def _derive_next_action(self, overall: str, blocked: list) -> str:
        if overall == VISIBLE_BLOCK:
            n = len(blocked)
            return f"BLOCK 项需人工处理（{n} 项）" if n > 0 else "BLOCK 状态，需人工处理"
        if overall == VISIBLE_AUTO_REPAIRING:
            return "后台自动修复中"
        return "正常监控"
