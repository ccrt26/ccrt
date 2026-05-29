# 日报流水线定时触发+归档修复 — 情墨架构设计交付物

> **阶段**: ① 架构设计 | **设计人**: 情墨 | **日期**: 2026-05-30
> **关联需求**: 腰子5/29数据收管缺口报告（P0-P3四项修复）

## 1. 问题诊断

| # | 问题 | 根因 |
|:--|:-----|:-----|
| P0 | 5/29评分流水线未产出数据 | `daily_workflow.py` 无 cron 定时触发，盘后无人启动数据采集 |
| P1 | 金融铁律缓存路径指向空目录 | `data_cache/` 是旧PS管线遗留路径，实际数据在 `代码文件/数据/` |
| P2 | 5/29数据缺口需回填 | 同P0根因，数据采集从未运行 |
| P3 | `archive_data.py` 缺失 | Phase 6 调用但文件不存在，仅 `_win32_legacy/` 下有 PS1 版 |

## 2. 设计范围

三个交付物：
1. **archive_data.py** (`代码文件/每日荐股/scripts/archive_data.py`) — L1 数据归档脚本
2. **crontab 更新** — 新增 daily_workflow 定时触发 + 调整 orchestrator 时序
3. **金融铁律 §1.2 更新** — 缓存路径修正

## 3. 架构设计

### 3.1 archive_data.py

**技术方案**: Python 移植自 `_win32_legacy/代码文件/每日荐股/scripts/archive_data.ps1`，适配 macOS 路径

**归档映射**:

| 源文件 | 目标目录 | 命名规则 |
|:-------|:---------|:---------|
| `代码文件/数据/data_full.json` | `历史数据/04_原始数据/` | `{date}_data_full.json` |
| `代码文件/数据/data_scored.json` | `历史数据/04_原始数据/` | `{date}_data_scored.json` |
| `代码文件/数据/data_final.json` | `历史数据/04_原始数据/` | `{date}_data_final.json` |
| `代码文件/数据/score_history.jsonl` | `历史数据/04_原始数据/` | `{date}_score_history.jsonl` |
| `代码文件/数据/dynamic_pool.json` | `历史数据/05_参考数据/` | `{date}_dynamic_pool.json` |
| `代码文件/数据/sector_data.json` | `历史数据/05_参考数据/` | `{date}_sector_data.json` |

**保留策略**: 每目录保留最新60个文件（trim），90天过期清理（clean）

**代码等级**: L1（数据管线，非引擎核心）
**文件预算**: ~120行
**Token预算**: ~3KB

### 3.2 crontab 变更

```
# 新增
35 15 * * 1-5  daily_workflow.py --mode daily_latest    # 盘后数据采集+评分+归档

# 调整（37→05）
5  16 * * 1-5  daily_orchestrator.py --mode daily       # 数据就绪检查+信号（晚于流水线30min）
```

**变更理由**: 原15:37 orchestrator 检查时数据尚未采集（chicken-egg），需先跑流水线再检查

### 3.3 金融铁律 §1.2 更新

在 §1.2 数据源编号表末尾追加缓存实际位置说明：

```
实际缓存路径:
- 管线快照: 代码文件/数据/data_full.json
- Tushare本地: 代码文件/数据/tushare/{api_type}/{code}.json
- PS缓存层: 代码文件/每日荐股/data_cache/（迁移过渡期，当前近乎空）
- 历史归档: 历史数据/04_原始数据/, 05_参考数据/
```

## 4. 接口契约

| 脚本 | 调用方式 | 参数 | 退出码 |
|:-----|:---------|:-----|:------:|
| archive_data.py | `daily_workflow.py` Phase 6 subprocess | `--date YYYY-MM-DD` | 0=成功, 1=部分失败 |
| daily_workflow.py | crontab 直接调用 | `--mode daily_latest` | 0=成功, 1=失败 |

## 5. 需求→代码核对

| 编号 | 需求 | 设计覆盖 |
|:----:|:-----|:--------|
| R01 | 流水线盘后自动运行 | §3.2 crontab 15:35 触发 daily_workflow |
| R02 | 数据归档到历史数据/ | §3.1 六项归档映射 |
| R03 | 归档保留策略 | §3.1 trim(60)+clean(90d) |
| R04 | 缓存路径文档修正 | §3.3 金融铁律更新 |
| R05 | orchestrator 时序修正 | §3.2 15:37→16:05 |

## 6. 部署段

| 项目 | 内容 |
|:-----|:-----|
| 灰度方案 | 下次交易日(6/1周一)自动触发，观察workflow日志 |
| 回滚方案 | crontab 还原15:37 orchestrator，移除15:35 workflow |
| 监控 | `每日荐股/运营记录/workflow_202606.log` + `orchestrator_20260601.log` |
