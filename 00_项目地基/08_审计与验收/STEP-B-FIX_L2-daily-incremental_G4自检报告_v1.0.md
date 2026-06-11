# G4 自检记录：STEP-B-FIX L2日增量自动接入修复

> 日期：2026-06-11
> 流程：F-DATA + F-SCHEDULE + F-GATE
> pipeline：RUN-20260611-012309-1c1116
> 执行角色：情墨（G2）+ 红结（G3）
> 状态：G4 自检完成，G5 待旧影复查，G6 待腰子放行

---

## 1. 根因

L2 日增量没有被接入自动调度/日常编排。crontab 有 data_only 数据链，但 daily_workflow.py --mode data_only 没有调用 scripts/update_l2_cache.py。因此 L1 已有 20260610 数据，但 L2 哨兵仍停在 2026-06-09T22:05:56。

## 2. 修改内容

| 编号 | 文件 | 变更 |
|:----:|:-----|:-----|
| A1 | 代码文件/每日荐股/scripts/daily_workflow.py | run_data_only() 新增 Phase 2.4：materialize 成功后调用 update_l2_cache.py --date <目标日期>；返回 0→继续，非 0→FAILED；后续阶段号顺延（2.6→2.7→3.5） |
| D1 | 00_项目地基/09_迁移计划/L2_INDEX_运行化阶段接力索引_v1.0.md | §1 L2 SQLite 行更新为"日增量已接入 data_only 调度链"；新增一行"L2 日增量接入" |
| D2 | 00_项目地基/09_迁移计划/L2_RUNBOOK_地基1.0后运行化总方案_v1.0.md | §10 新增暂停点 8：L2 日增量从 data_only 扩大到其他调度模式需另开 G2/G3；§11 更新 STEP-B 状态 |

## 3. 执行顺序（data_only 链路变更后）

batch_data_collector → data_full 校验 → materialize_daily_authoritative_cache → **update_l2_cache.py**（新增） → DQ-Gate → check_daily_data_chain_health → archive_data

## 4. 验收标准（已执行）

| # | 命令 | 结果 |
|:-:|:-----|:----:|
| 1 | `python3 -m py_compile daily_workflow.py update_l2_cache.py check_d04_health.py` | PASS ✅ 语法检查通过 |
| 2 | `python3 scripts/update_l2_cache.py --date 20260610 --dry-run` | PASS ✅ 55 只股票待处理 |
| 3 | `python3 scripts/update_l2_cache.py --date 20260610 --limit-code 600114` | PASS ✅ 写入 1 条 kline |
| 4 | `python3 scripts/check_d04_health.py --dry-run` | PASS ✅ 9 PASS, 0 WARN, 0 BLOCK |
| 5 | `sqlite3 l2_cache.db "select max(trade_date), count(*) from kline"` | PASS ✅ max=2026-06-10, 3941 行（3140→3941） |
| 6 | `tail -n 5 operation_log.jsonl` | PASS ✅ 出现 update(date=20260610 upserted=1) 记录 |
| 7 | `grep -R UnifiedDataSource daily_workflow.py daily_orchestrator.py cached_data_source.py` | PASS ✅ 无引用 |
| 8 | `last_update.json` sentinel | PASS ✅ status=OK, updated_at=2026-06-11T09:29:01 |

## 4a. data_only 链路确认

新增 Phase 2.4 后 data_only 链路：batch_data_collector → data_full 校验 → materialize → **update_l2_cache**（新增） → DQ-Gate → health check → archive_data。不生成报告、不切入口。

## 5. 回滚方案

| 级别 | 回滚操作 |
|:----:|:---------|
| 代码 | 恢复 daily_workflow.py 中新增的 L2 增量调用块（Phase 2.4 段 + 阶段号调整） |
| 数据 | 若小范围实跑写入异常，使用 update_l2_cache.py 自动生成的 backup/ 恢复 l2_cache.db |
| 验证 | 回滚后重跑：python3 scripts/check_d04_health.py --dry-run |

## 6. 严禁修改确认

| 禁止项 | 状态 |
|:-------|:----:|
| 日报/深度分析正式读取逻辑 | 未修改 ✅ |
| 每日荐股评分逻辑 | 未修改 ✅ |
| daily_orchestrator.py 的生产行为 | 未修改 ✅ |
| cached_data_source.py 为读 L2 | 未修改 ✅ |
| runtime_entry_registry.json 为生产切换 | 未修改 ✅ |
| 不改 WARN 为 BLOCK | 未修改 ✅ |
| 不删除历史接力包 | 未修改 ✅ |
| 不处理 Git commit/push/PR | 未操作 ✅ |

## 7. 已知例外

- C5 情墨 HMAC 验签因检查清单后期补充 file_budgets 字段导致哈希变更失效，属于明示例外
- pipeline actor/HMAC 仍为过渡模式（actual_actor=空）
- 本自检记录不代签 G5 旧影复查 / G6 腰子放行
