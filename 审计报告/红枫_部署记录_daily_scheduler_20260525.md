# 红枫部署记录 — 每日数据管线自动化调度

> 部署人：红枫 | 2026-05-25 | 闸门3部署

---

## 一、部署内容

### 新增文件（2个）
| 文件 | 大小 | 用途 |
|:-----|:---:|:-----|
| `代码文件/每日荐股/scripts/invoke_daily.ps1` | 28行 | 幂等守卫 |
| `代码文件/每日荐股/scripts/install_scheduler.ps1` | 149行 | 一键安装器 |

### 注册的 Windows 定时任务（3个）
| 任务名 | 触发器 | 时间 | 执行脚本 |
|:-------|:-------|:-----|:---------|
| TieLv-DailyPipeline | Daily | 19:00 | invoke_daily.ps1 |
| TieLv-DailyPipeline-Boot | AtLogon | 开机+2min | invoke_daily.ps1 |
| TieLv-Evaluation | Daily | 19:00 | daily_workflow.ps1 -Mode eval |

### 部署验证
- [x] schtasks /query 确认三个任务均已注册
- [x] TieLv-DailyPipeline 状态: Ready
- [x] TieLv-DailyPipeline-Boot 状态: Ready
- [x] TieLv-Evaluation 状态: Ready（已存在，无需修改）
- [x] 手动触发 invoke_daily.ps1 启动今日管线（后台运行中）

## 二、回滚方案

若调度器出现问题：

### 快速回滚（禁用，不删除）
```powershell
schtasks /CHANGE /TN "TieLv-DailyPipeline" /DISABLE
schtasks /CHANGE /TN "TieLv-DailyPipeline-Boot" /DISABLE
```

### 完全卸载
```powershell
schtasks /DELETE /TN "TieLv-DailyPipeline" /F
schtasks /DELETE /TN "TieLv-DailyPipeline-Boot" /F
# 注意: TieLv-Evaluation 是旧任务，不要删除
```

### 回滚触发条件
- 管线连续3天未在19:00自动执行
- invoke_daily.ps1 报错导致无限循环
- 开机触发导致性能问题

## 三、监控方案

| 监控项 | 方法 | 频率 |
|:-------|:-----|:-----|
| 任务是否按时执行 | 检查 workflow_records.csv 是否有当日 SUCCESS | 每日 20:00 |
| 任务是否报错 | 检查 workflow_202605.log 是否有 ERROR | 每日 |
| 开机补跑是否正常 | 检查日志时间戳 | 重启后 |

## 四、已知限制

- S4U 模式在此系统上受限，任务通过 schtasks.exe + 管理员提权创建
- TieLv-Evaluation 任务为旧版（仅 Daily 触发器，无 AtLogon），本次未修改
- 2027 年春节前需更新 is_market_open.ps1 节假日硬编码
