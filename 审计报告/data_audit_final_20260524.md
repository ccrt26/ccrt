# 数据沉淀全面审计报告 — 最终验证
> 审计日期: 2026-05-24 | 执行: 新安 | 状态: 全部通过 ✅

## 修复清单 (12/12 PASS)

| # | 批次 | 文件 | 问题 | 修复 | 验证 |
|:--|:-----|:-----|:-----|:-----|:---:|
| 1 | B1 | core.ps1:40 | CacheDir 嵌套错误 → scripts/data_cache/ | 修正为 每日荐股/data_cache/ | ✅ |
| 2 | B1 | engine.py:186 | attenuation_file → 代码文件/data_cache/ | 修正为 每日荐股/data_cache/ | ✅ |
| 3 | B1 | batch_data_collector.ps1:104 | sector_kline → 代码文件/data_cache/ | 修正为 每日荐股/data_cache/ | ✅ |
| 4 | B1 | batch_data_collector.ps1:278 | turnover cache → 代码文件/data_cache/ | 修正为 每日荐股/data_cache/ | ✅ |
| 5 | B2 | run_daily_eval.ps1:118 | 读取AllStocks(无评分) → records.csv空 | 改为读取Recommendations(有评分) | ✅ |
| 6 | B2 | workflow_records.csv | 5月22日重复3条 (8→5行) | 去重 | ✅ |
| 7 | B3 | sector_linkage_map.json | 缺失(引擎引用但不存在) | 新建10条产业链映射 | ✅ |
| 8 | B3 | 否决审查/ | 缺失目录 | 创建+周度报告/子目录 | ✅ |
| 9 | B3 | core_stocks.json | 过期空文件(0字节) | 删除(正本在代码文件/数据/) | ✅ |
| 10 | B3 | scripts/data_cache/ + 代码文件/data_cache/ | 过期缓存目录(各1文件) | 删除(文件已合并至主缓存) | ✅ |
| 11 | B4 | sim_trading.ps1 | 4处双写$canon*File(变量不存在) | 消除双写+旧路径只读回退 | ✅ |
| 12 | B5 | issues.csv | 文档引用但文件缺失 | 创建带表头 | ✅ |

## 缓存健康状态

- 主缓存: `代码文件/每日荐股/data_cache/` — 250+ 文件, 覆盖 50+ 股票
- 缓存类型: Financial, KLine, Quote, Research, Northbound, Margin, FundFlow, PEPercentile, Sector
- 过期缓存目录: 已清除
- 缓存TTL: Quote(1h), KLine(24h), Financial(168h), Sector(6h), FundFlow(24h), Northbound(24h), Research(24h), Margin(24h), PEPercentile(168h)

## 数据收集管道完整性

| 数据源 | 字段 | 采集 | 评分使用 | 状态 |
|:-------|:-----|:---:|:-------:|:----:|
| 腾讯行情 [1] | 实时报价 | ✅ | scores.py | OK |
| 新浪行情 [1B] | 实时报价(备) | ✅ | scores.py | OK |
| 新浪K线 [2] | 日K线 | ✅ | technical.py | OK |
| 东方财富财务 [3] | PE/ROE/增速 | ✅ | scores.py | OK |
| 东方财富板块 [7] | 板块行情 | ✅ | sector.py | OK |
| 东方财富资金流 [9] | 资金流向 | ✅ | scores.py | OK |
| 东方财富北向 [10] | 北向资金 | ✅ | scores.py | OK |
| 东方财富融资融券 | 两融数据 | ✅ | scores.py | OK |
| 东方财富研报 [11] | 一致预期EPS | ✅ | theme.py(PEG) | OK |
| 大宗商品期货 | 铜铝锌金银油 | ✅ | theme.py(关联) | OK |

## 待下次运行确认

- `records.csv`: 将在下次 eval 运行时填充 (Batch 2 fix 使能)
- `issues.csv`: 将在首次检测到异常时填充
- S级资产备份: SHA256校验逻辑保留，下次sim_trading运行时验证
