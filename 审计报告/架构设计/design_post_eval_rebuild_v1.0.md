# 每日荐股后评估系统重建 — 架构设计

> **pipeline_stage**: complete | **版本**: v1.0 | **日期**: 2026-05-29
> **设计人**: 情墨 | **触发**: 腰子全团讨论结论——后评估框架正确、执行断裂，需从零重建日常化评估

---

## 一、问题诊断摘要

| # | 问题 | 严重度 | 根因 |
|:--|:-----|:------|:-----|
| P0-1 | eval_v2.2_v1.4.py硬编码日期+过期维度 | 阻断 | 实验性脚本未日常化 |
| P0-2 | 评估结果未驱动参数优化 | 阻断 | 无自动化反馈链路 |
| P1-1 | 缺少T+3/T+5多窗口评估 | 高 | backfill已有能力但eval未调用 |
| P1-2 | v3.0新指标(C8/档位/相位折扣)无评估代码 | 高 | 白皮书与代码脱节 |
| P2-1 | records.csv仅16条，数据积累严重不足 | 中 | 自动化未运行 |

## 二、重构决策矩阵

| 维度 | 评分 | 理由 |
|:-----|:----:|:-----|
| 问题严重度 | 5 | 评估断裂=评分体系无反馈信号=策略在盲飞 |
| 发生频率 | 5 | 每日评估都应该运行，实际从未正常运行 |
| 扩散风险 | 4 | 影响评分优化、否决校准、策略迭代全部下游 |
| 修复成本 | 3 | 约半天（新建1个核心脚本+改2个文件） |
| 验证难度 | 4 | 一行命令验证：对比新旧eval输出一致性 |

**总分** = 5×0.35 + 5×0.25 + 4×0.20 + 3×0.15 + 4×0.05 = 1.75 + 1.25 + 0.80 + 0.45 + 0.20 = **4.45** → **立即重构**

## 三、模块归属与代码分级

### 3.1 归属

| 文件 | 归属层 | 归属模块 | 等级 | 理由 |
|:-----|:------|:--------|:----:|:-----|
| `post_eval_engine.py` (新建) | 计算层 | 后评估引擎 | **L1** | 策略/评分相关，涉及评分有效性判断 |
| `run_daily_eval.py` (重写) | 工具层 | 调度入口 | **L0** | 纯调度脚本，无业务逻辑 |
| `scoring_engine_v2.py` (修改) | 计算层 | 评分引擎 | **L1** | 补充v3.0字段到落库输出 |
| `eval_v2.2_v1.4.py` (废弃) | — | — | — | 归档至历史数据/ |

### 3.2 分级理由

post_eval_engine.py 为 L1 而非 L0：包含评分区分度计算、维度误判率判定、否决有效度诊断——这些直接影响策略参数调整决策。需情墨复审+新安全量测试。

run_daily_eval.py 为 L0：仅做文件存在性检查+subprocess调用+日期参数传递，零业务逻辑。

## 四、文件变更计划

### 新建文件

| 文件 | 行数估算 | 功能 |
|:-----|:-------|:-----|
| `代码文件/每日荐股/分析逻辑/post_eval_engine.py` | ~350行 | 核心评估引擎，日期参数化，对齐v1.6白皮书+v3.0评分 |

### 修改文件

| 文件 | 修改量 | 内容 |
|:-----|:------|:-----|
| `代码文件/每日荐股/scripts/run_daily_eval.py` | ~30行重写 | 调用post_eval_engine替代eval_v2.2_v1.4 |
| `代码文件/每日荐股/分析逻辑/scoring_engine_v2.py` | ~15行新增 | score_history.jsonl补充tier/c8_blocked/phase_disc/veto_reason字段 |

### 废弃文件

| 文件 | 处理 |
|:-----|:-----|
| `代码文件/每日荐股/分析逻辑/eval_v2.2_v1.4.py` | 归档到`历史数据/临时回溯/` |

## 五、接口契约

### 5.1 post_eval_engine.py

**输入**:
```
--date YYYY-MM-DD           # 被评估的荐股日期(T日)
--data-dir PATH             # 数据目录(默认 代码文件/数据/)
--output-dir PATH           # 输出目录(默认 每日荐股/评估报告/)
--no-backfill               # 跳过backfill(已回填过时使用)
```

**数据读取**:
| 数据 | 来源 | 格式 |
|:-----|:-----|:-----|
| T日评分记录 | score_history.jsonl (筛选date=T) | JSONL |
| T+N收益 | score_history.jsonl (ret_t1/t3/t5字段) | JSONL |
| T日否决记录 | score_history.jsonl (筛选date=T, veto_reason非空) | JSONL |
| T日全市场数据 | data_full.json 或 行情API | JSON |
| 历史records | records.csv | CSV |

