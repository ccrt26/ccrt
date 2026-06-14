# F-SCHEDULE 调度收口执行报告

生成时间：2026-06-11T15:46:38.948756

## 修改范围
- runtime_entry_registry.json (v1.0→v2.0)
- schedule_authority_contract.md (v1.0→v2.0)
- generate_launchd.py (全面重写)
- check_runtime_entry_authority.py (新增 C7-C12)
- install_crontab.sh (改为废弃保护)
- .github/workflows/sim_trading.yml (移除 schedule，保留 workflow_dispatch + dry-run)

## 执行结果
- crontab 铁律量化任务：已清理（crontab 现为空）
- launchd 权威任务：已由 generate_launchd.py 安装 9 个任务
- GitHub Actions 定时模拟交易：已取消 schedule，保留 dry-run
- PS1/cron_runner/data_only：均已被禁止
- runtime gate：全部 12 项检查 PASS（C1-C12）

## 安装的 launchd 任务
| 任务 | 调度 | 命令 |
|:-----|:-----|:------|
| git_autosweep | 每小时 :07 | git_autosweep.py |
| pigeon | 交易日 19:07 | daily_orchestrator.py --mode pigeon |
| daily_signal | 交易日 16:15 | daily_orchestrator.py --mode daily |
| deep_signal | 周五 20:30 | daily_orchestrator.py --mode deep |
| post_eval | 交易日 17:20 | daily_workflow.py --mode eval |
| scheduler_health | 每小时 :03、:33 | scheduler_health_check.py |
| sim_trading | 交易日 09:45 | sim_orchestrator.py |
| feishu_bridge | 每 30s | feishu_bridge.py --once |
| im_consumer | 每 30s | im_consumer.py --once |

## 待复查
交给 Codex 执行 G5 独立复查。
