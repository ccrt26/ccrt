# F-SCHEDULE 自检报告

生成时间：2026-06-11T15:46:42.440996

## runtime_registry_check

```text
{
    "version": "2.0",
    "generated_at": "2026-06-11",
    "note": "macOS \u5f53\u524d\u552f\u4e00\u8c03\u5ea6\u6ce8\u518c\u5668: generate_launchd.py | \u552f\u4e00\u8c03\u5ea6\u6267\u884c\u5668: launchd. crontab/GitHub Actions schedule/PS1 \u5747\u7981\u6b62\u4f5c\u4e3a\u5f53\u524d\u8fd0\u884c\u5165\u53e3\u3002",
    "entries": [
        {
            "entry": "generate_launchd.py",
            "authority": "primary_scheduler_registry",
            "path": "\u4ee3\u7801\u6587\u4ef6/\u6bcf\u65e5\u8350\u80a1/scripts/generate_launchd.py",
            "platform": "macOS",
            "status": "active"
        },
        {
            "entry": "launchd",
            "authority": "primary_scheduler_runtime",
            "path": "system launchd",
            "platform": "macOS",
            "status": "active"
        },
        {
            "entry": "daily_workflow.py",
            "authority": "scheduled_executable",
            "path": "\u4ee3\u7801\u6587\u4ef6/\u6bcf\u65e5\u8350\u80a1/scripts/daily_workflow.py",
            "platform": "cross",
            "status": "active"
        },
        {
            "entry": "batch_data_collector.py",
            "authority": "data_collector",
            "path": "\u4ee3\u7801\u6587\u4ef6/\u6bcf\u65e5\u8350\u80a1/scripts/batch_data_collector.py",
            "platform": "cross",
            "status": "active"
        },
        {
            "entry": "daily_orchestrator.py",
            "authority": "report_generator",
            "path": "\u4ee3\u7801\u6587\u4ef6/tools/daily_orchestrator.py",
            "platform": "cross",
            "status": "active"
        },
        {
            "entry": "check_runtime_entry_authority.py",
            "authority": "runtime_gate",
            "path": "scripts/check_runtime_entry_authority.py",
            "platform": "cross",
            "status": "active"
        },
        {
            "entry": "feishu_bridge.py",
            "authority": "feishu_bridge",
            "path": "\u4ee3\u7801\u6587\u4ef6/tools/feishu_bridge.py",
            "platform": "macOS",
            "status": "active"
        },
        {
            "entry": "im_consumer.py",
            "authority": "im_consumer",
            "path": "\u4ee3\u7801\u6587\u4ef6/tools/im_consumer.py",
            "platform": "macOS",
            "status": "active"
        },
        {
            "entry": "sim_orchestrator.py",
            "authority": "sim_trading_engine",
            "path": "\u6a21\u62df\u4ea4\u6613/sim_orchestrator.py",
            "platform": "macOS",
            "status": "active"
        },
        {
            "entry": "scheduler_health_check.py",
            "authority": "scheduler_health",
            "path": "\u4ee3\u7801\u6587\u4ef6/tools/scheduler_health_check.py",
            "platform": "macOS",
            "status": "active"
        },
        {
            "entry": "Windows Task Scheduler",
            "authority": "legacy_scheduler",
            "path": "N/A",
            "platform": "Windows",
            "status": "legacy_forbidden"
        },
        {
            "entry": "register_tasks.ps1",
            "authority": "legacy_scheduler_registration",
            "path": "\u4ee3\u7801\u6587\u4ef6/\u6bcf\u65e5\u8350\u80a1/scripts/register_tasks.ps1",
            "platform": "Windows",
            "status": "forbidden_current_runtime"
        },
        {
            "entry": "setup_scheduler.ps1",
            "authority": "legacy_scheduler_registration",
            "path": "\u4ee3\u7801\u6587\u4ef6/\u6bcf\u65e5\u8350\u80a1/scripts/setup_scheduler.ps1",
            "platform": "Windows",
            "status": "forbidden_current_runtime"
        },
        {
            "entry": "register_pigeon_scheduler.ps1",
            "authority": "legacy_scheduler_registration",
            "path": "\u4ee3\u7801\u6587\u4ef6/\u4fe1\u9e3d\u4fe1\u606f\u91c7\u96c6/register_pigeon_scheduler.ps1",
            "platform": "Windows",
            "status": "forbidden_current_runtime"
        },
        {
            "entry": "batch_data_collector.ps1",
            "authority": "data_collector_legacy",
            "path": "\u4ee3\u7801\u6587\u4ef6/\u6bcf\u65e5\u8350\u80a1/scripts/batch_data_collector.ps1",
            "platform": "Windows",
            "status": "forbidden_when_python_replacement_exists"
        },
        {
            "entry": "daily_workflow.ps1",
            "authority": "workflow_legacy",
            "path": "\u4ee3\u7801\u6587\u4ef6/\u6bcf\u65e5\u8350\u80a1/scripts/daily_workflow.ps1",
            "platform": "Windows",
            "status": "forbidden_when_python_replacement_exists"
        },
        {
            "entry": "crontab",
            "authority": "legacy_scheduler",
            "path": "system crontab",
            "platform": "macOS",
            "status": "forbidden_current_runtime"
        },
        {
            "entry": "install_crontab.sh",
            "authority": "legacy_scheduler_registration",
            "path": "\u4ee3\u7801\u6587\u4ef6/tools/install_crontab.sh",
            "platform": "macOS",
            "status": "forbidden_current_runtime"
        },
        {
            "entry": "cron_runner.sh",
            "authority": "legacy_scheduler_runner",
            "path": "\u6a21\u62df\u4ea4\u6613/\u5de5\u5177/cron_runner.sh",
            "platform": "macOS",
            "status": "forbidden_current_runtime"
        },
        {
            "entry": "GitHub Actions schedule: sim_trading.yml",
            "authority": "legacy_scheduler",
            "path": ".github/workflows/sim_trading.yml",
            "platform": "GitHub",
            "status": "forbidden_current_runtime"
        }
    ]
}

```

