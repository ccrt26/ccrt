"""
ProductStockPoolService - 产品股票池服务。

作为产品页面当前服务股票的唯一来源。
所有产品股票信息必须从此服务获取，不得硬编码到 API 或前端。
"""

from datetime import datetime, timezone
from typing import Optional


class ProductStockPoolService:
    """产品股票池服务。

    当前池成员在类内部定义。池成员变更时在此处维护。
    600114 / 东睦股份 信息仅出现在此处和由它生成的 stock_pool.json 中。
    """

    SCHEMA_VERSION = "keystock.product_stock_pool.v1"
    POOL_ID = "keystock_product_pool"
    POOL_NAME = "重点股票产品池"
    POOL_VERSION = "2026-06-16.v1"

    # 当前产品股票池成员配置
    _POOL_MEMBERS = [
        {
            "stock_code": "600114",
            "stock_name": "东睦股份",
            "status": "active",
            "join_reason": "current_product_scope",
            "joined_at": "2026-06-16",
            "primary_baseline_id": None,
            "baseline_status": "readonly_external",
            "evidence_status": "existing_product_eval_evidence",
            "data_status": "existing_product_eval_data",
            "display_order": 1,
            "source_refs": [],
        }
    ]

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------

    def get_active_members(self) -> list:
        """获取当前活跃成员列表。"""
        return [m for m in self._POOL_MEMBERS if m.get("status") == "active"]

    def get_primary_member(self) -> Optional[dict]:
        """获取主成员（第一个活跃成员）。"""
        active = self.get_active_members()
        return active[0] if active else None

    # ------------------------------------------------------------------
    # 构建 / 验证
    # ------------------------------------------------------------------

    def build_pool(self) -> dict:
        """构建完整股票池对象（输出到 stock_pool.json）。"""
        return {
            "schema_version": self.SCHEMA_VERSION,
            "pool_id": self.POOL_ID,
            "pool_name": self.POOL_NAME,
            "pool_version": self.POOL_VERSION,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "members": list(self._POOL_MEMBERS),
        }

    def validate_pool_contract(self, pool: dict) -> list:
        """验证 stock_pool.json 是否符合最低契约。返回错误列表，空列表表示通过。"""
        errors = []
        if not isinstance(pool, dict):
            errors.append("pool must be a dict")
            return errors
        if not pool.get("schema_version"):
            errors.append("schema_version is missing or empty")
        if not pool.get("pool_version"):
            errors.append("pool_version is missing or empty")
        members = pool.get("members")
        if not isinstance(members, list):
            errors.append("members must be a list")
            return errors
        if len(members) == 0:
            errors.append("members must not be empty")
            return errors
        required_keys = {"stock_code", "stock_name", "status", "display_order", "source_refs"}
        for i, m in enumerate(members):
            missing = required_keys - m.keys()
            if missing:
                errors.append(f"members[{i}] missing required fields: {missing}")
        return errors
