# 架构设计 — Tushare Pro 全量API接入（三梯队）

> pipeline_stage: complete | 情墨 v1.0 | 扩展 design_tushare_pro_v1.0
> 代码等级: L0（全部数据桥接+注册）
> 前置: 桥接脚本 stock_data_fetcher_tushare.py 已实现全部15个action

---

## 一、变更范围

桥接脚本无需修改（已预留全部action）。本次仅涉及：

| 文件 | 改动 | 行数 | 等级 |
|:-----|:----|:---:|:---:|
| `core.ps1` | SourceRegistry新增/调整11条 | +60行 | L0 |
| `数据字典.md` | 新增Tushare数据条目 | +20行 | M类 |
| `01-数据源全景.md` | 更新降级链 | +20行 | M类 |

## 二、SourceRegistry 变更

### 新增条目

| Key | Primary | Backups | TTL |
|:----|:--------|:--------|:--:|
| MoneyFlow | Tushare[tushare] | 东财[9], THS | 24h |
| DailyBasic | Tushare[tushare] | 腾讯[1] | 6h |
| Forecast | Tushare[tushare] | baostock[14] | 168h |
| MainBZ | Tushare[tushare] | — | 168h |
| BlockTrade | Tushare[tushare] | — | 24h |
| TopList | Tushare[tushare] | 东财 | 24h |
| HolderTrade | Tushare[tushare] | — | 24h |
| Repurchase | Tushare[tushare] | — | 24h |
| Dividend | Tushare[tushare] | baostock[14] | 168h |

### 调整条目

| Key | 变更 |
|:----|:-----|
| Margin | Tushare升为Primary，东财[12]降为Backup |
| FundFlow | 新增Tushare为Primary（当前[9]东财降为Backup） |

## 三、Token影响：零

## 四、需求→代码核对清单

| # | 需求 | 位置 |
|:--|:-----|:----|
| 1-9 | 9条新SourceRegistry | core.ps1 |
| 10-11 | 2条调整(Margin/FundFlow) | core.ps1 |
| 12-13 | 文档同步 | 数据字典/数据源全景 |
