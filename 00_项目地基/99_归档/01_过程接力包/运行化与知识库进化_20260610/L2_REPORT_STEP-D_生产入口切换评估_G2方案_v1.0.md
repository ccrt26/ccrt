# STEP-D：生产入口切换评估 G2 方案

> 日期：2026-06-09
> 流程编号：F-SCHEDULE + F-DATA + F-GATE
> 阶段门：G0/G1/G2；本文件不授权 G3 切换
> 目标：评估日报、深度分析等正式入口是否可以改读新地基，并给出切换、回滚、验收策略。

---

## 1. 启动条件

| 条件 | 要求 |
|:-----|:-----|
| STEP-B | L2 全量和日增量稳定 |
| STEP-C | UDS shadow diff 连续稳定 |
| 业务口径 | 腰子金融口径明确：哪些字段可由 L2 提供，哪些仍以 L1 为准 |
| 技术口径 | 入口切换矩阵、回滚方案、验收命令齐全 |
| 用户确认 | 必须单独确认进入生产切换评估 |

---

## 2. 评估对象

| 入口 | 当前建议 |
|:-----|:---------|
| 日报正式入口 | 暂不直接切；先评估字段级读取 |
| 深度分析入口 | 暂不直接切；先评估历史回溯字段 |
| `daily_workflow.py` | 保持 BAU，候选 shadow-only 参数 |
| `daily_orchestrator.py` | 保持 BAU，候选注册表驱动 |
| `cached_data_source.py` | 保持旧返回，候选内部 shadow 对比 |
| `unified_data_source.py` | 继续 shadow，候选 guarded provider |
| `runtime_entry_registry.json` | 只在最终切换方案中调整 |

---

## 3. 切换策略候选

| 策略 | 说明 | 风险 |
|:-----|:-----|:-----|
| 不切 | 继续旧入口生产，UDS/L2 只做 shadow | 低，收益慢 |
| 字段级 guarded | 仅部分历史字段从 L2 读，失败即回旧路径 | 中低 |
| 入口级 guarded | 日报或深度分析入口启用 UDS provider，保留 fallback | 中 |
| full cutover | 全部改读新地基 | 高，不建议当前阶段 |

当前建议：最多评估“字段级 guarded”，不建议 full cutover。

---

## 4. G1 业务/金融口径待确认

| 问题 | 待确认 |
|:-----|:-------|
| 当日行情 | 是否永远以 L1 为准 |
| 历史 K 线 | L2 与 L3/L1 不一致时如何裁决 |
| 评分历史 | score_history 缺失时是否降级 |
| 质量标记 | quality_flag 为 WARN 时报告是否可发布 |
| 差异阈值 | 价格/成交量/资金流偏差超过多少阻断 |

---

## 5. 必备 G2 输出

正式进入任何 G3 切换前，必须补齐：

1. 入口切换矩阵。
2. 字段级 provider 矩阵。
3. fallback 和 rollback 方案。
4. 金融口径确认。
5. 数据健康和 shadow diff 连续稳定证据。
6. 验收命令和失败判定。
7. 用户确认的暂停点。

---

## 6. 验收命令候选

生产入口 diff：

```bash
git diff -- 代码文件/每日荐股/scripts/daily_workflow.py 代码文件/tools/daily_orchestrator.py 代码文件/lib/cached_data_source.py 代码文件/数据/unified_data_source.py 00_项目地基/06_调度与运行/runtime_entry_registry.json
```

数据健康：

```bash
python3 scripts/check_d04_health.py --strict
```

shadow diff：

```bash
python3 scripts/run_shadow_diff.py --strict
```

闸门观察：

```bash
python3 scripts/check_numeric_source_consistency.py --dry-run
python3 scripts/check_freshness_degradation.py --dry-run
```

---

## 7. 回滚要求

| 对象 | 回滚要求 |
|:-----|:---------|
| 入口代码 | 一键关闭新 provider 或恢复旧路径 |
| 注册表 | 保留切换前 `runtime_entry_registry.json` 备份 |
| 报告产物 | 切换前备份目标日期 MD/sidecar |
| L2 数据 | 切换前 DB 备份可恢复 |
| 闸门策略 | BLOCK 收紧前可恢复 WARN/SKIP |

---

## 8. 结论

STEP-D 是评估阶段，不是实施阶段。

本阶段完成后，如果结论为可切换，也必须另开“生产入口 guarded cutover 实施”G2/G3，并由用户明确确认后执行。

