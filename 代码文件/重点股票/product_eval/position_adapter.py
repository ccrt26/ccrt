"""
PositionAdapter — 公开持仓视图适配器。

仅输出固定的公开 UNAVAILABLE 视图。
不读取真实持仓数据，不输出真实成本/数量，不计算盈亏。
"""

from datetime import datetime, timezone


class PositionAdapter:
    """持仓适配器，输出安全的公开持仓视图。"""

    # 固定的公开持仓视图
    _PUBLIC_POSITION = {
        "has_position": False,
        "position_status": "UNAVAILABLE",
        "position_source_type": "NONE",
        "position_as_of": None,
        "cost_price": None,
        "quantity": None,
        "market_value": None,
        "market_price": None,
        "unrealized_pnl": None,
        "unrealized_pnl_pct": None,
        "display_note": "当前未接入真实持仓，不生成持仓盈亏判断",
    }

    def get_public_position(self, market_price=None) -> dict:
        """获取安全的公开持仓视图。

        参数 market_price 仅用于前端展示当前市价参考，
        不用于盈亏计算。盈亏相关字段始终为 None。
        """
        pos = dict(self._PUBLIC_POSITION)
        if market_price is not None:
            pos["market_price"] = market_price
        pos["generated_at"] = datetime.now(timezone.utc).isoformat()
        return pos

    def get_uavaialable_reason(self) -> str:
        """返回不可用的固定说明。"""
        return self._PUBLIC_POSITION["display_note"]
