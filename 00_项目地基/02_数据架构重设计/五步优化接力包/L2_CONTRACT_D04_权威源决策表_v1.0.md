# D04 权威源决策表

> 流程：F-ARCH | F-DATA
> 阶段门：G2（技术方案设计冻结）
> 日期：2026-06-08

---

## 一、三维权威源定义

### 1.1 当日权威源（L1 JSON）

| 组成 | 路径 | 格式 | 容量 | git 跟踪 | 用途 |
|:-----|:-----|:-----|:-----|:---------|:-----|
| data_full.json | `代码文件/数据/data_full.json` | JSON（Stocks 数组 + FundFlows） | ~5.6MB | ✅ 是 | 当日全量截面，引擎唯一读入源 |
| kline_cache/*.json | `代码文件/数据/kline_cache/{code}.json` | JSON 数组（OHLCV 日线） | ~8KB/只 | ✅ 是 | K线 L1 缓存（当前 122 天） |
| fund_flow_cache/*.json | `代码文件/数据/fund_flow_cache/{code}.json` | JSON 数组（四档资金） | ~2KB/只 | ✅ 是 | 资金流 L1 缓存 |

**权威规则**：
- L1 是引擎当日唯一读入源
- `materialize_daily_authoritative_cache.py` 从 `data_full.json` 派生补齐 `kline_cache` / `fund_flow_cache`
- `data_full.json` 是 L1 当日权威组成之一，**不是**单一权威源
- L1 数据不做复权标准化，原始缓存保持原样（`adjust_flag = 'none'`）

### 1.2 历史权威源（L2 SQLite）

| 表名 | 用途 | Tier 映射 | 容量预估 | TTL |
|:-----|:-----|:----------|:---------|:----|
| kline | K 线历史（前复权） | Tier 3 + Tier 2 历史副本 | ~10MB | 永久（750 天+） |
| score_history | 评分历史 | Tier 3 低频历史 | ~3MB | 永久 |
| returns | 收益表（IC 计算） | Tier 3 低频历史 | ~1MB | 永久 |
| financials | 财务指标 | Tier 3 季度更新 | ~1MB | 永久 |
| macro | 宏观数据 | Tier 3 月度更新 | ~0.5MB | 永久 |
| risk_metrics | 风控预计算 | Tier 2 日频 | ~0.5MB | 24h 更新 |
| historical_percentiles | 跨期对比缓存 | Tier 2 日频 | ~0.1MB | 24h 更新 |

**权威规则**：
- L2 是历史查询的首选源（索引快 + SQL JOIN + 口径统一）
- L2 数据的分析副本性质：以 L1 为准同步，不一致时以 L1 为准
- 所有写入 L2 的 K 线统一为前复权（`adjust_flag = 'forward'`）
- `.gitignore` 排除，不进入 git

### 1.3 永久归档权威源（L3 JSON 年目录）

| 路径 | 格式 | 周期 | 容量 | git 跟踪 | 用途 |
|:-----|:-----|:-----|:-----|:---------|:-----|
| `历史数据/04_原始数据/{年}/` | JSON 周级快照 | 每周最后交易日 | ~176MB/年 | ✅ 是（<800MB） | 审计追溯，不被程序常规读取 |

**权威规则**：
- L3 只用于审计追溯，不作为程序常规读取源
- git 红线阈值：项目仓库 < 800MB → L3 继续入 git；≥ 800MB → L3 移出 git（保留索引）
- 每次归档后生成 `archive_manifest.sha256` 和 `archive_index.json`

---

## 二、权威冲突裁决规则

| 冲突场景 | 裁决规则 | 裁决人 | 绑定红线 |
|:---------|:---------|:-------|:---------|
| L1 vs L2 不一致 | **以 L1 为准**（L1 是生产数据实时截面，L2 是分析副本） | 玉夜 | R-FIN-0001 §1.7 |
| L2 vs L3 不一致 | **以 L2 为准**（L2 是最新重建基线，L3 快照可能过时） | 玉夜 | R-FIN-0001 §1.7 |
| tushare 历史修正 vs L1 | **情墨+腰子双签**后方可反向更新 L1 | 情墨+腰子 | R-FIN-0001 §1.7 |
| 价格差异 < 0.5% | 玉夜可自行决定以 L1 为准 | 玉夜 | — |
| 价格差异 ≥ 0.5% | 玉夜收集数据事实后上报腰子裁决 | 玉夜→腰子 | R-FIN-0001 §1.7 |

---

## 三、当前脚本权威口径冲突与修正

### 3.1 `materialize_daily_authoritative_cache.py`

**当前口径**（第 5 行）：`data_full.json 是单一权威源`
**修正方向**：改为 "`data_full.json` + `kline_cache` + `fund_flow_cache` 共同组成 L1 当日权威"
**处理步骤**：STEP1 只冻结契约/派单口径；STEP2 或后续代码阶段修改注释口径与物理实现

### 3.2 `archive_data.py`

**当前保留策略**：`KEEP_LATEST=60`（第 23 行）、`RETENTION_DAYS=90`（第 24 行）
**冲突**：与 L3 永久归档设计完全矛盾
**修正方向**：双模式改造——每日归档模式 + 周级快照模式。取消 90 天裁剪，改为按年分目录永久保留
**处理步骤**：STEP1 只冻结方案；STEP2 修改 `archive_data.py` 并建立年目录+索引

### 3.3 `CachedDataSource`

**当前路由**：Tushare 本地 → PS 缓存 → 管线快照 → API → 过期兜底 → null（6 级混合路由）
**定位**：Phase 3 前保持 L1，不得删除或重大修改
**替换方案**：UnifiedDataSource shadow/dual-write → guarded cutover
**处理步骤**：STEP3 实现 UnifiedDataSource，STEP3 确认 import 清零

### 3.4 `data_full.json` 内嵌 KClose 数组

**现状**：`data_full.json` 的每个 Stock 对象内嵌 `KClose`/`KDate`/`KOpen`/`KHigh`/`KLow`/`KVolume` 数组（当前 ~60 天）
**冲突**：kline_cache/*.json 独立存在（122 天），两者部分重叠不同步
**修正方向**：`migrate_historical_kline.py` 将三者统一收敛到 L2 SQLite
**处理步骤**：STEP3 执行迁移脚本

---

## 四、数据源溯源关系

| 数据类型 | 进入 L1 的源 | 进入 L2 的源 | L3 归档源 | 频率 |
|:---------|:------------|:------------|:----------|:-----|
| K 线日线 | 东方财富 API → `batch_data_collector` → `data_full.json` | tushare pro（一次性拉 750 天→L2） | L2 重建 | 每日增量 |
| 评分数据 | `data_full.json` / `data_scored.json` | L3 归档重建 | 周级快照 | 每日增量 |
| 财务数据 | `data_full.json` 当前季度 | tushare `fina_indicator` | L2 重建 | 季度查询 |
| 资金流向 | `data_full.json` FundFlows | 同 L1（从 L1 同步） | L1 周级 | 每日 |
| 宏观指标 | N/A（无 L1） | 手动/自动注入 | L2 重建 | 月度 |
