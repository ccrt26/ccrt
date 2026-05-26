# 05 — 数据源与API详情

> 铁律量化 · 信鸽知识库 | 2026-05-26 v1.0
> 关联：pigeon_cninfo.ps1 / 玉夜-知识库/01-数据源全景

---

## 一、数据源架构（1+2）

```
主源[16] cninfo JSON API
  ↓ 失败
备源[17] china-stock-mcp (待集成)
  ↓ 失败
缓存[C] 本地24h缓存
```

---

## 二、cninfo [16] — 主源

### 端点
```
GET http://www.cninfo.com.cn/new/fulltextSearch/full
  ?searchkey={股票名称}
  &sdate={yyyy-MM-dd}
  &edate={yyyy-MM-dd}
  &isfulltext=false
  &sortName=pubdate
  &sortType=desc
  &pageNum=1
```

### 返回格式
```json
{
  "announcements": [
    {
      "announcementTitle": "标题（含<em>高亮标签）",
      "announcementTime": 1779724800000,
      "adjunctUrl": "finalpage/2026-05-26/1225328517.PDF",
      "secName": "东睦股份",
      "secCode": "600114"
    }
  ]
}
```

### 关键参数
- `searchkey`: URL Encode的股票名称（如 `%E4%B8%9C%E7%9D%A6%E8%82%A1%E4%BB%BD`）
- `isfulltext=false`: 仅标题搜索，不需要全文（全文返回噪音多）
- 不需要认证/API key/登录
- 返回条数不设上限，由MaxResults参数控制截断

### 频率限制
- **1s间隔**（`cninfo_interval_ms: 1000`），无官方文档但实测低于500ms会触发限流
- 重试策略：指数退避 1s→2s→4s，最多2次重试

### 字段映射
| API字段 | 信鸽字段 | 处理 |
|:-----|:-----|:-----|
| announcementTitle | title | 去`<em>` `</em>`标签 |
| announcementTime | publish_time | 毫秒时间戳 |
| adjunctUrl | pdf_url | 拼接 `http://static.cninfo.com.cn/` |
| secName | sec_name | 直接映射 |
| secCode | sec_code | 直接映射 |

---

## 三、baostock [14] — 业绩预告/快报

### 端点
```python
# Python库，通过 Invoke-BaostockFallback 桥接
baostock.query('forecast', code='sh.600114', start='2026-05-23', end='2026-05-26')
baostock.query('express', code='sh.600114', start='2026-05-23', end='2026-05-26')
```

### 市场前缀
- 6开头 → `sh.`
- 其他 → `sz.`

### 频率限制
- 500ms间隔

### 已知特征
- 季报空窗期（如5月下旬，距Q1季报已过）→ 返回空，正常行为
- 只返回有实际预告/快报的数据，无数据时返回空
- 包含字段：forecastType, profitRange, forecastDate, operateIncome, netProfit

---

## 四、东财研报 [11] — 研报标题采集

### 端点
```
通过 stock_data_fetcher_legacy.psm1 的 Get-ResearchData 函数
```

### 当前状态
- Phase 1 仅做研报标题层面采集（`Invoke-ResearchNewsOnly`）
- 不解析研报全文、不提取评级/目标价
- 返回字段：title, publishDate
- Phase 2 接入完整封装

---

## 五、china-stock-mcp [17] — 备源

### 端点
```
MCP Server: china-stock-mcp
Tool: get_news_data
```

### 当前状态
- Phase 1 占位（`Invoke-CninfoAnnouncementBackup` 返回空）
- 频率限制：50次/天
- Phase 2 正式集成

---

## 六、WebFetch 行业政策 — Phase 2

| 触发条件 | 目标 | 频次 |
|:-----|:-----|:-----|
| 周二/周五 | 工信部/发改委官网 | 每周2次 |

Phase 2实施。当前Phase 1占位。

---

## 七、缓存策略

| 层级 | 位置 | TTL | 清理 |
|:-----|:-----|:---:|:-----|
| L1 | `消息面数据/{date}_events.json` | 当日 | 不自动清理 |
| L2 | `消息面数据/events_db.json` | 永久追加 | 不清理 |
| L3 | `消息面数据/cache/{date}_cache.json` | 24h | >7天自动清除 |

缓存命中条件：主源+备源均失败 → 读取当日cache → 未过期(TTL内) → 返回
