# 架构设计 — 深度分析方法论 v1.3 → v1.4（Tushare全量数据集成）

> pipeline_stage: complete | 情墨 v1.0 | 2026-05-28
> 代码等级: M类（方法论文档+command更新）+ L0（数据存储+巡检工具）
> 前置: Tushare Pro 15个API全部接入完成

---

## 一、需求概述

Tushare Pro 15个API接入后，深度分析方法论需要升级以：
1. 数据源引用更新（[tushare]替换多处旧源）
2. 新增3个风险维度的分析子节（筹码/质押/解禁）
3. 新增2个财务维度的分析子节（主营构成/业绩预告预期差）
4. 增强资金面分析粒度（四档资金+北向+大宗）
5. 自检清单18→24条

同时需要建立Tushare数据的历史沉淀和巡检机制。

## 二、变更清单

### A. 方法论文件

| 文件 | 变更 | 类型 |
|:-----|:----|:---:|
| `重点股票/深度分析/深度分析逻辑/深度分析_v1.4.md` | 新建（基于v1.3+5子节+3自检+数据源更新） | M类 |
| `.claude/commands/深度分析.md` | 版本引用更新 v1.3→v1.4 | M类 |
| `CLAUDE.md` | 白皮书版本号更新 | M类 |

### B. 数据工程（玉夜）

| 文件 | 变更 | 类型 |
|:-----|:----|:---:|
| `代码文件/tools/tushare_history_sync.py` | 新建 — 历史数据沉淀脚本 | L0 |
| `代码文件/tools/tushare_health_check.py` | 新建 — API巡检脚本 | L0 |
| `代码文件/数据/tushare/` | 新建目录 — 历史数据存储 | L0 |

### C. 不修改的文件

- 评分引擎(scores.py) — 权重调整暂不涉及代码
- 桥接脚本 — 已完成
- 报告生成 — 数据经data_full.json流入

## 三、数据存储方案（玉夜设计）

### 3.1 双层存储架构

```
Layer 1: 热缓存 (已有) — core.ps1 data_cache/
  TTL: 行情1h/K线24h/财务168h/资金流24h
  用途: 当日管线快速读取

Layer 2: 冷历史 (新增) — 代码文件/数据/tushare/
  永久存储，按API类型分目录
  用途: 趋势分析/回测/深度分析引用

目录结构:
代码文件/数据/tushare/
  ├── hk_hold/{code}.json        ← 北向历史(全量)
  ├── holder_number/{code}.json   ← 股东人数(全量)
  ├── pledge/{code}.json          ← 质押(全量)
  ├── moneyflow/{code}.json       ← 资金流(近1年)
  ├── daily_basic/{code}.json     ← 每日指标(近1年)
  ├── fina_indicator/{code}.json  ← 财务指标(全量)
  ├── margin_detail/{code}.json   ← 两融(近1年)
  ├── forecast/{code}.json        ← 业绩预告(全量)
  ├── fina_mainbz/{code}.json     ← 主营构成(全量)
  ├── share_float/{code}.json     ← 解禁(全量)
  ├── block_trade/{code}.json     ← 大宗交易(全量)
  └── manifest.json               ← 元数据(更新时间/记录数)
```

### 3.2 沉淀策略

| 数据类型 | 频率 | 沉淀方式 | 保留期 |
|:--------|:---:|:--------|:---:|
| daily_basic/moneyflow/margin | 日频 | 每日追加新日数据 | 1年 |
| hk_hold/holder_number | 不定期 | 每次拉取全量覆盖(合并去重) | 永久 |
| fina_indicator/mainbz/forecast | 季频 | 每次拉取全量覆盖(合并去重) | 永久 |
| pledge/share_float/block_trade | 不定期 | 每次拉取追加新记录 | 永久 |

### 3.3 巡检机制

每日自动检查（通过cron或手动触发）：

| 检查项 | 方法 | 阈值 |
|:-------|:----|:---:|
| API连通性 | 调用daily接口验证 | 失败→告警 |
| Token有效性 | 检查返回是否含error | 含error→告警 |
| 数据完整性 | 对比8只重点股票各API数据存在性 | 缺失>1只→告警 |
| 缓存新鲜度 | 检查manifest.json更新时间 | 超TTL→告警 |
| 积分余额 | 暂不支持API查询，手动检查 | — |

## 四、Token影响：零（所有变更不入AI上下文）

## 五、需求→代码核对清单

| # | 需求 | 位置 |
|:--|:-----|:----|
| 1 | PE(TTM)数据源标注更新 | v1.4 §0.3 |
| 2 | §六.3a筹码集中度 | v1.4 新增 |
| 3 | §六.6质押风险 | v1.4 新增 |
| 4 | §六.7供给冲击 | v1.4 新增 |
| 5 | §三.6主营构成 | v1.4 新增 |
| 6 | §三.7业绩预告预期差 | v1.4 新增 |
| 7 | §六.3四档资金增强 | v1.4 修改 |
| 8 | 自检清单#22-#24 | v1.4 新增 |
| 9 | 数据存储脚本 | tushare_history_sync.py |
| 10 | 巡检脚本 | tushare_health_check.py |
