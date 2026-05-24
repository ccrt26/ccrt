# 数据沉淀全面修复 — 关键节点 (2026-05-24)

## 已完成 (Batch 1-4)

### Batch 1: 缓存碎片统一 ✅
- core.ps1:40 — cache dir从 scripts/data_cache/ → 代码文件/每日荐股/data_cache/
- engine.py:186 — attenuation_file 路径修复
- batch_data_collector.ps1:104,278 — sector kline + turnover cache 路径修复
- 删除过期缓存目录: scripts/data_cache/, 代码文件/data_cache/ (文件已合并)

### Batch 2: 记录空值根因 ✅
- run_daily_eval.ps1:118-127 — AllStocks→Recommendations (含评分字段)
- workflow_records.csv — 去重 (8→5行)

### Batch 3: 缺失目录/配置补齐 ✅
- 每日荐股/配置/sector_linkage_map.json — 新建 (10条产业链映射)
- 模拟交易/否决审查/ — 新建目录
- 每日荐股/配置/core_stocks.json — 删除过期空文件

### Batch 4: sim_trading.ps1 双写消除 ✅
- 主路径切换: 历史数据/00_核心交易/ ← 模拟交易/持仓记录/
- 删除所有 $canon*File 双写引用 (4处)
- 添加旧路径只读回退: positions, transactions, perf_summary (4处)
- prevSnapshot 主/备路径回退
- S级镜像备份保留 (_backup/)
- 备份SHA256哈希校验保留

## 待完成

### Batch 5: 玉夜数据质量补齐
- TECH-08: PEG一致预期数据调研
- TECH-05: 大宗商品API接入方案
- 评估准确率跟踪机制

### Batch 6: 新安全量验证
- 12项修复逐项验证
- 红线合规检查
- 审计报告保存