## win_legacy_check

```text
{
    "version": "1.0",
    "generated_at": "2026-06-04",
    "entries": [
        {
            "legacy_path": "\u4ee3\u7801\u6587\u4ef6/\u6bcf\u65e5\u8350\u80a1/scripts/daily_workflow.ps1",
            "python_replacement": "\u4ee3\u7801\u6587\u4ef6/\u6bcf\u65e5\u8350\u80a1/scripts/daily_workflow.py",
            "status": "forbidden",
            "forbidden_reason": "\u5df2\u6709 Python \u66ff\u4ee3\uff0c\u53cc\u5165\u53e3\u98ce\u9669",
            "allowed_exception": "None"
        },
        {
            "legacy_path": "\u4ee3\u7801\u6587\u4ef6/\u6bcf\u65e5\u8350\u80a1/scripts/batch_data_collector.ps1",
            "python_replacement": "\u4ee3\u7801\u6587\u4ef6/\u6bcf\u65e5\u8350\u80a1/scripts/batch_data_collector.py",
            "status": "forbidden",
            "forbidden_reason": "\u5df2\u6709 Python \u66ff\u4ee3\uff0c\u53cc\u5165\u53e3\u98ce\u9669",
            "allowed_exception": "None"
        },
        {
            "legacy_path": "\u4ee3\u7801\u6587\u4ef6/\u91cd\u70b9\u80a1\u7968/run_keystock_analysis.ps1",
            "python_replacement": "\u4ee3\u7801\u6587\u4ef6/\u91cd\u70b9\u80a1\u7968/run_keystock_analysis.py",
            "status": "forbidden_when_python_available",
            "forbidden_reason": "\u5df2\u6709 Python \u66ff\u4ee3",
            "allowed_exception": "\u5f53 Python \u7248\u4e0d\u53ef\u7528\u65f6\u7684\u56de\u9000"
        },
        {
            "legacy_path": "\u4ee3\u7801\u6587\u4ef6/\u4fe1\u9e3d\u4fe1\u606f\u91c7\u96c6/pigeon_collector.ps1",
            "python_replacement": "\u4ee3\u7801\u6587\u4ef6/\u4fe1\u9e3d\u4fe1\u606f\u91c7\u96c6/pigeon_collector.py",
            "status": "forbidden",
            "forbidden_reason": "\u5df2\u6709 Python \u66ff\u4ee3\uff0c\u53cc\u5165\u53e3\u98ce\u9669",
            "allowed_exception": "None"
        },
        {
            "legacy_path": "\u4ee3\u7801\u6587\u4ef6/\u76d1\u7763\u673a\u5236/pipeline_engine.ps1",
            "python_replacement": "scripts/pipeline_engine.py",
            "status": "forbidden",
            "forbidden_reason": "\u5df2\u5168\u9762\u8fc1\u79fb\u81f3 Python \u7248",
            "allowed_exception": "None"
        },
        {
            "legacy_path": "\u4ee3\u7801\u6587\u4ef6/\u76d1\u7763\u673a\u5236/run_full_audit.ps1",
            "python_replacement": "scripts/audit_scan.py",
            "status": "forbidden",
            "forbidden_reason": "\u5df2\u5168\u9762\u8fc1\u79fb\u81f3 Python \u7248",
            "allowed_exception": "None"
        },
        {
            "legacy_path": "\u4ee3\u7801\u6587\u4ef6/\u76d1\u7763\u673a\u5236/check_redlines.ps1",
            "python_replacement": "\u4ee3\u7801\u6587\u4ef6/\u89c4\u5219\u7ea2\u7ebf/check_redlines.py",
            "status": "forbidden_when_python_available",
            "forbidden_reason": "\u5df2\u6709 Python \u66ff\u4ee3",
            "allowed_exception": "\u5f53 Python \u7248\u4e0d\u53ef\u7528\u65f6\u7684\u56de\u9000"
        },
        {
            "legacy_path": "\u4ee3\u7801\u6587\u4ef6/\u76d1\u7763\u673a\u5236/version_supervisor.ps1",
            "python_replacement": "\u4ee3\u7801\u6587\u4ef6/\u76d1\u7763\u673a\u5236/version_supervisor.py",
            "status": "forbidden_when_python_available",
            "forbidden_reason": "\u5df2\u6709 Python \u66ff\u4ee3",
            "allowed_exception": "None"
        },
        {
            "legacy_path": "\u6a21\u62df\u4ea4\u6613/\u4ea4\u6613\u5f15\u64ce/sim_trading.ps1",
            "python_replacement": "\u6a21\u62df\u4ea4\u6613/\u4ea4\u6613\u5f15\u64ce/sim_trading.py",
            "status": "forbidden_when_python_available",
            "forbidden_reason": "\u5df2\u6709 Python \u66ff\u4ee3",
            "allowed_exception": "None"
        },
        {
            "legacy_path": "\u6a21\u62df\u4ea4\u6613/\u5171\u4eab\u6a21\u5757/quote_engine.ps1",
            "python_replacement": "\u6a21\u62df\u4ea4\u6613/\u5171\u4eab\u6a21\u5757/quote_engine.py",
            "status": "forbidden_when_python_available",
            "forbidden_reason": "\u5df2\u6709 Python \u66ff\u4ee3",
            "allowed_exception": "None"
        },
        {
            "legacy_path": "\u6a21\u62df\u4ea4\u6613/\u5171\u4eab\u6a21\u5757/risk_framework.ps1",
            "python_replacement": "\u6a21\u62df\u4ea4\u6613/\u5171\u4eab\u6a21\u5757/risk_framework.py",
            "status": "forbidden_when_python_available",
            "forbidden_reason": "\u5df2\u6709 Python \u66ff\u4ee3",
            "allowed_exception": "None"
        },
        {
            "legacy_path": "\u6a21\u62df\u4ea4\u6613/\u5171\u4eab\u6a21\u5757/trade_utils.ps1",
            "python_replacement": "\u6a21\u62df\u4ea4\u6613/\u5171\u4eab\u6a21\u5757/trade_utils.py",
            "status": "forbidden_when_python_available",
            "forbidden_reason": "\u5df2\u6709 Python \u66ff\u4ee3",
            "allowed_exception": "None"
        },
        {
            "legacy_path": "\u4ee3\u7801\u6587\u4ef6/tools/health_check.ps1",
            "python_replacement": "\u4ee3\u7801\u6587\u4ef6/tools/health_check.py",
            "status": "forbidden_when_python_available",
            "forbidden_reason": "\u5df2\u6709 Python \u66ff\u4ee3",
            "allowed_exception": "\u5f53 Python \u7248\u4e0d\u53ef\u7528\u65f6\u7684\u56de\u9000"
        },
        {
            "legacy_path": "\u4ee3\u7801\u6587\u4ef6/tools/check_data_quality.ps1",
            "python_replacement": "\u4ee3\u7801\u6587\u4ef6/tools/check_data_quality.py",
            "status": "forbidden_when_python_available",
            "forbidden_reason": "\u5df2\u6709 Python \u66ff\u4ee3",
            "allowed_exception": "\u5f53 Python \u7248\u4e0d\u53ef\u7528\u65f6\u7684\u56de\u9000"
        },
        {
            "legacy_path": "\u4ee3\u7801\u6587\u4ef6/tools/git_autocommit.ps1",
            "python_replacement": "\u65e0",
            "status": "under_review",
            "forbidden_reason": "\u5f85\u786e\u8ba4\u662f\u5426\u4ecd\u5728\u4f7f\u7528",
            "allowed_exception": "\u5f85\u5b9a"
        }
    ]
}

```

