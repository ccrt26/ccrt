# STEP-B：L2 数据实装 G2 方案

> 日期：2026-06-09
> 流程编号：F-DATA + F-GATE
> 阶段门：G0/G2；进入 G3 前必须用户确认
> 目标：让 `l2_cache.db` 从空 schema 进入可审计、可备份、可 shadow 使用的数据状态。

---

## 1. 前置状态

2026-06-09 只读检查：

| 表 | 行数 |
|:---|----:|
| `financials` | 0 |
| `historical_percentiles` | 0 |
| `kline` | 0 |
| `macro` | 0 |
| `returns` | 0 |
| `risk_metrics` | 0 |
| `score_history` | 0 |

结论：L2 schema 已存在，业务数据未落地。不得把当前 L2 视为生产可用。

---

## 2. 阶段目标

1. 审计现有 DB、schema、脚本、哨兵、备份目录。
2. dry-run 验证构建链路。
3. 先做少量股票、少量日期的小样本写入。
4. 小样本 PASS 后再全量回填。
5. 全量 PASS 后接日增量。
6. 每一步都保留 health、backup、日志和回滚路径。

---

## 3. 允许修改范围

进入 G3 并经用户确认后，允许触碰：

| 类型 | 文件 |
|:-----|:-----|
| 构建脚本 | `scripts/build_l2_cache.py` |
| 增量脚本 | `scripts/update_l2_cache.py` |
| 历史评分 | `scripts/rebuild_score_history.py` |
| 质量标记 | `scripts/sync_quality_flag.py` |
| 健康检查 | `scripts/check_d04_health.py` |
| L2 运行目录 | `代码文件/数据/l2_cache/` |
| 归档输入 | `历史数据/04_原始数据/` 只读 |
| L1 输入 | `代码文件/数据/data_full.json`, `kline_cache`, `fund_flow_cache` 只读 |

---

## 4. 禁止修改范围

| 禁止 | 说明 |
|:-----|:-----|
| 改日报生产入口 | L2 实装不等于入口切换 |
| 改深度分析生产入口 | 需 STEP-D 后另开实施 |
| 改闸门为 BLOCK | 先观察，不收紧 |
| 无备份写全量 | 全量前必须备份当前 DB |
| 无 dry-run 直接写 | 所有写入动作先 dry-run |
| 用 L2 覆盖 L1 当日权威 | L1 仍是当日权威 |

---

## 5. 执行分段

| 分段 | 操作 | 暂停点 |
|:----:|:-----|:-------|
| B0 | 只读审计 DB、schema、脚本参数、last_update | 无 |
| B1 | dry-run 构建 kline / score_history | dry-run FAIL 则暂停 |
| B2 | 小样本写入 2-3 只股票、5-10 个交易日 | 写入前暂停 |
| B3 | 小样本 health、主键、索引、quality_flag 校验 | FAIL 则清样本或恢复备份 |
| B4 | 全量回填 | 全量前暂停 |
| B5 | 日增量接入 | 增量前暂停 |
| B6 | 连续 health 观察 | PASS 后进入 STEP-C |

---

## 6. 验收命令

只读审计：

```bash
python3 scripts/check_d04_health.py --dry-run
```

dry-run 构建：

```bash
python3 scripts/build_l2_cache.py --dry-run
python3 scripts/rebuild_score_history.py --dry-run
python3 scripts/sync_quality_flag.py --table all --dry-run
```

日增量 dry-run：

```bash
python3 scripts/update_l2_cache.py --date YYYY-MM-DD --dry-run
```

SQLite 行数审计：

```bash
python3 -c "import sqlite3; con=sqlite3.connect('代码文件/数据/l2_cache/l2_cache.db'); [print(t, con.execute(f'select count(*) from {t}').fetchone()[0]) for (t,) in con.execute(\"select name from sqlite_master where type='table' order by name\")]; con.close()"
```

---

## 7. 通过条件

| 条件 | 标准 |
|:-----|:-----|
| 小样本通过 | kline/score_history 至少有可解释数据，主键无冲突 |
| health 通过 | `check_d04_health.py` 无 P0 错误 |
| 备份可用 | 写入前后均有可恢复备份 |
| 日增量可跑 | `update_l2_cache.py --dry-run` 和一次受控实跑通过 |
| 不切生产 | 日报、深度分析入口 diff 为空或无生产行为变化 |

---

## 8. 回滚方案

| 场景 | 回滚 |
|:-----|:-----|
| 小样本写入失败 | 恢复写入前 DB 备份，或清理样本表数据 |
| 全量回填失败 | 恢复全量前 DB 备份 |
| 增量失败 | 恢复增量前 DB 备份，并把 last_update 标记为 ERROR |
| health 失败 | 暂停 STEP-C，不允许 UDS 使用真实 L2 |

---

## 9. 下一阶段建议

只有当 B2 小样本、B4 全量、B5 日增量全部 PASS，并且至少一次 health PASS 后，才建议进入 STEP-C：运行入口 shadow 验证。

