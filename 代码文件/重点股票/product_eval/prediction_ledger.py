"""
PredictionLedger - 统一记录深度分析和日报中的可验证判断。

Phase 1 使用 JSONL 作为主存储格式（非 SQLite）。
幂等键: stock_code + trade_date + source_type + baseline_id +
         prediction_type + horizon + assertion_hash
"""

import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Optional


class PredictionLedger:
    """预测账本管理器。"""

    def __init__(self, ledger_dir: str):
        """初始化账本。

        Args:
            ledger_dir: JSONL 文件存放目录。
        """
        self.ledger_dir = ledger_dir
        self._ledger_path = os.path.join(ledger_dir, "prediction_ledger.jsonl")
        os.makedirs(ledger_dir, exist_ok=True)

    def _compute_assertion_hash(self, assertion: str) -> str:
        return hashlib.sha256(assertion.encode("utf-8")).hexdigest()

    def _compute_idempotency_key(self, record: dict) -> str:
        """计算幂等键。"""
        parts = [
            str(record.get("stock_code", "")),
            str(record.get("trade_date", "")),
            str(record.get("source_type", "")),
            str(record.get("baseline_id", "")),
            str(record.get("prediction_type", "")),
            str(record.get("horizon", "")),
            str(record.get("assertion_hash", "")),
        ]
        return "|".join(parts)

    def _generate_ledger_id(self) -> str:
        now = datetime.now(timezone.utc)
        date_part = now.strftime("%Y%m%d")
        uid = uuid.uuid4().hex[:8]
        return f"PL-{date_part}-{uid}"

    # ------------------------------------------------------------------
    # 读/写
    # ------------------------------------------------------------------

    def _read_all(self) -> list[dict]:
        """读取全部现有记录。"""
        records = []
        if not os.path.exists(self._ledger_path):
            return records
        with open(self._ledger_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
        return records

    def _write_all(self, records: list[dict]) -> None:
        """覆盖写入全部记录。"""
        with open(self._ledger_path, "w", encoding="utf-8") as f:
            for rec in records:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    def _append(self, record: dict) -> None:
        """追加单条记录。"""
        with open(self._ledger_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    # ------------------------------------------------------------------
    # 公共方法
    # ------------------------------------------------------------------

    def insert(self, record: dict) -> dict:
        """插入一条账本记录。幂等：重复键不新增，返回已有记录。

        Args:
            record: 至少包含 stock_code, trade_date, source_type,
                    baseline_id, prediction_type, horizon, assertion。

        Returns:
            写入/已存在的记录（含 ledger_id）。
        """
        # 补全必填元字段
        assertion = record.get("assertion", "")
        record.setdefault("assertion_hash", self._compute_assertion_hash(assertion))
        record.setdefault("ledger_id", self._generate_ledger_id())
        record.setdefault("status", "PENDING")
        record.setdefault("created_at", datetime.now(timezone.utc).isoformat())
        record.setdefault("evidence_refs", [])
        record.setdefault("verification_windows", [])

        key = self._compute_idempotency_key(record)

        # 检查幂等
        existing = self._read_all()
        for rec in existing:
            if self._compute_idempotency_key(rec) == key:
                return rec  # 幂等命中，返回已有记录

        self._append(record)
        return record

    def update_status(self, ledger_id: str, new_status: str,
                      evidence_ref: Optional[str] = None) -> Optional[dict]:
        """更新一条记录的 status。"""
        records = self._read_all()
        for rec in records:
            if rec.get("ledger_id") == ledger_id:
                rec["status"] = new_status
                rec["updated_at"] = datetime.now(timezone.utc).isoformat()
                if evidence_ref:
                    refs = rec.setdefault("evidence_refs", [])
                    if evidence_ref not in refs:
                        refs.append(evidence_ref)
                self._write_all(records)
                return rec
        return None

    def supersede(self, ledger_id: str, new_record: dict) -> dict:
        """替代旧记录。旧记录标记 superseded_by，新记录写入。"""
        old = self.update_status(ledger_id, "SUPERSEDED")
        new_record["superseded_by_ledger_id"] = ledger_id
        return self.insert(new_record)

    def find_due(self, as_of_date: str) -> list[dict]:
        """查找到期的判断（trade_date + horizon <= as_of_date，且仍为 PENDING）。"""
        due = []
        for rec in self._read_all():
            if rec.get("status") != "PENDING":
                continue
            trade_date = rec.get("trade_date", "")
            horizon = rec.get("horizon", 0)
            try:
                due_date = self._trade_date_plus(trade_date, horizon)
            except (ValueError, IndexError):
                continue
            if due_date <= int(as_of_date):
                rec["_due_date"] = str(due_date)
                due.append(rec)
        return due

    def get_by_stock(self, stock_code: str) -> list[dict]:
        """按股票代码查询所有记录。"""
        return [r for r in self._read_all() if r.get("stock_code") == stock_code]

    def get_by_id(self, ledger_id: str) -> Optional[dict]:
        """按 ledger_id 查询。"""
        for r in self._read_all():
            if r.get("ledger_id") == ledger_id:
                return r
        return None

    def count(self) -> int:
        """返回记录总数。"""
        return len(self._read_all())

    # ------------------------------------------------------------------
    # 辅助
    # ------------------------------------------------------------------

    @staticmethod
    def _trade_date_plus(trade_date: str, days: int) -> int:
        """YYYYMMDD + days → YYYYMMDD（简单日加法，跳过日期有效性校验）。"""
        from datetime import datetime, timedelta
        dt = datetime.strptime(trade_date, "%Y%m%d")
        result = dt + timedelta(days=days)
        return int(result.strftime("%Y%m%d"))
