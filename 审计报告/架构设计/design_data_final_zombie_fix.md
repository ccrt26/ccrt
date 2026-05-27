# 设计文档：data_final僵尸文件修复

**设计日期**: 2026-05-27
**设计者**: 情墨
pipeline_stage: complete
finance_confirmed: true
**代码等级**: L0（工具/数据层，红结自查+新安常规）

---

## 1. 问题诊断

### 1.1 现象

玉夜巡检发现4天WARN（0522/0525/0526/0527），共同模式：
- `data_final`(42只) 与 `data_scored`(19只) 完全不匹配
- final中的27只股票不在scored中
- `data_final` 0522-0527四天文件内容**完全相同**（42只股票不变）

### 1.2 根因

`data_final.json` 是**僵尸文件**。全项目检索确认：**没有任何脚本生成 `data_final.json`**。

数据管线实际流程：
```
batch_data_collector.ps1 → data_full.json    (53只)
scoring_engine_v2.py     → data_scored.json   (19只)
                           data_final.json    (无人生成！)
archive_data.ps1         → 盲目归档三个文件到历史数据
```

0522年某次手动操作或已删除的旧脚本生成了一份 `data_final.json`（42只），此后该文件未被任何代码更新，每天被 `archive_data.ps1` 原样复制到历史数据目录，与当天新生成的 `data_scored.json` 产生矛盾。

`data_final_optimized.json` 同理——无代码生成，仅由巡检脚本的auto-repair从 `data_final` 复制。

### 1.3 影响范围

- `archive_data.ps1:118` — 归档 data_final.json（盲拷僵尸文件）
- `inspect_data_health.py:28` — 将 data_final 和 data_final_optimized 列为必选文件
- `gen_daily_html.ps1:26` — 已使用 `data_scored.json` 作为默认输入（无影响）
- `run_daily_eval.ps1:16` — 使用 `data_scored.json`（无影响）
- 审计脚本 — 检查 data_final 存在性（检查到僵尸文件也无意义）

## 2. 修复方案

### 2.1 策略

**在管线中重新生成 `data_final.json`**，而非删除它。

理由：
- `data_final` 语义上有价值：从 scored 中提取 passed 股票，按 TotalScore 排序，作为"最终推荐列表"的稳定入口
- 多个下游脚本引用此文件名，删除需改动更多文件
- 生成逻辑已在 `inspect_data_health.py:repair_data_final()` 中实现，可直接复用

### 2.2 变更清单

| # | 文件 | 变更 | 等级 |
|:--|:-----|:-----|:----:|
| 1 | `engine/__init__.py` | 新增 FINAL_FILE 路径定义 | L0 |
| 1a | `engine/engine.py` | 新增：评分完成后输出 `data_final.json`（passed股票按分排序）+ 导入 FINAL_FILE | L0 |
| 2 | `archive_data.ps1` | 无需修改（data_final_optimized 本不在归档列表，data_final 继续归档） | — |
| 3 | `inspect_data_health.py` | `data_final_optimized` 从必选→可选 | L0 |

### 2.3 设计决策

- **在哪生成**：`scoring_engine_v2.py` —— 评分引擎是 data_scored 的产出者，在同一执行中产出 data_final 可保证原子一致性
- **生成内容**：passed 股票，按 TotalScore 降序，包含 FINAL_KEYS（PE/MktCap/Name/TurnoverRate/Amplitude/TotalScore/S_News/S_Tech/Industry/S_Base/ChangePct/S_Fund/Price/Volume/S_Risk/Code/S_Money）
- **data_final_optimized**：不再生成。历史上其内容=data_final的副本，无独立价值

## 3. 需求→代码核对清单

| 需求 | 实现 | 状态 |
|:-----|:-----|:----:|
| 每次评分后生成 fresh data_final | scoring_engine_v2.py 新增输出 | 待实现 |
| data_final 与 data_scored 原子一致 | 同一引擎执行中生成 | 待实现 |
| 僵尸 data_final_optimized 停止归档 | archive_data.ps1 删除对应行 | 待实现 |
| 巡检不再为 optimized 报 WARN | inspect_data_health.py 改为可选 | 待实现 |
| 已有历史数据的4天WARN修复 | 巡检脚本的auto-repair已处理0526/0527；0522/0525需手动触发修复 | 待确认 |

## 4. 验证方法

1. 运行 `scoring_engine_v2.py` → 确认 `data_final.json` 已生成
2. 确认 `data_final.json` 中的所有股票 Code ∈ `data_scored.json` 中 passed 股票集合
3. 确认 `data_final.json` 股票数 ≤ data_scored 的 passed 数
4. 运行 `inspect_data_health.py` → 确认当前及以后日期PASS
5. Golden Master: 现有 `data_scored.json` 内容不受影响

---

**情墨签认**: ✓
**腰子签认**: 待
