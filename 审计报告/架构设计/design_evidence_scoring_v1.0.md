# 证据等级 → 评分引擎集成 v1.0

> pipeline_stage: complete | finance_confirmed: true
> **日期**: 2026-05-27 | **设计**: 情墨 | **审核**: 腰子
> **关联**: 深度分析_v1.3.md §零.7（接口契约定义）

---

## 一、变更动机

深度分析 v1.3 方法论 §零.7 定义了证据等级(L1-L4)与评分的联动契约，但评分引擎(scores.py)从未读取 events_db.json。当前 S_News 纯基于 CAR5 价格动量，S_SectorTrend 基于五因子模型——事件数据在评分中完全缺席。

本次集成填补这个缺口，实现方法论定义的接口契约。

## 二、接口契约

| 证据等级 | S_News加分 | S_SectorTrend乘数 |
|:--------|:---------|:-------------|
| L1 | +3 | ×1.00 |
| L2 | +1 | ×0.90 |
| L3 | 0 | ×0.75 |
| L4 | 0 | ×0.60 |

数据源：`重点股票/消息面数据/events_db.json`

## 三、设计决策

1. **数据加载在 engine.py**：遵循 sector_info/sector_trend_info 的预加载→传入模式
2. **MAX 聚合**：取该股票所有事件中最高 evidence_level
3. **90天新鲜度窗口**：过期事件不参与评分
4. **向后兼容**：无事件数据时 evidence_mult=1.0, bonus=0，评分不变

## 四、代码变更

### engine.py
- 新增 `load_evidence_levels(db_path)` 函数（~30行）
- main() 中加载 evidence_map 并传入 compute_scores()

### scores.py
- compute_scores() 签名新增 evidence_info=None
- S_SectorTrend 应用 evidence_mult 折扣
- S_News 添加 evidence_bonus（在 CAR5 和 news_bonus 之后）

## 五、Golden Master 保证

当 events_db.json 不存在/无事件/evidence_level 为 null 时，evidence_info=None → 折扣=1.0, 加分=0，与原版评分完全一致。

## 六、风险

- events_db.json 刚部署 evidence_level 字段，大部分事件可能尚无数据 → 安全降级为无折扣
- 关键词匹配可能误标 evidence_level → 仅影响 S_SectorTrend 折扣(最大40%差异)，非否决逻辑

> **版本**: v1.0 | **日期**: 2026-05-27 | pipeline_stage: complete | finance_confirmed: true | implemented: true
> **实现**: 2026-05-27 红结完成编码 | engine.py +31行, scores.py +8行 | Golden Master: PASS (events_db无evidence_level → 评分不变)
