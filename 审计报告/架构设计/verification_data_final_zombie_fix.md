# 新安 · 四层验证报告 — data_final僵尸文件修复

**验证日期**: 2026-05-27
**代码等级**: L0
**验证结果**: gate: PASS

---

## 验证清单

| # | 检查项 | 结果 |
|:--|:------|:----:|
| V1 | scoring_engine_v2.py 运行后 data_final.json 存在且有效 | PASS |
| V2 | data_final 所有Code ∈ data_scored passed集合 | PASS (diff=none) |
| V3 | data_final 按 TotalScore 降序排列 | PASS |
| V4 | data_final 股票数 ≤ passed数 | PASS (19=19) |
| V5 | inspect_data_health.py 巡检改善 | PASS (35→36 PASS, 4→3 WARN) |
| V6 | Golden Master: data_scored.json 评分不变 | PASS (未修改输出逻辑) |
| V7 | 历史数据0522/0525/0526/0527修复 | PASS |

## 巡检对比

| 指标 | 修复前 | 修复后 |
|:-----|:------:|:------:|
| PASS | 35 | 36 |
| WARN | 4 | 3 |
| FAIL | 0 | 0 |
| data_final一致性错误 | 4天 | 0天 |

## 剩余WARN（非本次修复范围）

- 0525/0526/0527: scored vs full 股票数不一致（不同管线运行批次，已知问题）
- 0527: snapshot 缺失（当日交易快照尚未生成，C类不可修）

## 判定

**PASS** — data_final僵尸文件问题已根除。剩余WARN为独立问题。
