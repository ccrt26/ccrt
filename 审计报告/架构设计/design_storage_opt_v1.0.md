# 玉夜数据存储小优化

> pipeline_stage: complete | L0 | 两处改动

## 变更

| 文件 | 改动 | 行数 |
|:-----|:----|:---:|
| `tushare_history_sync.py` | manifest增加version字段 | +2行 |
| `cached_data_source.py` | _safe_read_json优先orjson | +8行 |
| `tushare_health_check.py` | 检查manifest版本号 | +3行 |
