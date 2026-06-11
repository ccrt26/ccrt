# F-SCHEDULE-R1 自检报告

生成时间：2026-06-11T16:03:13.883297

## runtime_gate

```text
{
  "result": "PASS",
  "checks": [
    {
      "check_id": "C1",
      "field": "registry",
      "status": "PASS",
      "expected": "合法JSON",
      "actual": "25 entries",
      "message": ""
    },
    {
      "check_id": "C2",
      "field": "legacy_registry",
      "status": "PASS",
      "expected": "合法JSON",
      "actual": "15 entries",
      "message": ""
    },
    {
      "check_id": "C3",
      "field": "registry_entries",
      "status": "PASS",
      "expected": "['generate_launchd.py', 'launchd', 'daily_workflow.py', 'batch_data_collector.py', 'daily_orchestrator.py', 'feishu_bridge.py', 'im_consumer.py', 'sim_orchestrator.py', 'scheduler_health_check.py', 'git_autosweep.py', 'pigeon', 'daily_signal', 'deep_signal', 'post_eval']",
      "actual": "['generate_launchd.py', 'launchd', 'daily_workflow.py', 'batch_data_collector.py', 'daily_orchestrator.py', 'feishu_bridge.py', 'im_consumer.py', 'sim_orchestrator.py', 'scheduler_health_check.py', 'git_autosweep.py', 'pigeon', 'daily_signal', 'deep_signal', 'post_eval']",
      "message": ""
    },
    {
      "check_id": "C4",
      "field": "scheduler_ps1",
      "status": "PASS",
      "expected": "全部标记",
      "actual": "全部标记",
      "message": ""
    },
    {
      "check_id": "C4b",
      "field": "macos_forbidden",
      "status": "PASS",
      "expected": "全部标记",
      "actual": "全部标记",
      "message": ""
    },
    {
      "check_id": "C5",
      "field": "legacy_ps1",
      "status": "PASS",
      "expected": "全部登记",
      "actual": "全部登记",
      "message": ""
    },
    {
      "check_id": "C6",
      "field": "collector_ps_fallback",
      "status": "PASS",
      "expected": "已阻断",
      "actual": "sys.exit(1)",
      "message": ""
    },
    {
      "check_id": "C7",
      "field": "generate_launchd_placeholder",
      "status": "PASS",
      "expected": "无占位任务",
      "actual": "无占位任务",
      "message": ""
    },
    {
      "check_id": "C8",
      "field": "generate_launchd_forbidden_refs",
      "status": "PASS",
      "expected": "无禁止引用",
      "actual": "无禁止引用",
      "message": ""
    },
    {
      "check_id": "C9",
      "field": "github_actions_schedule",
      "status": "PASS",
      "expected": "无 schedule",
      "actual": "无 schedule",
      "message": ""
    },
    {
      "check_id": "C10",
      "field": "install_crontab_deprecated",
      "status": "PASS",
      "expected": "废弃保护",
      "actual": "已标记废弃",
      "message": ""
    },
    {
      "check_id": "C11",
      "field": "crontab_tielv_tasks",
      "status": "PASS",
      "expected": "无铁律量化任务",
      "actual": "无铁律量化任务",
      "message": ""
    },
    {
      "check_id": "C12",
      "field": "launchd_registration",
      "status": "PASS",
      "expected": "全部 9 个已登记",
      "actual": "全部已登记",
      "message": ""
    }
  ]
}

```

## crontab

```text

```

## launchctl

```text
-	0	com.tielv.pigeon
-	1	com.tielv.scheduler-health
-	0	com.tielv.feishu-bridge
-	0	com.tielv.daily-signal
-	0	com.tielv.post-eval
-	0	com.tielv.sim-trading
-	0	com.tielv.git-autosweep
-	0	com.tielv.deep-signal
-	0	com.tielv.im-consumer

```

## plists

