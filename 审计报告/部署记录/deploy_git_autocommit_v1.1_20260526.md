# 部署记录 — git_autocommit v1.1

> **部署人**：红枫 | **日期**：2026-05-26 | **闸门**：gate_3 PASS

## 部署清单

| # | 文件 | 操作 | 状态 |
|:--|:-----|:----:|:----:|
| 1 | `代码文件/tools/git_sweep.ps1` | 新增(51行) | ✅ |
| 2 | `代码文件/tools/git_autocommit.ps1` | 改1行(ValidateSet +engineering) | ✅ |
| 3 | `代码文件/每日荐股/scripts/daily_workflow.ps1` | 改5行(末尾git_sweep调用) | ✅ |
| 4 | `审计报告/架构设计/design_git_autocommit_v1.1.md` | 新增(设计文档) | ✅ |

## 前置检查

| 闸门 | 状态 | 备注 |
|:----:|:----:|:-----|
| gate_1a (腰子确认) | ✅ | finance_confirmed: true |
| gate_1b (新安+旧影) | ✅ | 联合审查 PASS |
| gate_2 (新安四层) | ✅ | DryRun验证通过，116文件正确检测 |

## 灰度策略

- **触发条件**：下次 `daily_workflow.ps1` 运行时自动激活（末尾调用 git_sweep）
- **回退触发**：若 git_sweep 导致异常提交 → 删除 git_sweep.ps1 + 移除 daily_workflow 调用行
- **监控**：`临时报告/git_autocommit.log` 中 engineering 模块日志

## 回滚方案

```powershell
# 步骤1: 删除 git_sweep.ps1
Remove-Item "代码文件/tools/git_sweep.ps1"

# 步骤2: 还原 daily_workflow.ps1 (删除 git_sweep 调用段)
# 定位并删除以下5行:
#   # Auto-commit: engineering sweep ...
#   $gitSweep = ...
#   if (Test-Path $gitSweep) { ... }

# 步骤3: 还原 git_autocommit.ps1 ValidateSet
# 将 "engineering" 从 ValidateSet 中移除
```
