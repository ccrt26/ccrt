# 地基 1.0 后运行化总方案 v1.0

> 日期：2026-06-09
> 状态修正：2026-06-11
> 流程编号：F-ARCH + F-MIGRATE + F-DATA + F-SCHEDULE + F-GATE
> 当前阶段门：运行化总方案；A/B 收口证据需按 `L2_INDEX_运行化阶段接力索引_v1.0.md` §2.1 追溯
> 不授权：生产入口切换、STEP-C 扩展到每日荐股/保护机制/模拟交易、闸门直接收紧为 BLOCK

---

## 1. 前置检查结论

地基 1.0 的正确定位是：治理、架构、契约、注册表、闸门、运行边界、回滚边界已建立；运行系统尚未全部按新地基生产运行。

| 项目 | 结论 |
|:-----|:-----|
| 架构冻结 | 已完成，不建议继续扩大重构 |
| 数据分层 | L1/L2/L3 结构成立，L2 已有 `kline` 与 `score_history` 部分数据，其他表仍为空 |
| 正式入口 | 暂不切换，深度分析和每日报告继续旧生产路径 |
| UDS | 继续 shadow；当前 STEP-C 仅限深度分析与每日报告方向 |
| 闸门 | 保持观察期，不立即从 WARN/SKIP 收紧为 BLOCK |
| 文档资产 | STEP-A/B 收口证据已按实际工程名归档，必须通过运行化索引 §2.1 映射读取 |
| formal pipeline | actor/HMAC 继续明示例外，另开工具链治理 |

Formal pipeline 未通过；RUN 仍停在当前阶段。
本阶段基于用户明确授权与接力包流程例外继续，不等同于 formal pipeline PASS。
不得伪造 actor/HMAC sign-off，不得代签角色结论，不得自动推进后续阶段。

---

## 2. 阶段目标

运行化阶段的目标不是“继续重构地基”，而是把已经建好的地基按低风险顺序接入真实运行：

1. 文档与接力包索引化，减少后续会话迷路。
2. L2 SQLite 从空 schema 进入可审计数据状态，并继续补齐日增量与空表。
3. UDS 在深度分析与每日报告方向做 shadow diff，不影响生产。
4. 基于稳定 shadow 结果，单独评估是否切深度分析/每日报告入口。

当前不处理每日荐股、保护机制、模拟交易等其他场景；这些场景如需接入 L2/shadow，必须另开 G2 方案。

---

## 3. 允许修改范围

| 阶段 | 允许范围 |
|:----:|:---------|
| STEP-A | `00_项目地基/09_迁移计划/` 下新增或更新索引、手册、接力方案 |
| STEP-B | 经用户确认后，按方案使用 `scripts/build_l2_cache.py`, `scripts/update_l2_cache.py`, `scripts/rebuild_score_history.py`, `scripts/sync_quality_flag.py`, `scripts/check_d04_health.py` 与 `代码文件/数据/l2_cache/` |
| STEP-C | 经用户确认后，只在深度分析与每日报告范围内做 shadow-only 运行与 diff 记录 |
| STEP-D | 只输出切换评估、风险矩阵和回滚方案；不直接切换 |

---

## 4. 禁止修改范围

| 禁止项 | 原因 |
|:-------|:-----|
| 未确认前修改 `daily_workflow.py` | 生产入口，需单独 G2/G3；每日荐股场景未纳入当前 STEP-C |
| 未确认前修改 `daily_orchestrator.py` | 调度入口，需单独 G2/G3 |
| 未确认前修改 `cached_data_source.py` | 每日报告数据取数关键路径 |
| 未确认前修改 `unified_data_source.py` 的生产行为 | 只能 shadow，不切正式读取 |
| 未确认前修改 `runtime_entry_registry.json` 的生产状态 | 入口权威注册表 |
| 将 STEP-C 扩展为全场景 | 每日荐股、保护机制、模拟交易等未进入当前 shadow 范围 |
| 直接删除旧接力包或历史 md | 证据链不可丢 |
| 将闸门策略直接改为 BLOCK | 需要观察期证据和 G2 策略 |

---

## 5. 四阶段路线

| 步骤 | 目标 | 通过条件 | 下一步 |
|:----:|:-----|:---------|:-------|
| STEP-A | 文档与接力包整理 | 热索引与 Markdown 治理 G6 收口可追溯，证据链不丢 | 已可作为接力入口 |
| STEP-B | L2 数据实装 | schema、脚本、备份、`kline`/`score_history` 部分数据可审计；日增量和空表仍需继续健康观察 | 允许在深度分析/每日报告范围进入 STEP-C |
| STEP-C | 深度分析与每日报告 shadow 验证 | 仅这两个方向的 UDS/L2 shadow diff 连续稳定，失败可回滚到纯旧路径 | 之后才评估 STEP-D |
| STEP-D | 生产入口切换评估 | 切换矩阵、风险、回滚、验收命令、用户确认点齐全 | 另开生产切换 G2/G3 |

---

## 6. 数据分层采集、生成、存储路线

