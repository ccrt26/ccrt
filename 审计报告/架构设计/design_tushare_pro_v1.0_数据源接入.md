# 架构设计 — Tushare Pro 数据源接入（第一梯队）

> pipeline_stage: complete | 情墨 v1.0 | 待腰子确认
> 代码等级: L0（桥接+数据采集）
> 白皮书依据: 规则红线v1.16 §1.1(1+2主备) §1.2(数据源编号) §5.4(文档同步)
> 背景: 引入Tushare Pro 2000积分档，覆盖北向/质押/解禁/股东人数四项盲区数据

---

## 一、需求概述

当前数据架构存在三个盲区：

| 盲区 | 现状 | Tushare修复 |
|:-----|:----|:----------|
| 北向资金日频 | 2024/08政策后仅季度快照，~57天滞后 | `hk_hold` 恢复日频 |
| 股权质押 | 零覆盖，风控盲区 | `pledge_detail` 新接入 |
| 限售解禁 | 零覆盖，供给冲击不可测 | `share_float` 新接入 |
| 股东人数 | 零覆盖，筹码集中度不可测 | `stk_holdernumber` 新接入 |

Tushare Pro 2000积分档（¥200/年）：200次/分钟，100,000次/天/API，覆盖上述全部接口。

### 核心收益

| 收益 | 说明 |
|:-----|:-----|
| 北向资金复活 | 日频外资持股数据恢复，资金面评分不再"盲" |
| 风控盲区补全 | 质押爆仓+解禁抛压预警，P0事件可提前触发 |
| 新alpha因子 | 筹码集中度因子(股东人数)可纳入评分体系 |
| 1+2架构加固 | K线/财务/两融获高质量备源 |

---

## 二、模块设计

### 2.1 新增文件

| 文件 | 行数 | 等级 | 说明 |
|:-----|:---:|:---:|:-----|
| `代码文件/每日荐股/scripts/stock_data_fetcher_tushare.py` | ~300行 | L0 | Tushare Pro Python桥接脚本，CLI模式 |

### 2.2 修改文件

| 文件 | 改动 | 行数 | 等级 |
|:-----|:----|:---:|:---:|
| `代码文件/每日荐股/scripts/modules/core.ps1` | SourceRegistry 新增/调整降级链 + Invoke-TushareFallback | ~50行 | L0 |
| `代码文件/config/api_config.json` | 新增Tushare配置段(token引用/端点/限速) | ~10行 | L0 |
| `.claude/knowledge/数据字典.md` | 新增Tushare数据源条目，更新北向降级链 | ~15行 | M类 |
| `.claude/agents/玉夜-知识库/01-数据源全景.md` | 新增[tushare]条目 | ~30行 | M类 |

### 2.3 不修改的文件

- 评分引擎 (`scores.py`) — 第一梯队不涉及评分权重调整，仅数据接入
- 模拟交易引擎 — 无交易逻辑变更
- 报告生成 — 数据写入 `data_full.json`，报告层自动拾取
- 必盈[13]/baostock[14]/THS桥接 — 无耦合

---

## 三、接口契约

### 3.1 Tushare桥接 CLI

```
调用: python stock_data_fetcher_tushare.py <action> [--code CODE] [--start DATE] [--end DATE]
返回: JSON数组 → stdout
```

**Action清单**（第一梯队 + 第二梯队预留）：

| action | Tushare API | 积分要求 | 梯队 |
|:-------|:-----------|:--------|:---:|
| `daily` | `pro.daily()` | 120 | 2(预留) |
| `kline` | `pro.pro_bar()` | 2000 | 2(预留) |
| `financial` | `pro.fina_indicator()` | 2000 | 2(预留) |
| `moneyflow` | `pro.moneyflow()` | 2000 | 2(预留) |
| `margin` | `pro.margin_detail()` | 2000 | 2(预留) |
| `hk_hold` | `pro.hk_hold()` | 2000 | **1** |
| `pledge` | `pro.pledge_detail()` | 2000 | **1** |
| `share_float` | `pro.share_float()` | 3000 | **1**(预留) |
| `holder_number` | `pro.stk_holdernumber()` | 2000 | **1** |

> `share_float` 需3000积分，第一梯队暂保留接口，数据可用性取决于实际积分等级。

### 3.2 返回字段规范

每个action返回统一Schema，在桥接层完成字段映射：

**hk_hold（北向持股）**：
```json
[
  {"trade_date": "20260528", "ts_code": "600114.SH", "hold_vol": 12345678, "hold_ratio": 0.034, "hold_value": 2.5e8},
  ...
]
```

**pledge（股权质押）**：
```json
[
  {"ts_code": "600114.SH", "pledge_date": "20260520", "pledgor": "xxx集团", "pledge_amount": 50000000, "pledge_total_ratio": 0.15, "cum_pledge_ratio": 0.35},
  ...
]
```

**share_float（限售解禁）**：
```json
[
  {"ts_code": "600114.SH", "float_date": "20260615", "float_share": 10000000, "float_ratio": 0.05, "float_type": "首发原股东限售"},
  ...
]
```

**holder_number（股东人数）**：
```json
[
  {"ts_code": "600114.SH", "end_date": "20260331", "holder_num": 45678, "holder_change": -1234},
  ...
]
```

### 3.3 ts_code格式转换

