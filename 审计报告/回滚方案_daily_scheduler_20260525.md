# 回滚方案 — 每日数据管线自动化调度

> 红枫 | 2026-05-25

## 快速禁用（停止自动化）
```powershell
schtasks /CHANGE /TN "TieLv-DailyPipeline" /DISABLE
schtasks /CHANGE /TN "TieLv-DailyPipeline-Boot" /DISABLE
```

## 完全移除
```powershell
schtasks /DELETE /TN "TieLv-DailyPipeline" /F
schtasks /DELETE /TN "TieLv-DailyPipeline-Boot" /F
Remove-Item "代码文件/每日荐股/scripts/invoke_daily.ps1"
Remove-Item "代码文件/每日荐股/scripts/install_scheduler.ps1"
```

## 回滚不影响
- daily_workflow.ps1（未修改）
- TieLv-Evaluation（旧任务，独立运行）
- 所有数据、评分、报告、交易逻辑
