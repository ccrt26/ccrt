# 部署记录 — 信鸽BOM修复
> gate: PASS | 日期: 2026-05-27 | 类型: L0热修复

## 部署清单
| 文件 | 操作 | 验证 |
|:-----|:-----|:----|
| pigeon_boot_check.ps1 | 覆盖写入(UTF8无BOM) | xxd hex PASS |
| test_catchup_logic.ps1 | 覆盖写入(UTF8无BOM) | xxd hex PASS |
| pigeon_collector.ps1:74 | 添加-DisableNameChecking | 语法检查 PASS |

## 部署方式
- 直接文件覆盖，无需重启服务
- 下次信鸽开机自检自动生效