```
Tushare格式: 000001.SZ / 600001.SH
内部格式:    sz.000001 / sh.600001

桥接层: _convert_ts_code("000001.SZ") → "sz000001" (去掉点号，小写市场前缀)
         _to_tushare_code("sz000001") → "000001.SZ"
```

---

## 四、1+2降级链调整

### 调整后的降级路径

```
行情:     腾讯[1] → 新浪[B] → 必盈[13] → 缓存[C]           (不变)
K线:      Tushare[tushare] → 新浪[2] → 必盈[13] → 缓存[C]   (Tushare升为主源)
财务:     Tushare[tushare] → 东财[3] → THS → baostock[14] → 缓存[C]  (Tushare升为主源)
北向:     Tushare[tushare] → 东财季度快照[8] → 缓存[C]       (恢复日频!)
两融:     东财[12] → Tushare[tushare] → THS → 缓存[C]        (Tushare新增备源)
质押:*    Tushare[tushare] → 缓存[C]                          (新接入,独有源)
解禁:*    Tushare[tushare] → 缓存[C]                          (新接入,独有源)
股东人数:* Tushare[tushare] → 缓存[C]                         (新接入,独有源)
```

> \* 标注"仅供参考"至备源建立

### SourceRegistry 新增条目

```powershell
# core.ps1 — 新增注册项
@{ Name = "Pledge";       Primary = "Tushare"; Fallback = @();           TTLHours = 24 }
@{ Name = "ShareFloat";   Primary = "Tushare"; Fallback = @();           TTLHours = 24 }
@{ Name = "HolderNumber"; Primary = "Tushare"; Fallback = @();           TTLHours = 168 }  # 股东人数季度更新,7d刷新
@{ Name = "NorthBound";   Primary = "Tushare"; Fallback = @("EastMoney_Quarterly"); TTLHours = 24 }
@{ Name = "KLine";        Primary = "Tushare"; Fallback = @("Sina", "Biying"); TTLHours = 24 }
@{ Name = "Financial";    Primary = "Tushare"; Fallback = @("EastMoney", "THS", "Baostock"); TTLHours = 168 }
@{ Name = "Margin";       Primary = "EastMoney"; Fallback = @("Tushare", "THS"); TTLHours = 24 }
```

---

## 五、缓存策略

| 数据类型 | TTL | 理由 |
|:--------|:---|:-----|
| 北向资金(hk_hold) | 24h | 日频更新，次日更新 |
| 股权质押(pledge) | 24h | 公告频率不定，24h轮询 |
| 限售解禁(share_float) | 24h | 提前公告，日频刷新 |
| 股东人数(holder_number) | 7d(168h) | 季度报告披露，7d刷新即可 |

缓存格式与现有 `Export-DataCache` / `Import-DataCache` 兼容，存储于 `data_cache/`。

---

## 六、限速与容错

```python
# stock_data_fetcher_tushare.py
RATE_LIMIT_SEC = 0.35     # ≥300ms, 匹配全局限速器
MAX_RETRIES = 2            # 失败重试2次
RETRY_BACKOFF = 1.0        # 退避1s
```

- Tushare SDK自带超时控制，无需额外包装
- 2000积分档限额200次/分钟+100,000次/天/API，远高于当前用量（每日≤500次调用）
- 调用失败 → 自动降级到 Fallback 链的下一个源（由 `Invoke-DataSource` 处理）

---

## 七、Token影响评估

| 维度 | 评估 |
|:-----|:-----|
| 新增模板体积 | 0（CLI桥接，无新增模板文件） |
| 输出模式变化 | 0（JSON→stdout→文件，不入AI上下文） |
| API调用新增 | +4个Tushare API action，每次调用~1KB JSON（不入上下文） |
| 文档同步 | M类变更（数据字典+数据源全景），~45行，轻度 |
| **总体评估** | **零Token增量**。桥接层是纯数据通道，数据经stdout写入JSON文件，不进入AI对话 |

---

## 八、需求→代码核对清单

| # | 需求 | 实现位置 | 情墨✓ | 腰子✓ |
|:--|:-----|:--------|:-----:|:-----:|
| 1 | Tushare SDK token配置 | api_config.json + 环境变量 | | |
| 2 | hk_hold北向日频数据 | do_hk_hold() in bridge | | |
| 3 | pledge_detail股权质押 | do_pledge() in bridge | | |
| 4 | share_float限售解禁 | do_share_float() in bridge | | |
| 5 | stk_holdernumber股东人数 | do_holder_number() in bridge | | |
| 6 | ts_code格式转换 | _convert_ts_code() / _to_tushare_code() | | |
| 7 | SourceRegistry注册新源 | core.ps1 新增4条 | | |
| 8 | 降级链调整(K线/财务/两融/北向) | core.ps1 修改4条 | | |
| 9 | Invoke-TushareFallback | core.ps1 新增函数 | | |
| 10 | 限速+重试 | bridge内置 | | |
| 11 | 缓存TTL兼容 | Export-DataCache自动生效 | | |
| 12 | 数据字典更新 | 数据字典.md / 数据源全景.md | | |
| 13 | share_float 3000积分检测 | bridge启动时检查积分等级→不可用返回降级标记 | | |
| 14 | 不修改评分/交易/报告逻辑 | 设计约束 | | |
