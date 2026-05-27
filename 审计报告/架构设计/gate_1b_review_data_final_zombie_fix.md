# 新安 · 架构审查报告 — data_final僵尸文件修复

**审查日期**: 2026-05-27
**审查级别**: L0（工具/数据层）
**审查结果**: gate: PASS

---

## 变更影响分析

| 文件 | 变更类型 | 风险 |
|:-----|:---------|:----:|
| `scoring_engine_v2.py` | 新增输出 data_final.json | 低 — 只增不减 |
| `archive_data.ps1` | 删1行(optimized归档) | 低 — 减少盲拷 |
| `inspect_data_health.py` | optimized必选→可选 | 低 — 放宽约束 |

## 架构合规

- [x] 不改变评分/排序/否决/交易逻辑
- [x] 不改变数据接口格式
- [x] 不新增跨模块依赖
- [x] 符合L0代码等级
- [x] 现有 data_scored.json 输出不受影响

## 回归风险

- 核心链路(data_full→data_scored→report)不受影响
- 唯一影响：scoring_engine_v2.py 多输出一个文件
- 下游消费者(gen_daily_html, run_daily_eval)已使用 data_scored.json

## 判定

**PASS** — 变更范围小、风险低、无架构违规。

## 验证要求（阶段⑤）

1. scoring_engine_v2.py 运行后 data_final.json 存在且有效
2. data_final 所有Code ∈ data_scored passed集合
3. inspect_data_health.py 运行无新增WARN
4. 现有 data_scored.json 内容Golden Master一致（评分/排序不变）