## runtime_gate_after

```text
{
  "result": "PASS",
  "checks": [
    {
      "check_id": "C1",
      "field": "registry",
      "status": "PASS",
      "expected": "合法JSON",
      "actual": "20 entries",
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
      "expected": "['generate_launchd.py', 'launchd', 'daily_workflow.py', 'batch_data_collector.py', 'daily_orchestrator.py', 'feishu_bridge.py', 'im_consumer.py', 'sim_orchestrator.py', 'scheduler_health_check.py']",
      "actual": "['generate_launchd.py', 'launchd', 'daily_workflow.py', 'batch_data_collector.py', 'daily_orchestrator.py', 'feishu_bridge.py', 'im_consumer.py', 'sim_orchestrator.py', 'scheduler_health_check.py']",
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
      "expected": "全部 10 个已登记",
      "actual": "全部已登记",
      "message": ""
    }
  ]
}

```

## generate_launchd_list

```text
铁律量化 launchd 调度任务清单
============================================================
  git_autosweep        :07                自动 Git 同步清扫（每小时 :07）
  pigeon               19 :07 周一～五        信鸽事件采集（交易日 19:07）
  daily_signal         16 :15 周一～五        日报信号（交易日 16:15）
  deep_signal          20 :30 周五          深度分析信号（周五 20:30）
  post_eval            17 :20 周一～五        后评估正式链路（交易日 17:20）
  scheduler_health     :03                调度心跳监控（每小时 :03、:33）
  sim_trading          09 :45 周一～五        模拟交易引擎开盘执行（交易日 09:45）
  feishu_bridge        每 30 秒             飞书消息桥接（每 30 秒轮询）
  im_consumer          每 30 秒             IM 消息消费（每 30 秒轮询）


```

