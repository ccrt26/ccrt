# 模拟交易引擎 v1.7 — 架构设计

> **pipeline_stage**: complete | **日期**: 2026-05-29 | **设计者**: 情墨

---

## 变更概述

三项变更，按数据流从底层到上层：

```
09:25 集合竞价 → 09:35 引擎运行
                      │
  ① quote_engine.py   ← 行情获取加退避重试（堵不如等）
                      │
  ② sim_trading.py    ← 入场价记录影子基准（不改变执行）
                      │
  ③ enrich_trades.py  ← 交易×事件×情绪三维关联（事后批处理）
```

---

## ① 行情获取退避重试

### 影响文件
`模拟交易/共享模块/quote_engine.py` (L1)

### 当前逻辑
```
get_quote_map() → fetch_tencent → 失败 → fetch_sina → 失败 → load_cache → 返回空
```
单次尝试，失败即降级。

### 新逻辑
```
get_quote_map_with_retry(codes, deadline_str="09:45")
  ├─ attempt 1: fetch_tencent (timeout=5s)
  │   └─ 成功 → 返回
  ├─ attempt 2: fetch_sina (timeout=5s)
  │   └─ 成功 → 返回
  ├─ attempt 3 (等15s): fetch_tencent (timeout=5s)
  │   └─ 成功 → 返回
  ├─ attempt 4 (等30s): fetch_sina (timeout=5s)
  │   └─ 成功 → 返回
  ├─ attempt 5+ (每60s): 交替重试 [1]→[1B]
  │   └─ ...
  └─ 超过deadline → load_cache[C] 兜底
```

### 接口契约
```python
# 不变（向后兼容）
get_quote_map(stock_list, cache_file, sim_dir) -> dict

# 新增（引擎调用此函数替代 get_quote_map）
get_quote_map_with_retry(stock_list, cache_file, sim_dir, deadline_str="09:45") -> dict
# 返回格式与 get_quote_map 完全一致 {"Quotes": {...}, "Source": "..."}
# source 标注重试次数，如 "腾讯行情[1]-retry2"
```

### 设计要点
- 新增函数，不修改原有 `get_quote_map`——保持向后兼容，每日荐股赛道不受影响
- deadline 默认 09:45，可通过参数覆盖
- 每次API调用间隔 >= 0.3s（玉夜铁律），重试间隔远大于此
- sim_trading.py 调用处从 `get_quote_map()` 改为 `get_quote_map_with_retry()`

---

## ② 影子基准（Shadow Benchmark）

### 影响文件
`模拟交易/交易引擎/sim_trading.py` (L2)

### 原理
每笔开仓记录"如果用昨日收盘价入场"的理论成本，平仓时计算理论PnL。不改变实际交易执行。

### 数据结构变更

**positions.json 新增字段：**
```json
{
  "601689": {
    "AvgCost": 72.09,
    "ShadowEntryPrice": 71.50,
    "UnrealizedPnL": -48.00,
    "ShadowUnrealizedPnL": 660.00
  }
}
```

**snapshot 新增字段：**
```json
{
  "StockDetails": [{
    "UnrealizedPnL": -48.00,
    "ShadowUnrealizedPnL": 660.00
  }]
}
```

**perf_summary.json 新增汇总：**
```json
{
  "ShadowBenchmark": {
    "TotalRealUnrealizedPnL": 8171.00,
    "TotalShadowUnrealizedPnL": 9200.00,
    "DeltaNote": "影子基准正=昨日收盘入场更优(开盘正向跳空)，负=开盘入场更优"
  }
}
```

**transactions.csv 新增2列：** `shadow_entry_price`, `shadow_realized_pnl`（仅SELL行有值）

### 代码改动点（sim_trading.py）
- 开仓段（约L587-598）：记录 `quote["PrevClose"]` 到 `ShadowEntryPrice`
- 平仓段（约L430-453）：计算 `shadow_realized_pnl`
- 快照生成（约L690-702）：补 `ShadowUnrealizedPnL`
- perf_summary 更新：新增 `ShadowBenchmark` 汇总

### 向后兼容
- 旧持仓无 ShadowEntryPrice → 首次运行时标注 null，仅新开仓写入
- transactions.csv 新增列在末尾 → 旧解析器只读前N列不受影响

---

## ③ 跨角色数据联动

### 影响文件
新增 `模拟交易/分析/enrich_trades.py` (L0)

### 设计思路
事后批处理，不侵入引擎实时路径。每周运行一次，消费交易流水 + 事件数据，产出富化视图。

### 数据流
```
transactions.csv ─────┐
                       ├─→ enrich_trades.py ─→ trade_context.json
events_db.json ────────┤    (匹配±3日窗口)
宏观情绪标注 ──────────┘    (山猫手动标注字段，先占位)
```

### trade_context.json schema
```json
{
  "generated_at": "2026-06-01T20:00:00",
  "trades": [
    {
      "date": "20260522",
      "code": "600114",
      "action": "BUY",
      "reason": "开仓_看多_健康",
      "price": 35.19,
      "events_window": {
        "start": "20260519",
        "end": "20260525",
        "events": [
          {
            "date": "20260521",
            "category": "公告/业绩预告",
            "impact_score": 3,
            "direction": "positive",
            "summary": "一季度净利润同比增长45%"
          }
        ]
      },
      "macro_context": {
        "market_sentiment": null,
        "csi300_direction": null,
        "annotated_by": null,
        "annotated_at": null
      }
    }
  ]
}
```

### 事件匹配规则
- 信鸽 events_db.json 按 code + date 匹配
- 窗口：交易日前3日 → 后3日（共7日）
- 过滤：impact_score >= 2 或 P0标记的事件
- 去重：同一天同类别事件合并

### 宏观标注
山猫手动字段，先留 schema 占位。数据积累到20个交易日后由山猫批量回填。

---

## 模块分级与影响范围

| 变更 | 文件 | 等级 | 行数估算 | 风险 |
|:-----|:-----|:----:|:-------:|:----:|
| 退避重试 | quote_engine.py | L1 | +50行 | 低：新增函数，不改现有逻辑 |
| 影子基准 | sim_trading.py | L2 | +30行 | 低：只加字段，不改变执行路径 |
| 数据联动 | enrich_trades.py | L0(新) | ~100行 | 低：批处理脚本，不侵入实时引擎 |
| Schema变更 | positions/snapshot/perf | L2 | +6字段 | 中：需向后兼容旧数据 |

---

## Token影响评估

| 项目 | 评估 |
|:-----|:-----|
| 新增模板/提示词体积 | 无新增模板，无Agent调用变化 |
| API调用模式变化 | quote_engine 重试增加API调用次数（拥堵时2-4次），但每次调用数据量不变 |
| 输出模式变化 | snapshot/perf_summary 各增加 ~200 bytes，可忽略 |
| 总体 | 无显著Token影响 |

---

## 需求→代码核对清单

- [ ] quote_engine.py: `get_quote_map_with_retry()` 存在，deadline参数可用
- [ ] sim_trading.py 开仓段: ShadowEntryPrice 写入 positions
- [ ] sim_trading.py 平仓段: shadow_realized_pnl 写入 transactions
- [ ] sim_trading.py 快照段: ShadowUnrealizedPnL 写入 snapshot
- [ ] perf_summary.json: ShadowBenchmark 汇总块
- [ ] enrich_trades.py: 可独立运行，消费 transactions.csv + events_db.json
- [ ] 09:45 deadline 硬截止，超时走缓存[C]兜底
- [ ] API调用间隔 >= 0.3s
- [ ] 向后兼容：旧持仓 ShadowEntryPrice=null 不报错
