# 开机补跑时间闸门 — 架构设计 v1.0

pipeline_stage: complete
created: 2026-05-27
executor: 情墨

## 问题

`TieLv-DailyPipeline-Boot` 登录触发器在任何时间登录都会触发全量每日管线（动态池→数据采集→评分→报告）。
2026-05-27 08:23 登录触发了当日管线，此时尚未开盘，数据为前一日数据，报告无意义。

## 根因

`invoke_daily.ps1` 仅做幂等检查（今日是否已SUCCESS），未做时间闸门判断。

## 设计方案

### 修改点1：`invoke_daily.ps1`

在幂等检查之后、健康检测之前插入时间闸门：

```powershell
# 时间闸门：20:00之前不启动补跑（由TieLv-DailyStock 20:00定时任务处理）
$now = Get-Date
$cutoff = Get-Date -Hour 20 -Minute 0 -Second 0
if ($now -lt $cutoff) {
    $msg = "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] 当前时间早于20:00，跳过补跑（定时任务将按时执行）"
    Write-Output $msg
    exit 0
}
```

### 修改点2：`install_scheduler.ps1`

任务注册对齐实际运行的三任务架构：

| 任务名 | 触发器 | 动作 | 
|--------|--------|------|
| TieLv-DailyPipeline | 每日19:00 | invoke_daily.ps1 |
| TieLv-DailyPipeline-Boot | 登录+120s | invoke_daily.ps1（经时间闸门） |
| TieLv-DailyStock | 每日20:00 | daily_workflow.ps1 -Mode daily_latest |

install_scheduler.ps1 需额外注册 TieLv-DailyStock（目前仅注册了DailyPipeline和Evaluation）。

### 修改点3：`daily_workflow.ps1`

Phase 5 调用 `run_keystock_analysis.ps1` 时不传 `-Mode daily_latest`，确保使用标准日报模板（而非深度分析模板）。

## 影响范围

- `代码文件/每日荐股/scripts/invoke_daily.ps1` — 6行新增
- `代码文件/每日荐股/scripts/install_scheduler.ps1` — 注册TieLv-DailyStock任务
- `代码文件/每日荐股/scripts/daily_workflow.py` — Phase 5传参确保日报模板

## 需求→代码核对清单

- [ ] invoke_daily.ps1: 时间闸门 (20:00前→skip)
- [ ] install_scheduler.ps1: 三任务对齐注册
- [ ] daily_workflow.ps1: Phase 5日报模板模式
- [ ] 部署后验证：TieLv-DailyPipeline-Boot任务参数更新