## crontab_after

```text

```

## launchctl_tielv_after

```text
-	0	com.tielv.pigeon
-	1	com.tielv.scheduler-health
-	0	com.tielv.feishu-bridge
-	0	com.tielv.daily-signal
39161	0	com.tielv.caffeinate
-	0	com.tielv.post-eval
-	0	com.tielv.sim-trading
-	0	com.tielv.git-autosweep
-	0	com.tielv.deep-signal
-	0	com.tielv.im-consumer

```

## git_status_after

```text
 M .github/workflows/sim_trading.yml
 M "00_\351\241\271\347\233\256\345\234\260\345\237\272/06_\350\260\203\345\272\246\344\270\216\350\277\220\350\241\214/runtime_entry_registry.json"
 M "00_\351\241\271\347\233\256\345\234\260\345\237\272/06_\350\260\203\345\272\246\344\270\216\350\277\220\350\241\214/schedule_authority_contract.md"
 M scripts/check_runtime_entry_authority.py
 M "\344\270\264\346\227\266\346\212\245\345\221\212/git_autocommit.log"
 M "\344\273\243\347\240\201\346\226\207\344\273\266/tools/install_crontab.sh"
 M "\344\273\243\347\240\201\346\226\207\344\273\266/\346\257\217\346\227\245\350\215\220\350\202\241/scripts/generate_launchd.py"

```
