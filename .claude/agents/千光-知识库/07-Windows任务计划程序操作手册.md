# Windows任务计划程序操作手册 — 千光构建工程师

> 版本 v1.0 | 生效日期 2026-05-24
> 用途：Windows Task Scheduler的具体操作指南——创建、管理、调试定时任务
> 平台：Windows 11 / Windows Server

---

## 一、基本概念

| 概念 | 说明 |
|:-----|:-----|
| 任务计划程序 | Windows内置的定时任务调度器(Task Scheduler) |
| 任务(Job) | 一个定时执行的单元 |
| 触发器(Trigger) | 任务的执行时间规则(每日/每周/事件触发) |
| 操作(Action) | 任务执行的具体命令(运行脚本/程序) |
| 条件(Condition) | 任务执行的前置条件(空闲/电源/网络) |
| 设置(Settings) | 任务的行为选项(失败重试/超时/并行) |

---

## 二、使用PowerShell管理

### 2.1 创建任务

```powershell
$Action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-File `"C:\path\to\script.ps1`" -NoProfile -NonInteractive"
$Trigger = New-ScheduledTaskTrigger -Daily -At "09:30"
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 5)
$Principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest

Register-ScheduledTask -TaskName "TL-每日选股池更新" -Action $Action -Trigger $Trigger -Settings $Settings -Principal $Principal -Description "铁律量化：每日选股池更新(D01)"
```

### 2.2 查询任务

```powershell
# 列出所有铁律量化任务
Get-ScheduledTask -TaskPath "\铁律量化\*"

# 查看任务详情
Get-ScheduledTask -TaskName "TL-每日选股池更新" | Get-ScheduledTaskInfo

# 查看任务状态
Get-ScheduledTask -TaskName "TL-每日选股池更新" | Select-Object -Property TaskName, State, LastRunTime, NextRunTime
```

### 2.3 启停任务

```powershell
# 禁用任务
Disable-ScheduledTask -TaskName "TL-每日选股池更新"

# 启用任务
Enable-ScheduledTask -TaskName "TL-每日选股池更新"

# 立即运行任务(测试用)
Start-ScheduledTask -TaskName "TL-每日选股池更新"

# 停止正在运行的任务
Stop-ScheduledTask -TaskName "TL-每日选股池更新"
```

### 2.4 修改任务

```powershell
# 修改触发器
$NewTrigger = New-ScheduledTaskTrigger -Daily -At "09:00"
Set-ScheduledTask -TaskName "TL-每日选股池更新" -Trigger $NewTrigger

# 修改执行参数
$NewAction = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-File `"new_script.ps1`""
Set-ScheduledTask -TaskName "TL-每日选股池更新" -Action $NewAction
```

### 2.5 删除任务

```powershell
Unregister-ScheduledTask -TaskName "TL-每日选股池更新" -Confirm:$false
```

---

## 三、任务命名规范

```
格式：TL-<类别>-<名称>
  TL   = 铁律量化项目前缀
  类别 = 每日(D)/每周(W)/每月(M)/维护(MAINT)
  名称 = 描述性短名

示例：
  TL-D-选股池更新     (每日D01)
  TL-D-行情采集        (每日D02)
  TL-W-财务刷新        (每周W01)
  TL-M-深度审计        (每月M01)
  TL-MAINT-缓存清理    (维护类)
```

---

## 四、任务文件夹组织

```
任务计划程序库/
└── 铁律量化/
    ├── 每日/
    │   ├── TL-D-选股池更新
    │   ├── TL-D-行情采集
    │   ├── TL-D-评分计算
    │   └── TL-D-报告生成
    ├── 每周/
    │   ├── TL-W-财务刷新
    │   └── TL-W-周度审计
    ├── 每月/
    │   └── TL-M-深度审计
    └── 维护/
        ├── TL-MAINT-数据备份
        └── TL-MAINT-缓存清理
```

---

## 五、常见设置模板

### 每日任务
```powershell
$Trigger = New-ScheduledTaskTrigger -Daily -At "09:30"
$Settings = New-ScheduledTaskSettingsSet `
  -AllowStartIfOnBatteries `
  -DontStopIfGoingOnBatteries `
  -StartWhenAvailable `
  -RestartCount 1 `
  -RestartInterval (New-TimeSpan -Minutes 2) `
  -ExecutionTimeLimit (New-TimeSpan -Minutes 10)
```

### 每周任务
```powershell
$Trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday -At "08:00"
$Settings = New-ScheduledTaskSettingsSet `
  -StartWhenAvailable `
  -RestartCount 2 `
  -RestartInterval (New-TimeSpan -Minutes 5) `
  -ExecutionTimeLimit (New-TimeSpan -Minutes 30)
```

### 登录时触发
```powershell
$Trigger = New-ScheduledTaskTrigger -AtLogOn -User "SYSTEM"
```

### 系统启动时触发
```powershell
$Trigger = New-ScheduledTaskTrigger -AtStartup
```

---

## 六、调试与排错

### 查看任务历史
```powershell
# 从事件查看器查看任务历史(需先启用历史记录)
Get-WinEvent -LogName "Microsoft-Windows-TaskScheduler/Operational" -MaxEvents 50 | Where-Object { $_.Message -like "*TL-*" }
```

### 常见错误

| 错误代码 | 含义 | 常见原因 | 解决 |
|:--------|:-----|:--------|:-----|
| 0x1 | 操作失败 | 脚本抛出异常 | 手动运行脚本看报错 |
| 0x41301 | 任务仍在运行 | 上次未完成+设置冲突 | 检查ExecutionTimeLimit |
| 0x800704DD | 未登录 | 任务配置为仅登录时运行 | 改用SYSTEM账户 |
| 0xC000013A | 进程被终止 | 超时/手动停止 | 检查超时设置 |
| 0x80070002 | 文件未找到 | 脚本路径错误 | 检查路径 |

### 调试步骤
1. **手动运行测试**：`Start-ScheduledTask -TaskName "TL-xxx"`
2. **检查上次运行结果**：`Get-ScheduledTaskInfo -TaskName "TL-xxx"`
3. **查看脚本日志**：检查脚本自身的日志输出
4. **检查权限**：确认执行账户有脚本目录的读写权
5. **检查执行策略**：`Get-ExecutionPolicy` 确认允许PowerShell脚本执行

---

## 七、任务锁机制

防止同一任务并行执行(千光-知识库/05-幂等性与失败恢复.md)：

```powershell
# 脚本内的任务锁实现
$LockFile = "$env:TEMP\TL-{task_id}.lock"
if (Test-Path $LockFile) {
    $lockAge = (Get-Date) - (Get-Item $LockFile).LastWriteTime
    if ($lockAge.TotalMinutes -lt 30) {
        Write-Output "任务已在运行中，跳过。"
        exit 0
    }
    Write-Output "锁文件过期(>$lockAge分钟)，强制运行。"
}
New-Item -ItemType File -Path $LockFile -Force | Out-Null
# ... 任务逻辑 ...
Remove-Item -Path $LockFile -Force -ErrorAction SilentlyContinue
```

---

## 八、维护规则

- 千光设计任务结构→红结实现脚本→红枫注册到Task Scheduler
- 每个任务必须在脚本内实现锁机制(防并行)
- 任务变更后测试运行一次确认
- 每季度检查所有任务运行历史(失败率/平均耗时)