```text
--- /Users/ccrt/Library/LaunchAgents/com.tielv.daily-signal.plist
{
  "KeepAlive" => false
  "Label" => "com.tielv.daily-signal"
  "ProgramArguments" => [
    0 => "python3"
    1 => "/Users/ccrt/ccrt/代码文件/tools/daily_orchestrator.py"
    2 => "--mode"
    3 => "daily"
  ]
  "RunAtLoad" => false
  "StandardErrorPath" => "/Users/ccrt/ccrt/代码文件/数据/logs/daily-signal.stderr.log"
  "StandardOutPath" => "/Users/ccrt/ccrt/代码文件/数据/logs/daily-signal.stdout.log"
  "StartCalendarInterval" => [
    0 => {
      "Hour" => 16
      "Minute" => 15
      "Weekday" => 1
    }
    1 => {
      "Hour" => 16
      "Minute" => 15
      "Weekday" => 2
    }
    2 => {
      "Hour" => 16
      "Minute" => 15
      "Weekday" => 3
    }
    3 => {
      "Hour" => 16
      "Minute" => 15
      "Weekday" => 4
    }
    4 => {
      "Hour" => 16
      "Minute" => 15
      "Weekday" => 5
    }
  ]
  "WorkingDirectory" => "/Users/ccrt/ccrt"
}
--- /Users/ccrt/Library/LaunchAgents/com.tielv.deep-signal.plist
{
  "KeepAlive" => false
  "Label" => "com.tielv.deep-signal"
  "ProgramArguments" => [
    0 => "python3"
    1 => "/Users/ccrt/ccrt/代码文件/tools/daily_orchestrator.py"
    2 => "--mode"
    3 => "deep"
  ]
  "RunAtLoad" => false
  "StandardErrorPath" => "/Users/ccrt/ccrt/代码文件/数据/logs/deep-signal.stderr.log"
  "StandardOutPath" => "/Users/ccrt/ccrt/代码文件/数据/logs/deep-signal.stdout.log"
  "StartCalendarInterval" => [
    0 => {
      "Hour" => 20
      "Minute" => 30
      "Weekday" => 5
    }
  ]
  "WorkingDirectory" => "/Users/ccrt/ccrt"
}
--- /Users/ccrt/Library/LaunchAgents/com.tielv.feishu-bridge.plist
{
  "KeepAlive" => false
  "Label" => "com.tielv.feishu-bridge"
  "ProgramArguments" => [
    0 => "python3"
    1 => "/Users/ccrt/ccrt/代码文件/tools/feishu_bridge.py"
    2 => "--once"
  ]
  "RunAtLoad" => true
  "StandardErrorPath" => "/Users/ccrt/ccrt/代码文件/数据/logs/feishu-bridge.stderr.log"
  "StandardOutPath" => "/Users/ccrt/ccrt/代码文件/数据/logs/feishu-bridge.stdout.log"
  "StartInterval" => 30
  "WorkingDirectory" => "/Users/ccrt/ccrt"
}
--- /Users/ccrt/Library/LaunchAgents/com.tielv.git-autosweep.plist
{
  "KeepAlive" => false
  "Label" => "com.tielv.git-autosweep"
  "ProgramArguments" => [
    0 => "python3"
    1 => "/Users/ccrt/ccrt/代码文件/tools/git_autosweep.py"
  ]
  "RunAtLoad" => true
  "StandardErrorPath" => "/Users/ccrt/ccrt/代码文件/数据/logs/git-autosweep.stderr.log"
  "StandardOutPath" => "/Users/ccrt/ccrt/代码文件/数据/logs/git-autosweep.stdout.log"
  "StartCalendarInterval" => [
    0 => {
      "Minute" => 7
    }
  ]
  "WorkingDirectory" => "/Users/ccrt/ccrt"
}
--- /Users/ccrt/Library/LaunchAgents/com.tielv.im-consumer.plist
{
  "KeepAlive" => false
  "Label" => "com.tielv.im-consumer"
  "ProgramArguments" => [
    0 => "python3"
    1 => "/Users/ccrt/ccrt/代码文件/tools/im_consumer.py"
    2 => "--once"
  ]
  "RunAtLoad" => true
  "StandardErrorPath" => "/Users/ccrt/ccrt/代码文件/数据/logs/im-consumer.stderr.log"
  "StandardOutPath" => "/Users/ccrt/ccrt/代码文件/数据/logs/im-consumer.stdout.log"
  "StartInterval" => 30
  "WorkingDirectory" => "/Users/ccrt/ccrt"
}
--- /Users/ccrt/Library/LaunchAgents/com.tielv.pigeon.plist
{
  "KeepAlive" => false
  "Label" => "com.tielv.pigeon"
  "ProgramArguments" => [
    0 => "python3"
    1 => "/Users/ccrt/ccrt/代码文件/tools/daily_orchestrator.py"
    2 => "--mode"
    3 => "pigeon"
  ]
  "RunAtLoad" => false
  "StandardErrorPath" => "/Users/ccrt/ccrt/代码文件/数据/logs/pigeon.stderr.log"
  "StandardOutPath" => "/Users/ccrt/ccrt/代码文件/数据/logs/pigeon.stdout.log"
  "StartCalendarInterval" => [
    0 => {
      "Hour" => 19
      "Minute" => 7
      "Weekday" => 1
    }
    1 => {
      "Hour" => 19
      "Minute" => 7
      "Weekday" => 2
    }
    2 => {
      "Hour" => 19
      "Minute" => 7
      "Weekday" => 3
    }
    3 => {
      "Hour" => 19
      "Minute" => 7
      "Weekday" => 4
    }
    4 => {
      "Hour" => 19
      "Minute" => 7
      "Weekday" => 5
    }
  ]
  "WorkingDirectory" => "/Users/ccrt/ccrt"
}
--- /Users/ccrt/Library/LaunchAgents/com.tielv.post-eval.plist
{
  "KeepAlive" => false
  "Label" => "com.tielv.post-eval"
  "ProgramArguments" => [
    0 => "python3"
    1 => "/Users/ccrt/ccrt/代码文件/每日荐股/scripts/daily_workflow.py"
    2 => "--mode"
    3 => "eval"
  ]
  "RunAtLoad" => false
  "StandardErrorPath" => "/Users/ccrt/ccrt/代码文件/数据/logs/post-eval.stderr.log"
  "StandardOutPath" => "/Users/ccrt/ccrt/代码文件/数据/logs/post-eval.stdout.log"
  "StartCalendarInterval" => [
    0 => {
      "Hour" => 17
      "Minute" => 20
      "Weekday" => 1
    }
    1 => {
      "Hour" => 17
      "Minute" => 20
      "Weekday" => 2
    }
    2 => {
      "Hour" => 17
      "Minute" => 20
      "Weekday" => 3
    }
    3 => {
      "Hour" => 17
      "Minute" => 20
      "Weekday" => 4
    }
    4 => {
      "Hour" => 17
      "Minute" => 20
      "Weekday" => 5
    }
  ]
  "WorkingDirectory" => "/Users/ccrt/ccrt"
}
--- /Users/ccrt/Library/LaunchAgents/com.tielv.scheduler-health.plist
{
  "KeepAlive" => false
  "Label" => "com.tielv.scheduler-health"
  "ProgramArguments" => [
    0 => "python3"
    1 => "/Users/ccrt/ccrt/代码文件/tools/scheduler_health_check.py"
  ]
  "RunAtLoad" => true
  "StandardErrorPath" => "/Users/ccrt/ccrt/代码文件/数据/logs/scheduler-health.stderr.log"
  "StandardOutPath" => "/Users/ccrt/ccrt/代码文件/数据/logs/scheduler-health.stdout.log"
  "StartCalendarInterval" => [
    0 => {
      "Minute" => 3
    }
    1 => {
      "Minute" => 33
    }
  ]
  "WorkingDirectory" => "/Users/ccrt/ccrt"
}
--- /Users/ccrt/Library/LaunchAgents/com.tielv.sim-trading.plist
{
  "KeepAlive" => false
  "Label" => "com.tielv.sim-trading"
  "ProgramArguments" => [
    0 => "python3"
    1 => "/Users/ccrt/ccrt/模拟交易/sim_orchestrator.py"
  ]
  "RunAtLoad" => false
  "StandardErrorPath" => "/Users/ccrt/ccrt/代码文件/数据/logs/sim-trading.stderr.log"
  "StandardOutPath" => "/Users/ccrt/ccrt/代码文件/数据/logs/sim-trading.stdout.log"
  "StartCalendarInterval" => [
    0 => {
      "Hour" => 9
      "Minute" => 45
      "Weekday" => 1
    }
    1 => {
      "Hour" => 9
      "Minute" => 45
      "Weekday" => 2
    }
    2 => {
      "Hour" => 9
      "Minute" => 45
      "Weekday" => 3
    }
    3 => {
      "Hour" => 9
      "Minute" => 45
      "Weekday" => 4
    }
    4 => {
      "Hour" => 9
      "Minute" => 45
      "Weekday" => 5
    }
  ]
  "WorkingDirectory" => "/Users/ccrt/ccrt"
}

```

## git_status

```text
 M .github/workflows/sim_trading.yml
 M "00_\351\241\271\347\233\256\345\234\260\345\237\272/06_\350\260\203\345\272\246\344\270\216\350\277\220\350\241\214/runtime_entry_registry.json"
 M "00_\351\241\271\347\233\256\345\234\260\345\237\272/06_\350\260\203\345\272\246\344\270\216\350\277\220\350\241\214/schedule_authority_contract.md"
 M scripts/check_runtime_entry_authority.py
 M "\344\273\243\347\240\201\346\226\207\344\273\266/tools/install_crontab.sh"
 M "\344\273\243\347\240\201\346\226\207\344\273\266/\346\257\217\346\227\245\350\215\220\350\202\241/scripts/generate_launchd.py"

```
