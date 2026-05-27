# 回滚方案 — 信鸽BOM修复
> gate: PASS | 日期: 2026-05-27

## 回滚触发条件
- 信鸽开机自检出现新的编码错误
- pigeon_collector.ps1 Import-Module因-DisableNameChecking参数报错（PS v2.0以下不支持）

## 回滚操作
1. pigeon_boot_check.ps1 → `git checkout HEAD~1 -- "代码文件/信鸽信息采集/pigeon_boot_check.ps1"`
2. test_catchup_logic.ps1 → `git checkout HEAD~1 -- "代码文件/每日荐股/scripts/test_catchup_logic.ps1"`
3. pigeon_collector.ps1 → `git checkout HEAD~1 -- "代码文件/信鸽信息采集/pigeon_collector.ps1"`

## 回滚影响
- 回退后BOM错误重新出现（采集阻断）
- 建议修复而非回滚
