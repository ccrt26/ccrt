# 变更影响分析 — 信鸽BOM修复
> gate: PASS | L0修复 | 2026-05-27
- 影响范围：3文件，零功能变更
- pigeon_boot_check.ps1: 去除双BOM → 修复采集阻断
- test_catchup_logic.ps1: 去除双BOM → 修复测试脚本
- pigeon_collector.ps1: 添加-DisableNameChecking → 抑制动词警告
- 风险评估：无功能回归风险，无性能影响，无接口变更