**输出**:
| 输出 | 路径 | 格式 |
|:-----|:-----|:-----|
| 评估JSON | 每日荐股/评估报告/eval_result_YYYYMMDD.json | JSON |
| records追加 | 每日荐股/评估报告/records.csv | CSV追加 |
| summary追加 | 每日荐股/评估报告/summary.csv | CSV追加 |

### 5.2 eval_result JSON Schema

```json
{
  "meta": {
    "eval_date": "2026-05-29", "report_date": "2026-05-28",
    "generated_at": "2026-05-29T19:00:00"
  },
  "core_metrics": {
    "total_recs": 8, "wins": 4, "losses": 4, "untraded": 0,
    "win_rate": 50.0, "floating_benchmark": 55.0, "benchmark_status": "未达标",
    "profit_loss_ratio": 1.5, "portfolio_return": 0.8,
    "hs300_return": 0.3, "excess_return": 0.5,
    "score_distinction_70": 15.0, "spearman_rho": 0.25
  },
  "v30_metrics": {
    "c8_blocked_count": 2, "c8_correct_rate": 50.0, "c8_false_kill_rate": 50.0,
    "a_tier_fill_rate": 40.0, "a_tier_win_rate": 66.7, "non_a_tier_win_rate": 40.0,
    "phase_discount": {
      "tech": "effective", "money": "effective", "news": "needs_review"
    }
  },
  "dimension_misjudge": {
    "tech": {"rate": 15.0, "total": 5, "misjudged": 1},
    "money": {"rate": 20.0, "total": 5, "misjudged": 1},
    "sector": {"rate": 10.0, "total": 5, "misjudged": 0},
    "news": {"rate": 25.0, "total": 4, "misjudged": 1}
  },
  "veto_analysis": {
    "veto_effectiveness": 20.0, "veto_win_rate": 30.0,
    "miskill_rate": 10.0, "miskill_count": 1
  },
  "dimension_corr": {
    "总分": 0.25, "技术": 0.30, "资金": 0.15,
    "基本面": 0.05, "消息": -0.10, "板块趋势": 0.20
  },
  "alerts": [
    {"level": "L1", "indicator": "win_rate", "value": 12.5, "threshold": 55.0, "action": "胜率严重低于浮动基准"},
    {"level": "L2", "indicator": "spearman", "value": 0.15, "trend": "declining", "action": "评分区分度连续下降"}
  ],
  "param_suggestions": [
    {"param": "C8阈值", "current": ">7%", "suggested": ">8%", "confidence": "中", "reason": "C8误杀率50%偏高"}
  ],
  "per_stock": [
    {
      "code": "603501", "name": "豪威集团", "score": 79.0,
      "tier": "B", "c8_blocked": false, "phase": "主升调整",
      "ret_t1": -2.34, "ret_t3": null, "ret_t5": null,
      "misjudge_dim": null, "misjudge_subtype": null
    }
  ]
}
```

### 5.3 scoring_engine_v2.py 新增输出字段

在 score_history.jsonl 每行新增（向后兼容，缺失时eval引擎用默认值）:

| 字段 | 类型 | 说明 | 默认值 |
|:-----|:----|:-----|:------|
| `tier` | string | A/B/C档 | "C" |
| `c8_blocked` | bool | C8是否拦截 | false |
| `phase_discount` | float | 应用的相位折扣系数 | 1.0 |
| `rating` | string | 评级(推荐/观察) | "观察" |
| `veto_reason` | string | 否决原因(空=未被否决) | "" |
| `market_stage` | string | T日市场阶段 | "" |

### 5.4 records.csv 新增字段

| 字段 | 白皮书引用 |
|:-----|:----------|
| `tier` | v1.6 §6.1 |
| `c8_blocked` | v1.6 §6.1 |
| `phase_discount_impact` | v1.6 §6.1 |
| `ret_t3`, `ret_t5` | v1.6 §6.3 |

## 六、数据流设计

```
N日 20:00 (daily模式)
  scoring_engine_v2.py → score_history.jsonl (含新字段tier/c8/phase_disc/veto)
                       → data_scored.json

N+1日 19:00 (eval模式)
  daily_workflow.py --mode eval
    ├── backfill_returns.py          # 回填ret_t1/t3/t5
    └── run_daily_eval.py --date N
        └── post_eval_engine.py --date N
            ├── 读取 score_history.jsonl (筛选date=N)
            ├── 读取 records.csv (历史对比)
            ├── 计算全部v1.6指标
            ├── 输出 eval_result_N.json
            ├── 追加 records.csv
            └── 追加 summary.csv
```

## 七、与现有系统的集成

### 7.1 不改变现有接口

- `daily_workflow.py --mode eval` 调用链不变
- `backfill_returns.py` 不变（已完善）
- `scoring_engine_v2.py` 仅新增输出字段，不改变评分逻辑
- `records.csv` / `summary.csv` 格式向后兼容（新增字段追加在末尾）

