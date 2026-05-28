# 架构设计 — 数据本地优先架构（缓存层重构）

> pipeline_stage: complete | 情墨 v1.0 | 基于青山+旧影框架
> 代码等级: L0（数据访问层+采集器修改）
> Token影响评估: 零（数据走本地文件，减少AI上下文API调用）

---

## 一、需求

当前 `batch_data_collector.py` 每次运行都实时调用腾讯/新浪/THS API，已有23,064条Tushare本地数据和PowerShell缓存层完全不使用。需要在数据采集层增加"本地优先"的5级降级逻辑。

## 二、新增文件

| 文件 | 行数 | 等级 | 说明 |
|:-----|:---:|:---:|:-----|
| `代码文件/lib/cached_data_source.py` | ~200行 | L0 | 统一数据访问层 |

## 三、修改文件

| 文件 | 改动 | 行数 | 等级 |
|:-----|:----|:---:|:---:|
| `代码文件/每日荐股/scripts/batch_data_collector.py` | 每个数据采集函数改为CachedDataSource调用 | ~100行 | L0 |
| `代码文件/每日荐股/scripts/daily_workflow.py` | 新增Phase 0: 盘后Tushare日频预同步 | ~10行 | L0 |

## 四、CachedDataSource 接口设计

### 4.1 核心方法

```python
class CachedDataSource:
    # 数据获取（5级降级：Tushare本地→PS缓存→管线快照→API→过期兜底）
    def get_financial(code) -> dict       # fina_indicator, TTL=168h
    def get_daily_basic(code) -> dict     # TTL=24h
    def get_moneyflow(code) -> dict       # TTL=24h
    def get_margin(code) -> dict          # TTL=24h
    def get_kline(code, days=120) -> dict # TTL=24h
    def get_quote(code) -> dict           # 实时行情, TTL=1h
    def get_northbound(code) -> dict      # hk_hold, TTL=24h
    def get_holder_number(code) -> dict   # TTL=168h
    def get_pledge(code) -> dict          # TTL=24h
    def get_forecast(code) -> dict        # TTL=168h
    def get_mainbz(code) -> dict          # TTL=168h
    
    # 内部
    def _load_tushare(api_type, code)     # ① 读取 数据/tushare/{type}/{code}.json
    def _load_ps_cache(cache_key)          # ② 读取 data_cache/{key}.json
    def _load_pipeline_snapshot(code)      # ③ 读取 数据/data_full.json
    def _check_freshness(data, ttl_hours)  # 检查新鲜度
```

### 4.2 返回格式

```json
{
  "data": [...],
  "source": "tushare-local",
  "source_label": "[tushare]",
  "freshness": "fresh",
  "cached_at": "2026-05-28T16:00:00",
  "ttl_hours": 168,
  "rows": 7
}
```

### 4.3 降级链

```
① 数据/tushare/{type}/{code}.json → fresh → return
② data_cache/{type}_{code}.json → fresh → return  
③ 数据/data_full.json → hit → return
④ API实时调用 → success → write cache → return
⑤ 过期缓存(30d) → return + is_stale=True
⑥ return {"data": null, "error": "数据不可获取"}
```

## 五、batch_data_collector.py 改动

原有模式：
```python
def collect_quote(stocks):
    for code in stocks:
        quote = http_fetch_tencent(code)  # 直接HTTP
```

改为：
```python
def collect_quote(stocks, cache):
    for code in stocks:
        result = cache.get_quote(code)
        if result["source"] != "tushare-local":
            log_miss(code, result["source"])
```

## 六、daily_workflow.py 改动

在Phase 1之前新增 Phase 0：
```python
# Phase 0: 盘后Tushare日频预同步
subprocess.run(["python", "tushare_history_sync.py", "--daily"])
```

## 七、Token影响评估

| 维度 | 评估 |
|:-----|:-----|
| 新增模板 | 0 |
| AI上下文数据量 | 减少（AI角色读本地摘要，不再实时调API） |
| API调用 | batch_data_collector从~200次/run降至~0-5次 |
| 总体 | 零Token增量，显著降低AI上下文消耗 |

## 八、需求→代码核对清单

| # | 需求 | 位置 |
|:--|:-----|:----|
| 1 | CachedDataSource类 | cached_data_source.py |
| 2 | get_financial → fina_indicator | cached_data_source.py |
| 3 | get_daily_basic → daily_basic | cached_data_source.py |
| 4 | get_moneyflow → moneyflow | cached_data_source.py |
| 5 | get_margin → margin_detail | cached_data_source.py |
| 6 | get_kline → daily/pro_bar | cached_data_source.py |
| 7 | get_quote → 腾讯行情(实时) | cached_data_source.py |
| 8 | 5级降级链 | cached_data_source.py |
| 9 | batch_data_collector改为读缓存 | batch_data_collector.py |
| 10 | daily_workflow添加Phase 0预同步 | daily_workflow.py |
