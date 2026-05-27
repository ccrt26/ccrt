# 架构设计 — 南向资金[THS-SB]接入，补位北向[8]失效

> pipeline_stage: complete | 情墨 v1.0 | 待腰子确认
> 代码等级: L0（桥接+采集）/ L1（评分权重调整）
> 白皮书依据: 规则红线v1.16 §1.1(1+2主备) §1.2(数据源编号) §5.4(文档同步)
> 背景: 北向资金[8]个股日频数据因2024/08政策变更不可得(滞后57天)，需日频替代

---

## 一、需求概述

2024年8月19日起，上交所/深交所停止逐日披露个股北向资金持股明细。现有[8]东方财富API (`RPT_MUTUAL_HOLDSTOCKNORTH_STA`) 仅返回季度快照，最新数据滞后~57天，无法用于日频资金面评分。

经玉夜实测确认：AKShare `stock_hsgt_hist_em(symbol='南向资金')` **日频可用**，最新数据到今日(2026-05-26)，2636/2637行有效。

### 核心收益

| 收益 | 说明 |
|:-----|:-----|
| 补位北向失效 | 南向资金作为外资态度的**反向指标**，日频可用 |
| 资金面评分不再"盲" | 日频资金信号替代季度滞后数据 |
| 零新增依赖 | AKShare已在THS桥接中集成，无需新库 |
| 历史天然齐全 | `stock_hsgt_hist_em` 返回2014年至今全量，无需回填 |

### 南向作为反向指标的逻辑

```
南向净流出(钱去港股) → A股资金面偏紧 → 对个股不利
南向净流入(钱回A股)  → A股资金面改善 → 对个股有利
连续3-5日同向 → 信号增强
```

⚠️ **局限性**：南向≠北向。南向反映的是内地资金跨境行为，不能1:1替代外资持股分析。它补的是"日频资金态度"维度，不是"外资持仓结构"维度。

---

## 二、模块设计

### 2.1 新增文件

无新增文件。全部利用现有模块扩展。

### 2.2 修改文件

| 文件 | 改动 | 行数 | 等级 |
|:-----|:----|:---:|:---:|
| `代码文件/每日荐股/scripts/stock_data_fetcher_ths.py` | 新增 `northbound_flow` action，查询南向+北向资金流 | ~40行 | L0 |
| `代码文件/每日荐股/scripts/modules/external.ps1` | 新增 `Get-SouthboundFlow` 函数，1+2降级路径 | ~35行 | L0 |
| `代码文件/每日荐股/scripts/batch_data_collector.ps1` | 新增南向采集步骤，写入 `data_full.json` | ~15行 | L0 |
| `代码文件/每日荐股/分析逻辑/engine/scores.py` | 北向因子权重[0,+3]→[0,+1]；新增南向信号[0,±2] | ~10行 | **L1** |
| `代码文件/tools/health_check.ps1` | 新增THS桥接连通性检查 | ~15行 | L0 |
| `.claude/agents/玉夜-知识库/01-数据源全景.md` | 更新北向降级链 + 新增南向条目 | ~40行 | M类 |
| `.claude/knowledge/数据字典.md` | 新增[THS-SB]南向资金条目 | ~8行 | M类 |

### 2.3 不修改的文件

- 模拟交易引擎 (`sim_trading.ps1`) — 资金面信号权重微调不改变交易逻辑
- 报告生成 (`gen_daily_brief.py`, `gen_doc.ps1`) — 南向数据写入 `data_full.json`，报告层自动拾取
- 深度分析管线 — 独立数据采集流程，不依赖 `batch_data_collector`
- 必盈[13]/baostock[14]桥接 — 无耦合

---

## 三、接口契约

### 3.1 THS桥接新增 action

```
Action: northbound_flow
调用: python stock_data_fetcher_ths.py northbound_flow [--direction south|north]
返回: JSON数组
```