### 7.2 不引入新依赖

全部使用标准库+已有库（json, csv, os, subprocess, argparse, math/statistics）。

## 八、Token影响评估

> CLAUDE.md §七.2 ③要求：情墨设计文档必含Token影响评估

| 维度 | 变更前 | 变更后 | 影响 |
|:-----|:------|:-----|:----:|
| **AI读取后评估** | 需读取~1000行eval脚本+手工解读CSV | 读取~50行eval_result JSON摘要 | **减少95%** |
| **参数调整决策** | 腰子手动检查CSV→人工判断 | eval_result含param_suggestions→AI读取JSON即可决策 | **减少80%** |
| **调试/排错** | 需阅读完整eval脚本理解逻辑 | JSON输出自描述，直接定位异常指标 | **减少70%** |
| **每日评估触发** | 无自动化，手工运行 | workflow自动调度，AI仅在alert触发时介入 | **日常零Token** |
| **输出模式** | 970行HTML（硬编码样式+数据） | 结构化JSON（<200行），下游按需消费 | **体积降80%** |

**结论**: 本设计是Token净减方案。评估从"AI手工解读"变为"脚本自动产出结构化结果"，AI仅在有L1/L2报警时介入。

## 九、实施计划

### Phase 1: 核心引擎（红结本次实现）
1. 新建 `post_eval_engine.py` — 核心评估逻辑
2. 重写 `run_daily_eval.py` — 调度入口
3. 修改 `scoring_engine_v2.py` — 补充落库字段
4. 归档 `eval_v2.2_v1.4.py`

### Phase 2: 后续优化（单独任务）
5. 浮动基准接入全市场实时数据
6. L1/L2/L3三级报警自动响应
7. 子因子IC分析（需≥3000条数据积累后激活）
8. 参数联动分析（协方差）

## 十、风险与回退

### 风险
- **数据兼容**: 旧score_history.jsonl缺少新字段 → eval引擎用默认值fallback，不阻断
- **性能**: 评估计算<1秒（164条→遍历+统计），无性能风险

### 回退方案
- 归档的eval_v2.2_v1.4.py保留，如新引擎有误可临时切换
- post_eval_engine.py输出JSON同时保留CSV兼容，旧CSV不变
- rollback步骤: `git revert` + 恢复run_daily_eval.py旧版即可

## 十一、反模式检查

| 反模式 | 触发? | 说明 |
|:-------|:-----:|:-----|
| AP-01 上帝模块 | 否 | 单一职责：评估计算，不混入数据采集/报告生成 |
| AP-02 硬编码路径 | 否 | 全部通过--data-dir参数或相对ROOT计算 |
| AP-03 配置散落 | 否 | 指标阈值集中在脚本顶部常量区 |
| AP-04 静默失败 | 否 | 所有异常写stderr+返回非零exit code |
| AP-05 跨层直接调用 | 否 | 仅通过run_daily_eval调度，不跨层 |
| AP-06 循环依赖 | 否 | 评估引擎→读取score_history.jsonl→无反向依赖 |
| AP-07 重复代码 | 否 | 单一评估引擎，不复用旧eval脚本 |

## 十二、需求→代码核对清单

| 编号 | 检查项 | 白皮书/红线条款 | 情墨勾 | 腰子勾 |
|:----:|:------|:-------------|:-----:|:-----:|
| R1 | 评估指标对齐v1.6白皮书§1.2核心指标列表 | 白皮书v1.6 §1.2 | ☐ | ☐ |
| R2 | 评分维度对齐v3.0(技术20/资金20/消息15/板块20) | 白皮书v3.0 §十九 | ☐ | ☐ |
| R3 | C8拦截/A档席位/相位折扣三维指标完整 | 白皮书v1.6 §3.6/§4.1.4 | ☐ | ☐ |
| R4 | 浮动基准五档(强普涨/普涨/震荡/普跌/强普跌) | 白皮书v1.6 §7.5.2 | ☐ | ☐ |
| R5 | T+1/T+3/T+5多窗口收益评估 | 白皮书v1.6 §6.3 | ☐ | ☐ |
| R6 | 否决有效度三组对照(推荐/否决/全市场) | 白皮书v1.6 §4.4 | ☐ | ☐ |
| R7 | L1阈值报警+L2趋势预判 | 白皮书v1.6 §5.2 | ☐ | ☐ |
| R8 | 参数校准建议自动产出 | 白皮书v1.6 §5.1 | ☐ | ☐ |
| R9 | 数据源1+2架构完整（eval数据来自score_history+CachedDataSource） | 红线§1.2 | ☐ | ☐ |
| R10 | 不改变评分逻辑/不引入新依赖/单文件≤500行 | 红线§9.2 | ☐ | ☐ |

---

> 设计完成。闸门1a：提请腰子确认金融逻辑；闸门1b：提请新安+旧影技术审查。