| 步骤 | 名称 | 说明 | 是否切生产 |
|:----:|:-----|:-----|:----------:|
| 1 | L1 稳定日更 | 确认 `data_full.json`, `kline_cache`, `fund_flow_cache` 继续作为当日权威 | 否 |
| 2 | L3 归档跑稳 | 每日归档、周级永久快照、manifest/index 可追溯 | 否 |
| 3 | L2 小样本回填 | 少量股票、少量日期写入 `kline` / `score_history` 等表，验证主键、索引、quality_flag | 否 |
| 4 | L2 全量回填 | 小样本 PASS 后构建全量历史数据 | 否 |
| 5 | L2 日增量 | 接入 `update_l2_cache.py`，每日更新、哨兵、backup、health | 否 |
| 6 | UDS shadow 读取 L2 | `UnifiedDataSource` 在深度分析与每日报告 shadow 模式读取 L2，跑 diff | 否 |
| 7 | 其他场景另案 | 每日荐股、保护机制、模拟交易等不在当前 STEP-C 范围 | 否 |

---

## 7. 文件级清单

| 类别 | 文件 |
|:-----|:-----|
| 运行入口 | `代码文件/每日荐股/scripts/daily_workflow.py`, `代码文件/tools/daily_orchestrator.py` |
| 数据源 | `代码文件/lib/cached_data_source.py`, `代码文件/数据/unified_data_source.py` |
| 入口注册 | `00_项目地基/06_调度与运行/runtime_entry_registry.json` |
| L2 构建 | `scripts/build_l2_cache.py`, `scripts/update_l2_cache.py`, `scripts/rebuild_score_history.py` |
| L2 质量 | `scripts/sync_quality_flag.py`, `scripts/check_d04_health.py` |
| 闸门 | `scripts/check_numeric_source_consistency.py`, `scripts/check_freshness_degradation.py` |
| 闸门配置 | `00_项目地基/04_一致性闸门/numeric_field_mapping.json`, `00_项目地基/04_一致性闸门/freshness_rules.json` |
| 归档 | `代码文件/每日荐股/scripts/archive_data.py`, `scripts/materialize_daily_authoritative_cache.py` |

---

## 8. 验收命令

文档层验收：

```bash
find 00_项目地基/09_迁移计划 -maxdepth 1 -type f -print
git status --short -- 00_项目地基/09_迁移计划
```

L2 只读健康检查：

```bash
python3 scripts/check_d04_health.py --dry-run
```

L2 行数审计：

```bash
sqlite3 代码文件/数据/l2_cache/l2_cache.db "select 'financials', count(*) from financials union all select 'historical_percentiles', count(*) from historical_percentiles union all select 'kline', count(*) from kline union all select 'macro', count(*) from macro union all select 'returns', count(*) from returns union all select 'risk_metrics', count(*) from risk_metrics union all select 'score_history', count(*) from score_history;"
```

生产不切换证明：

```bash
git diff -- 代码文件/每日荐股/scripts/daily_workflow.py 代码文件/tools/daily_orchestrator.py 代码文件/lib/cached_data_source.py 代码文件/数据/unified_data_source.py 00_项目地基/06_调度与运行/runtime_entry_registry.json
```

---

## 9. 回滚与不切生产证明

本方案本身只新增文档，回滚方式为删除本阶段新增文档并恢复 `目录治理索引.md` 的新增入口。

后续 STEP-B/STEP-C/STEP-D 必须分别提供自己的回滚证明：

| 阶段 | 回滚原则 |
|:----:|:---------|
| STEP-B | L2 写入前备份；小样本可清表或恢复 DB；全量前必须保存备份 |
| STEP-C | shadow-only 可关闭；不修改正式入口则无需生产回滚 |
| STEP-D | 只做评估，不做切换；若进入切换实施，必须备份 MD/sidecar 和入口配置 |

---

## 10. 暂停点

必须暂停并等待用户确认的点：

1. STEP-A 中任何删除、移动、归档历史接力包动作。
2. STEP-B 中任何非 dry-run 写入 L2 DB 动作。
3. STEP-B 从小样本扩大到全量回填，或从已有部分数据扩大到新表/新字段。
4. STEP-C 修改任何正式入口调用方式。
5. STEP-D 从评估进入实际生产入口切换。
6. STEP-C 扩展到每日荐股、保护机制、模拟交易等其他场景。
7. 任何 actor/HMAC formal pipeline 修复或替代策略。
8. L2 日增量从 data_only 链路扩大到其他调度模式（如 daily 模式），需另开 G2/G3。

## 11. 2026-06-11 根因修正

此前本 runbook 保留了 2026-06-09 的旧表述：“当前阶段门为 G0/G2”“L2 当前仅有空表”。实际后续已经发生：

| 项 | 修正 |
|:---|:-----|
| STEP-A | 收口证据以 Markdown 热区治理 G6、运行化索引、总 runbook 等形式存在，不能只按 `STEP-A` 文件名搜索 |
| STEP-B | L2 已有 `kline=3940`、`score_history=294`，不再是空库；日增量已接入 data_only 调度链（2026-06-11 STEP-B-FIX）；其余空表仍需继续治理 |
| STEP-C | 当前只覆盖深度分析与每日报告，不覆盖每日荐股等其他场景 |

后续新会话评估进度时，以 `L2_INDEX_运行化阶段接力索引_v1.0.md` §2.1 的收口证据映射为准。
