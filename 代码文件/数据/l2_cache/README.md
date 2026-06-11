# L2 历史分析缓存（SQLite）

## 用途

L2 是 D04 数据中台的历史分析缓存层，用于加速历史 K 线查询、评分回溯、财务指标分析和宏观数据查询。
L2 不做生产报告的直接数据源，仅作为 **历史回源** 使用。

## 目录结构

```
l2_cache/
├── .gitignore          # 排除 DB/备份/哨兵
├── .gitkeep            # 占位
├── README.md           # 本文件
├── SOP_P0.md           # 故障恢复标准操作流程
├── last_update.json    # 哨兵文件（运行时生成）
├── operation_log.jsonl # 操作日志（运行时生成）
├── l2_cache.db         # SQLite 数据库（运行时生成）
├── backup/             # 每日备份目录
│   ├── .gitkeep
│   └── l2_cache_YYYYMMDD_HHMMSS.db
```

## 数据来源

| 表名 | 数据源 | 更新频率 |
|:-----|:-------|:--------|
| kline | tushare pro.daily（一次性 750 天）+ 每日增量 | 每日 |
| score_history | L3 归档 `*_data_scored.json` 重建 | 一次性 |
| returns | L1 数据派生（STEP3 后填充） | 每日 |
| financials | tushare fina_indicator | 季度 |
| macro | 手动/自动注入 | 月度 |
| risk_metrics | D08 计算后填充 | 每日 |
| historical_percentiles | D04 update 计算 | 每日 |

## 权威层级

- **L1（当日权威）**: `data_full.json` + `kline_cache/*` + `fund_flow_cache/*`
- **L2（历史权威）**: 本 SQLite（索引快、口径统一、前复权）
- **L3（归档权威）**: `历史数据/04_原始数据/{year}/`

冲突裁决：当日判断以 L1 为准；历史回溯以 L2 为首选；L2 与 L3 不一致以 L2 为准。

## 维护入口

| 操作 | 脚本 |
|:-----|:-----|
| 一次性构建 | `scripts/build_l2_cache.py --dry-run` |
| 每日增量更新 | `scripts/update_l2_cache.py --date YYYY-MM-DD --dry-run` |
| 从 L3 重建评分历史 | `scripts/rebuild_score_history.py --dry-run` |
| 健康检查 | `scripts/check_d04_health.py --dry-run` |
| quality_flag 同步 | `scripts/sync_quality_flag.py --table all --dry-run` |

## 设计原则

1. **不切生产** — 日报/深度分析仍使用 L1，不读 L2。
2. **前复权统一** — 所有 K 线写入 L2 时统一为前复权（`adjust_flag='forward'`）。
3. **幂等写入** — `INSERT OR REPLACE` 按主键 upsert。
4. **dry-run 优先** — 任何数据写入前必须先通过 `--dry-run` 验证。
