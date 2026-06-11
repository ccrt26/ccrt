# STEP-C：运行入口 Shadow 验证 G2 方案

> 日期：2026-06-09
> 流程编号：F-SCHEDULE + F-DATA + F-GATE
> 阶段门：G0/G2；进入 G3 前必须用户确认
> 目标：让 UnifiedDataSource 使用真实 L2 数据做 shadow diff，但不切日报或深度分析生产入口。

---

## 1. 启动条件

| 条件 | 要求 |
|:-----|:-----|
| STEP-A | 文档索引和边界已清楚 |
| STEP-B | L2 小样本、全量、日增量至少完成到可 shadow 使用 |
| health | `check_d04_health.py` PASS 或仅非阻断 WARN |
| 回滚 | 可关闭 shadow，生产入口仍走旧路径 |

---

## 2. 阶段目标

1. 明确哪些入口只做 shadow，哪些入口保持 BAU。
2. 让 UDS 读取真实 L2 数据形成对照结果。
3. 使用 `run_shadow_diff.py` 或同类脚本产出 diff。
4. 收集差异类型：字段缺失、数值偏差、日期新鲜度、quality_flag、fallback。
5. 不修改生产入口，不改变报告内容。

---

## 3. 允许修改范围

经用户确认进入 G3 后，可在最小范围内修改或运行：

| 类型 | 文件 |
|:-----|:-----|
| UDS shadow | `代码文件/数据/unified_data_source.py` |
| shadow diff | `scripts/run_shadow_diff.py` |
| shadow 日志 | `代码文件/数据/l2_cache/shadow_diff_log.jsonl` |
| health | `scripts/check_d04_health.py` |

---

## 4. 禁止修改范围

| 禁止 | 说明 |
|:-----|:-----|
| 修改 `daily_workflow.py` 生产读取路径 | STEP-C 只做 shadow |
| 修改 `daily_orchestrator.py` 生产调度 | 调度切换属于 STEP-D 后续 |
| 修改 `cached_data_source.py` 正式返回值 | 生产取数保持旧路径 |
| 修改 `runtime_entry_registry.json` 为生产切换 | 入口注册变更需 STEP-D |
| 将 diff WARN 直接升级 BLOCK | 需要观察期和单独策略 |

---

## 5. Shadow Diff 观察维度

| 维度 | 说明 |
|:-----|:-----|
| 覆盖率 | L2 是否能覆盖目标股票、目标日期、目标字段 |
| 数值一致性 | L1/L2 close、volume、turnover 等关键字段差异 |
| 日期新鲜度 | L2 最新日期是否落后 L1 |
| fallback | L2 缺失时是否安全回到 L1/L3 |
| quality_flag | 缺失、降级、异常是否能解释 |
| 性能 | 查询耗时是否适合后续生产评估 |

---

## 6. 验收命令

```bash
python3 scripts/check_d04_health.py --dry-run
python3 scripts/run_shadow_diff.py --dry-run
```

生产入口不变证明：

```bash
git diff -- 代码文件/每日荐股/scripts/daily_workflow.py 代码文件/tools/daily_orchestrator.py 代码文件/lib/cached_data_source.py 00_项目地基/06_调度与运行/runtime_entry_registry.json
```

shadow 日志检查：

```bash
tail -n 20 代码文件/数据/l2_cache/shadow_diff_log.jsonl
```

---

## 7. 通过条件

| 条件 | 标准 |
|:-----|:-----|
| shadow 可运行 | 不影响日报/深度分析 BAU |
| diff 可解释 | 差异按类型归因，不出现静默错读 |
| fallback 可用 | L2 缺失时不阻断旧路径 |
| 日志可追溯 | 每次 shadow 有日期、股票、字段、差异摘要 |
| 连续稳定 | 建议至少 3 个交易日或 3 批样本稳定 |

---

## 8. 回滚方案

| 场景 | 回滚 |
|:-----|:-----|
| UDS shadow 失败 | 关闭 shadow 读取，保留旧入口 |
| L2 缺失严重 | 回到 STEP-B 补数据，不进入 STEP-D |
| diff 不可解释 | 暂停入口评估，补充字段映射和质量标记 |
| 日志异常膨胀 | 限制样本范围或关闭日志写入 |

---

## 9. 下一阶段建议

只有当 shadow diff 连续稳定，并且差异有明确解释和回滚路径后，才建议进入 STEP-D：生产入口切换评估。

