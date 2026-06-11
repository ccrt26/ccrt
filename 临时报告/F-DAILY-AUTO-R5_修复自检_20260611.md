# F-DAILY-AUTO-R5 修复自检 20260611

## 结论

PASS，范围限定为 data -> materialize -> signal 自动化闭环。

本次不声明最终 MD/HTML 日报自动生成 PASS。

## 已通过检查

- runtime gate: PASS
- v36 readiness: READY 50/50
- kline_match: 10/10
- signal date: 20260611
- signal data_ready: true
- signal stock_count: 10
- signal pipeline_mode: true
- lock status: absent
- today_run 日志出现 pipeline mode
- today_run 日志无 TIMEOUT

## 核心产物

- `.claude/signal_daily_report.json`
- `临时报告/F-DAILY-AUTO-R5_signal_check_20260611.json`
- `临时报告/F-DAILY-AUTO-R5_v36_check_20260611.json`
- `临时报告/F-DAILY-AUTO-R5_runtime_gate_20260611.json`
- `临时报告/F-DAILY-AUTO-R5_today_run_20260611.log`
- `临时报告/F-DAILY-AUTO-R5_lock_status_20260611.txt`

## 修改范围

- `代码文件/tools/daily_orchestrator.py`
- `scripts/run_daily_data_retry_once.py`
- `scripts/run_daily_data_pipeline_today.py`
- `代码文件/lib/config_loader.py`
- `代码文件/每日荐股/scripts/generate_launchd.py`
- `00_项目地基/06_调度与运行/runtime_entry_registry.json`
- `00_项目地基/06_调度与运行/schedule_authority_contract.md`

## 未覆盖范围

- 不覆盖最终 MD/HTML 日报自动生成。
- 不覆盖 PDF。
- 不修改策略、评分、买卖逻辑。
- 不修改重点股票分析结论。

## 下一阶段

新开 F-DAILY-REPORT-AUTO：实现 signal -> MD/JSON/HTML 的逐票自动生成闭环。
PDF 不进入每日自动放行标准。
