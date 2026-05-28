# 四层验证 — Tushare Pro 数据源接入（闸门2）

> pipeline_stage: stage_4 | 新安 | 2026-05-28

---

## 第一层：语法+结构验证

| 检查项 | 结果 | 说明 |
|:-------|:---:|:-----|
| Python语法 | PASS | `ast.parse()` 通过 |
| 单文件行数 | PASS | 363行 ≤ 500行红线 |
| 函数完整性 | PASS | 11个 action 全部实现 |
| 错误处理 | PASS | try/except + 重试退避 |

## 第二层：接口契约验证

| 设计约定 | 实现匹配 | 结果 |
|:--------|:--------|:---:|
| CLI: `action [--code] [--start] [--end]` | argparse 完全匹配 | PASS |
| 输出: JSON→stdout (UTF-8) | `safe_json()` + `sys.stdout.buffer.write` | PASS |
| Code转换: `_to_tushare_code` / `_from_tushare_code` | 实现正确 | PASS |
| Token: 环境变量 `TUSHARE_TOKEN` | `os.environ.get("TUSHARE_TOKEN")` | PASS |
| 限速: 0.35s | `RATE_LIMIT_SEC = 0.35` | PASS |
| 重试: 2次+退避 | `MAX_RETRIES=2, RETRY_BACKOFF=1.0` | PASS |

## 第三层：降级链验证

| SourceRegistry条目 | Primary | Backups | 结果 |
|:------------------|:--------|:--------|:---:|
| KLine | Tushare | 新浪→必盈 | PASS |
| Financial | Tushare | 东财→THS→必盈 | PASS |
| Northbound | Tushare | 东财[8] | PASS |
| Margin | 东财[12]→**Tushare(新)** | THS | PASS |
| Pledge(新) | Tushare | — (独有) | PASS |
| ShareFloat(新) | Tushare | — (独有) | PASS |
| HolderNumber(新) | Tushare | — (独有) | PASS |

## 第四层：变更影响验证

| 维度 | 结果 |
|:-----|:---:|
| 现有功能回归 | PASS — 无修改现有函数逻辑 |
| 评分引擎 | PASS — 未修改 scores.py |
| 交易引擎 | PASS — 未修改 |
| 报告生成 | PASS — 数据经 data_full.json 流入 |
| api_config.json 向后兼容 | PASS — 仅追加 tushare 段 |

## Token效率

| 检查项 | 结果 |
|:-------|:---:|
| 新增模板 | 0 |
| 数据入AI上下文 | 从不（stdout→文件） |
| check_token_efficiency.py | 工具脚本尚未部署，手工验证通过 |

---

## 验证结论：PASS — 放行至阶段⑥（红枫部署）
