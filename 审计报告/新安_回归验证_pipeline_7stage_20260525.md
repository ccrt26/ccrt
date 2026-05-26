# 新安 — 回归验证: pipeline_engine v1.1

> 验证人: 新安 | 日期: 2026-05-25

## 回归范围

L1变更 → 核心链路必测：Start→Validate→Advance→Complete 完整循环

## 回归检查点

| # | 检查点 | 结果 | 备注 |
|:--|:------|:----:|:-----|
| R01 | -Start 初始化 | ✅ | 7阶段数组正确 |
| R02 | -Status JSON输出 | ✅ | gate_1a/gate_1b字段存在 |
| R03 | -Validate 阶段①(情墨) | ✅ | 只检查pipeline_stage:complete |
| R04 | -Validate 阶段②(腰子) | ✅ | 检查finance_confirmed:true + 时间戳 |
| R05 | -Validate 阶段③(新安+旧影) | ✅ | 2+审查报告含gate:PASS |
| R06 | -Advance 推进 | ✅ | 7阶段边界正确(stage 7/7 → complete) |
| R07 | -Retry 重试机制 | ✅ | attempts递增+L3升级逻辑不变 |
| R08 | -Complete 归档 | ✅ | 重置为v1.1默认token |
| R09 | Schema迁移 | ✅ | v1.0→v1.1自动迁移 |
| R10 | Hook脚本兼容 | ✅ | pre-commit-check/ write_protection不依赖gate命名 |
| R11 | pipeline_token.ps1兼容 | ✅ | wrapper无阶段硬编码 |
| R12 | 30min stall检测 | ✅ | 逻辑不变 |

## Golden Master

不适用。本变更为流程引擎阶段结构变更，不涉及评分/排序/否决/相位逻辑。

## 结论

全部12项回归检查通过。无功能回归。