**南向模式 (`--direction south`)**：
```json
[
  {"date": "2026-05-26", "net_flow": -9.6766, "buy_amount": 782.3588, "sell_amount": 792.0354, "cumulative": 5.374790},
  {"date": "2026-05-22", "net_flow": -64.9365, "buy_amount": 574.0287, "sell_amount": 638.9652, "cumulative": 5.375758},
  ...
]
```

**北向模式 (`--direction north`)**：仅返回历史数据(截止2024-08-16)，标记 `"stale": true`。

### 3.2 PowerShell函数签名

```powershell
function Get-SouthboundFlow {
    param([int]$Days = 5)
    # 返回最近N日南向资金净流向
    # 降级路径: AKShare THS → 缓存[C]
    # 写入字段: SouthboundNetFlow, SouthboundFlow_History
}
```

### 3.3 data_full.json 新增字段

```json
{
  "SouthboundNetFlow": -9.68,           // 最新日南向净流向(亿)
  "SouthboundFlow_History": [-9.68, -64.94, -61.05, ...],  // 近5日序列
  "SouthboundSignal": -1                // 连续方向信号: -1(流出)/0(震荡)/+1(流入)
}
```

### 3.4 数据源降级路径更新

```
现有: Northbound : 东方财富[8] → 缓存[C]
更新: Northbound : 东方财富[8](季度持股) → 缓存[C]  // 保留，仅季度结构参考
新增: Southbound : AKShare THS → 缓存[C]           // 日频，资金态度代理
```

### 3.5 评分引擎权重调整 (scores.py)

```python
# 现有 (v2.8): 北向季度持股 → 资金面评分
if nb_shares_ratio > 5: money += 3      # → 改为 += 1 (降权，季度滞后)
elif nb_shares_ratio > 2: money += 2    # → 改为 += 1
elif nb_shares_ratio > 0.5: money += 1  # → 保留

# 新增: 南向日频资金信号
if southbound_signal < 0 and abs(southbound_net_5d) > 50:
    money -= 2   # 连续南下>50亿，资金面偏空
elif southbound_signal > 0 and southbound_net_5d > 30:
    money += 2   # 连续北上>30亿，资金面偏多
```

---

## 四、技术决策与权衡

### 4.1 南向替代北向 vs. 仅降权北向

| 选项 | 优点 | 缺点 | 选择 |
|:-----|:-----|:-----|:---:|
| 仅降权北向 | 零开发 | 资金面评分仍然"盲" | ❌ |
| 南向替代北向 | 日频信号、零新依赖 | 反向指标、非直接替代 | ✅ |
| 多源资金面(南向+两融+主力) | 信号最全 | 复杂度高 | 长期方向 |

**决策**: 南向补位+北向降权。这是最小变更、最大收益的方案。

### 4.2 THS桥接 vs. 新独立Python脚本

| 选项 | 优点 | 缺点 | 选择 |
|:-----|:-----|:-----|:---:|
| THS桥接扩展 | 复用现有 `Invoke-ThsFallback` 机制 | 函数稍长(~40行) | ✅ |
| 独立fetcher | 模块隔离 | 重复框架代码、增加维护面 | ❌ |

**决策**: 扩展THS桥接。AKShare已在 `stock_data_fetcher_ths.py` 中集成，添加一个action比新建文件更简洁。

### 4.3 南向作为独立采集步骤 vs. 北向采集的fallback

| 选项 | 优点 | 缺点 | 选择 |
|:-----|:-----|:-----|:---:|
| 独立步骤 | 清晰、可单独开关 | 多一次API调用 | ✅ |
| 北向fallback | 节省调用 | 混淆了"替代"和"降级"的概念 | ❌ |

**决策**: 独立采集步骤。语义清晰：北向拿季度结构，南向拿日频态度，两者并存。

---

## 五、缓存策略

