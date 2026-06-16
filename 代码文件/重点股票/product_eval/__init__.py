"""
重点股票产品化后评估/回测后端 MVP —— Phase 1 后端模块包。

模块清单：
  - inventory: 资产盘点
  - prediction_ledger: 预测账本 JSONL 管理
  - feature_service: 特征快照服务
  - backtest_engine: 单规则回测引擎
  - forward_eval: 前向到期扫描
  - status_exporter: 状态/告警 JSON 输出

包级别常量
"""
from datetime import datetime

__version__ = "0.1.0"
__phase__ = "Phase 1 MVP"
__build_date__ = "2026-06-16"

# 生产目录保护 — 任何模块不得写入以下路径
PRODUCTION_PATHS = [
    "重点股票/股票报告",
    "重点股票/深度分析",
    "00_项目地基/02_权威注册表/baseline_registry.json",
    "00_项目地基/06_调度与运行/runtime_entry_registry.json",
]

# 用户可见状态
VISIBLE_COMPLETE = "COMPLETE"
VISIBLE_AUTO_REPAIRING = "AUTO_REPAIRING"
VISIBLE_BLOCK = "BLOCK"

# 内部状态
STATUS_PASS = "PASS"
STATUS_WARN = "WARN"
STATUS_ALERT = "ALERT"
STATUS_BLOCK = "BLOCK"
STATUS_OBSERVE = "OBSERVE"
STATUS_PENDING = "PENDING"
STATUS_RUNNING = "RUNNING"

# 采样不足最小样本数
MIN_SAMPLES_REQUIRED = 5

# 回测窗口标签
WINDOW_3Y = "3Y"
WINDOW_1Y = "1Y"
WINDOW_6M = "6M"


def get_build_info() -> dict:
    return {
        "version": __version__,
        "phase": __phase__,
        "build_date": __build_date__,
    }
