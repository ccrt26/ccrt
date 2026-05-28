# 解决方案框架 — 数据本地优先架构

> 青山+旧影 联合设计 | 2026-05-28 | 待情墨转化为正式设计文档

---

## 一、问题定义（旧影审计发现）

| 审计项 | 发现 | 严重度 |
|:-------|:----|:---:|
| 本地数据利用率 | 23,064条Tushare数据+PowerShell缓存层完全不被报告流程读取 | **P0** |
| API重复调用 | batch_data_collector.py每次运行从头调用腾讯/新浪/THS API | **P0** |
| 缓存层断裂 | macOS Python管线绕过PowerShell Invoke-DataSource缓存层 | **P1** |
| 数据不可复现 | 同一标的在不同时间拉取数据可能不一致 | **P1** |
| Token浪费 | AI报告生成时实时调API，数据入AI上下文 | **P1** |

## 二、目标架构（青山设计）

### 2.1 数据获取优先级

```
报告/分析请求
  ↓
CachedDataSource.get(data_type, code, freshness_requirement)
  ↓
① Tushare本地历史 (数据/tushare/{type}/{code}.json)
   命中 + 新鲜 → 返回 [tushare-local]
  ↓ 未命中/过期
② 管线采集缓存 (data_cache/{type}_{code}.json)
   命中 + 新鲜 → 返回 [C]
  ↓ 未命中/过期  
③ 当日管线快照 (数据/data_full.json)
   命中 → 返回 [pipeline]
  ↓ 未命中
④ 降级到实时API (腾讯/新浪/THS/Tushare API)
   成功 → 返回 [API] + 写入缓存
  ↓ 失败
⑤ 过期缓存兜底 (30天TTL)
   存在 → 返回 [C-stale] + 标注"数据过期X小时"
  ↓ 不存在
⑥ 返回 null → "数据不可获取"
```

### 2.2 数据分层与TTL

| 层级 | 数据类型 | TTL | 存储 | 更新方式 |
|:----:|:--------|:--:|:----|:--------|
| **L0-实时** | 行情(价格/涨跌幅) | 1h | data_cache/ | 调API→写缓存 |
| **L1-日频** | 资金流/日指标/两融/K线 | 24h | Tushare本地 | 盘后sync→本地 |
| **L2-季频** | 财务/股东/质押/主营/预告 | 168h(7d) | Tushare本地 | 每周sync→本地 |
| **L3-事件** | 大宗/龙虎榜/增减持/回购/分红 | 24h | Tushare本地 | 日频追加 |
| **L4-计算** | 技术指标/PE分位/评分 | — | 本地计算 | 实时计算 |

### 2.3 调度时间线

```
15:30  盘后Tushare日频同步 (daily_basic/moneyflow/margin_detail)
       → tushare_history_sync.py --daily
16:00  管线批处理 (全量数据已在本地)
       → batch_data_collector.py (读本地→data_full.json→scoring→report)
19:00  信鸽事件采集
20:30  深度分析(周五)/日报(交易日)
       → AI角色直接从本地读取，不再调API
```

## 三、实现方案

### 3.1 新增模块

| 文件 | 等级 | 说明 |
|:-----|:---:|:-----|
| `代码文件/lib/cached_data_source.py` | L0 | 统一数据访问层，封装5级降级逻辑 |

### 3.2 修改文件

| 文件 | 改动 | 行数 | 等级 |
|:-----|:----|:---:|:---:|
| `batch_data_collector.py` | 每个数据采集函数改为CachedDataSource.get() | ~100行 | L0 |
| `daily_workflow.py` | 新增Phase 0: Tushare日频预同步 | ~10行 | L0 |
| `tushare_history_sync.py` | 新增--daily-only模式，注册到调度 | ~10行 | L0 |

### 3.3 CachedDataSource 接口

```python
class CachedDataSource:
    def get_financial(code, ttl_hours=168) -> dict
    def get_daily_basic(code, ttl_hours=24) -> dict  
    def get_moneyflow(code, ttl_hours=24) -> dict
    def get_margin(code, ttl_hours=24) -> dict
    def get_kline(code, days=120, ttl_hours=24) -> dict
    def get_quote(code, ttl_hours=1) -> dict           # 实时,短TTL
    def get_northbound(code, ttl_hours=24) -> dict
    def get_holder_number(code, ttl_hours=168) -> dict
    def get_pledge(code, ttl_hours=24) -> dict
    def get_forecast(code, ttl_hours=168) -> dict
    def get_mainbz(code, ttl_hours=168) -> dict
```

每个方法内部执行①→⑥降级链，返回统一格式：
```json
{
  "data": [...],
  "source": "tushare-local",
  "freshness": "fresh",
  "cached_at": "2026-05-28T16:00:00"
}
```

## 四、旧影合规标准

### 4.1 必须满足的红线

| 红线条款 | 要求 | 设计保证 |
|:--------|:----|:--------|
| §1.1 1+2主备 | 每个数据字段有主备源 | ④API调用保留现有主备链 |
| §1.2 数据源编号 | 标注来源 | 返回数据中含source字段 |
| §1.3 禁止编造 | 不推测 | null时返回"数据不可获取" |
| §5.4 文档同步 | 变更可追溯 | 设计文档+CHANGELOG |

### 4.2 数据质量闸门

| 检查项 | 阈值 | 动作 |
|:-------|:---:|:-----|
| API调用降为0(全本地命中) | 目标>90% | <80% → WARN |
| 缓存命中率 | >90% | <80% → 检查同步 |
| 数据滞后 | TTL内 | 超TTL → 标注stale |
| 缓存文件完整性 | 8/8重点股票 | <8 → WARN |

### 4.3 审计追踪

每次数据请求在返回中自动记录：数据源→命中层级→新鲜度→时间戳。下游可直接审计数据来源。

## 五、影响评估

| 维度 | 当前 | 改进后 | 改善 |
|:-----|:----|:-----|:---:|
| API调用/次报告 | ~200次 | ~0-5次(仅L0实时) | **95%+减少** |
| 报告生成耗时 | 60-120秒 | 5-10秒 | **10-20x** |
| Token消耗(AI报告) | 实时API数据入上下文 | 读本地摘要 | **大幅降低** |
| 数据复现性 | 不可复现 | 版本锁定 | 质的提升 |
| API故障影响 | 报告失败 | 降级到过期缓存 | 容错升级 |

## 六、Token影响：零（数据走本地文件，增强AI效率）

---

> 此框架移交情墨，进入§七流程阶段①正式架构设计。