| 数据 | TTL | 理由 |
|:-----|:---:|:-----|
| 南向资金日频 | **24h** | 盘后采集一次，下个交易日收盘前不变 |
| 南向全量历史 | **168h(7d)** | 历史不变，仅增量需刷新 |
| 北向季度持股 | **720h(30d)** | 季频数据，已有长TTL |

缓存Key: `SouthboundFlow_${Days}`, `SouthboundHistory`

---

## 六、影响范围评估

| 影响维度 | 评估 |
|:--------|:-----|
| 数据管线 | 低。新增1个采集步骤，不改变现有步骤 |
| 评分引擎 | **中(L1)**。权重微调，需要Golden Master diff验证 |
| 报告生成 | 极低。`data_full.json` 新增字段，报告层自动拾取 |
| 模拟交易 | 极低。资金面评分变化≤3分，不触发开仓/清仓阈值 |
| 红线合规 | **正向**。北向[8]从"过期数据参与评分"变为"仅结构参考+标注时效" |
| 现有fetcher | 无耦合。THS桥接扩展不影响现有action |

---

## 七、风险与缓解

| 风险 | 概率 | 影响 | 缓解措施 |
|:-----|:---:|:---:|:-----|
| AKShare南向接口未来也被封 | 低 | 回到当前状态(无日频外资信号) | 两融[12]+主力资金[9]作为资金面兜底 |
| 南向信号解读错误(反向指标误用) | 中 | 资金面评分偏差 | 文档明确标注"反向指标"；权重控制在±2(远低于主力资金的±7) |
| 批量采集超时(AKShare全量历史~2600行) | 低 | 单次采集慢(~3s) | 仅取最近60日用于日频判断；全量历史仅首次缓存 |
| AH股同步暴跌时南向信号失真 | 中 | 南向和A股同向下跌(非反向)，信号方向错误 | 评分引擎增加判断：当沪深300日跌幅>2%且恒指日跌幅>2%时，南向信号暂停使用 |

---

## 八、玉夜巡检新增项

| 检查项 | 方法 | 级别 | 触发条件 |
|:------|:----|:---:|:--------|
| AKShare THS桥接 | `python stock_data_fetcher_ths.py northbound_flow --direction south` | P3 | 返回非JSON或无data字段 |
| 南向数据新鲜度 | `max(date)` 与今日比较 | P2 | 延迟>2个交易日 |
| 南向全量行数 | 返回行数 >= 2000 | P3 | 首次检查后记录基线 |

---

## 九、需求→代码核对清单

> 情墨+腰子共同勾签后放行（闸门1a）

| # | 需求 | 实现文件 | 情墨✓ | 腰子✓ |
|:-:|:-----|:--------|:----:|:----:|
| 1 | THS桥接新增 `northbound_flow` action | `stock_data_fetcher_ths.py` | ✅ | ✅ |
| 2 | PowerShell `Get-SouthboundFlow` 函数 | `external.ps1` | ✅ | ✅ |
| 3 | 批量采集新增南向步骤 | `batch_data_collector.ps1` | ✅ | ✅ |
| 4 | `data_full.json` 新增南向字段 | `batch_data_collector.ps1` | ✅ | ✅ |
| 5 | 北向季度数据评分降权 [0,+3]→[0,+1] | `scores.py` | ✅ | ✅ |
| 6 | 南向日频信号接入评分 [0,±2] | `scores.py` | ✅ | ✅ |
| 7 | 健康检查新增THS桥接项 | `health_check.ps1` | ✅ | ✅ |
| 8 | 数据源全景更新降级链 | `01-数据源全景.md` | ✅ | ✅ |
| 9 | 数据字典新增[THS-SB]条目 | `数据字典.md` | ✅ | ✅ |
| 10 | 南向缓存策略(TTL 24h/168h) | `core.ps1` (Save-DataCache) | ✅ | ✅ |
| 11 | AH股同步暴跌暂停南向信号 | `scores.py` (流金追加) | ✅ | ✅ |
