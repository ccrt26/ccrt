---
name: craft-knowledge-03
description: API调用模式 — 腾讯/新浪/东方财富API的调用封装、批量查询、重试策略、降级触发、编码转换、频率控制、缓存集成
metadata:
  type: knowledge
  role: 红结
  version: v1.0
  created: 2026-05-23
  knowledge_id: "03"
  title: API调用模式
  dependencies: ["01-PowerShell编码规范"]
  estimated_tokens_saved: 12000
---

# 03 — API调用模式

> 红结知识库 | 编号：03 | 版本：v1.0 | 2026-05-23
> 关联角色：`.claude/agents/代码工匠-红结.md` §3.3

---

## 一、腾讯行情API (qt.gtimg.cn)

### 1.1 基本信息

| 项目 | 内容 |
|:-----|:-----|
| 主URL | `http://qt.gtimg.cn/q=` |
| 编码 | gbk（返回） |
| 频率限制 | >= 300ms/次 |
| 批量上限 | ~80只股票/次 |
| 角色 | 1+2架构中的**主源[1]** |

### 1.2 URL构建

```powershell
# 单只股票
$url = "http://qt.gtimg.cn/q=sh600519"

# 多只股票（逗号连接， ~80只）
$codes = @("sh600519", "sz000858", "sh600036", "sz002415")
$codeParam = ($codes -join ",")
$url = "http://qt.gtimg.cn/q=$codeParam"
```

### 1.3 返回格式解析

```
返回示例（单只）：
v_sh600519="1~贵州茅台~600519~1850.50~1805.00~1810.00~192638~..."

字段分隔符：~ （波浪号）
字段结构（关键字段）：
[0]  — 未知标记
[1]  — 股票名称
[2]  — 纯数字代码
[3]  — 最新价
[4]  — 昨收
[5]  — 开盘价
[6]  — 成交量(手)
...
[31] — 量比
[32] — 换手率
[33] — 市盈率(动态)  ← 注意：腾讯静态PE，项目不用
[38] — 总市值
[43] — 涨跌幅%
[45] — 市盈率(TTM)  ← 腾讯PE(TTM)，备用参考
[47] — 振幅%
```

### 1.4 解析代码

```powershell
function Parse-TencentResponse {
    param([string]$RawContent)

    $results = @()
    $lines = $RawContent -split "`n" | Where-Object { $_ -match "v_s[hz]" }

    foreach ($line in $lines) {
        if ($line -match "v_(s[hz]\d+)=\""(.+)\""") {
            $code = $Matches[1]
            $dataStr = $Matches[2]
            $fields = $dataStr -split "~"

            if ($fields.Count -lt 40) {
                Write-Log -Level "WARNING" -Message "腾讯API返回字段不足: $code (${fields.Count})" -ScriptName "Parse-TencentResponse"
                continue
            }

            $stock = [PSCustomObject]@{
                code       = $code
                name       = $fields[1]
                price      = [double]$fields[3]
                prev_close = [double]$fields[4]
                open       = [double]$fields[5]
                volume     = [long]$fields[6]
                change_pct = [double]$fields[43]
                pe_ttm     = if ($fields[45] -and $fields[45] -ne "") { [double]$fields[45] } else { $null }
                turnover   = [double]$fields[32]
            }
            $results += $stock
        }
    }
    return $results
}
```

### 1.5 批量分组策略

```powershell
function Get-BatchStockPrice {
    param([string[]]$StockCodes)

    $allResults = @()
    $batchSize = 80

    for ($i = 0; $i -lt $StockCodes.Count; $i += $batchSize) {
        $batch = $StockCodes[$i..([Math]::Min($i + $batchSize - 1, $StockCodes.Count - 1))]
        $codeParam = ($batch -join ",")
        $url = "http://qt.gtimg.cn/q=$codeParam"

        $response = Invoke-APIWithRetry -Uri $url
        $results = Parse-TencentResponse -RawContent $response
        $allResults += $results

        # 频率控制
        Start-Sleep -Milliseconds 350
    }

    return $allResults
}
```

---

## 二、新浪行情API (hq.sinajs.cn)

### 2.1 基本信息

| 项目 | 内容 |
|:-----|:-----|
| 主URL | `http://hq.sinajs.cn/list=` |
| 编码 | gbk（返回） |
| 频率限制 | >= 300ms/次 |
| 批量上限 | ~50只股票/次 |
| 角色 | 1+2架构中的**备源[B]** |

### 2.2 URL构建

```powershell
# 单只
$url = "http://hq.sinajs.cn/list=sh600519"

# 多只（逗号连接， ~50只）
$codes = @("sh600519", "sz000858", "sh600036")
$codeParam = ($codes -join ",")
$url = "http://hq.sinajs.cn/list=$codeParam"
```

### 2.3 返回格式解析

```
返回示例：
var hq_str_sh600519="贵州茅台,1850.50,1805.00,1810.00,1835.00,..."

字段分隔符：, （逗号）
字段结构：
[0]   — 股票名称
[1]   — 开盘价
[2]   — 昨收
[3]   — 最新价
[4]   — 最高价
[5]   — 最低价
[8]   — 成交量(手)
[9]   — 成交额(万)
[30]  — 日期
[31]  — 时间
[32]  — 停牌状态(03=正常)
```

### 2.4 编码处理

```powershell
# 新浪返回gbk编码，必须转换为utf-8
function Convert-GbkToUtf8 {
    param([string]$GbkString)
    $bytes = [System.Text.Encoding]::GetEncoding("gbk").GetBytes($GbkString)
    return [System.Text.Encoding]::UTF8.GetString($bytes)
}

# 使用
$rawContent = Invoke-WebRequest -Uri $url -UseBasicParsing
$utf8Content = Convert-GbkToUtf8 -GbkString $rawContent.Content
```

### 2.5 解析代码

```powershell
function Parse-SinaResponse {
    param([string]$RawContent)

    $results = @()
    $lines = $RawContent -split "`n" | Where-Object { $_ -match "hq_str_" }

    foreach ($line in $lines) {
        if ($line -match "hq_str_(s[hz]\d+)=\""(.+)\""") {
            $code = $Matches[1]
            $dataStr = $Matches[2]
            $fields = $dataStr -split ","

            if ($fields.Count -lt 30) {
                Write-Log -Level "WARNING" -Message "新浪API返回字段不足: $code" -ScriptName "Parse-SinaResponse"
                continue
            }

            $stock = [PSCustomObject]@{
                code       = $code
                name       = $fields[0]
                open       = [double]$fields[1]
                prev_close = [double]$fields[2]
                price      = [double]$fields[3]
                high       = [double]$fields[4]
                low        = [double]$fields[5]
                volume     = [long]$fields[8]
                amount     = [double]$fields[9] * 10000  # 万元→元
                date       = $fields[30]
                time       = $fields[31]
                status     = $fields[32]  # 03=正常交易
            }
            $results += $stock
        }
    }
    return $results
}
```

---

## 三、东方财富API

### 3.1 基本信息

| 项目 | 内容 |
|:-----|:-----|
| 板块资金流 | `http://push2.eastmoney.com/api/qt/clist/get` |
| 龙虎榜 | `http://data.eastmoney.com/DataCenter_V3/stock/trade_detail.html` |
| 返回格式 | JSON |
| 频率限制 | >= 500ms/次 |
| 角色 | 板块数据**主源**（无备源，降级到缓存） |

### 3.2 板块资金流调用

```python
import requests

def get_sector_flow(sector_code: str, page: int = 1, page_size: int = 100) -> dict:
    """获取东方财富板块资金流数据"""
    url = "http://push2.eastmoney.com/api/qt/clist/get"
    params = {
        "pn": page,
        "pz": page_size,
        "po": 1,
        "np": 1,
        "ut": "bd1d9ddb04089700cf9c27f6f7426281",
        "fltt": 2,
        "invt": 2,
        "fid": "f3",
        "fs": f"m:90+t2{f_sector_code}",
        "fields": "f2,f3,f4,f5,f6,f7,f8,f10,f12,f14,f15,f16,f17,f18,f20,f21",
        "_": int(time.time() * 1000),
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; TielvQuant/1.0)",
        "Referer": "http://data.eastmoney.com/",
    }
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if data.get("data") and data["data"].get("diff"):
            return data["data"]["diff"]
        else:
            logger.warning("东财板块资金流返回空数据")
            return []
    except requests.exceptions.Timeout:
        logger.error("东财板块资金流超时")
        raise DataSourceError("eastmoney", "超时")
    except requests.exceptions.RequestException as e:
        logger.error(f"东财板块资金流请求失败: {e}")
        raise DataSourceError("eastmoney", str(e))
```

### 3.3 反爬注意事项

- 必须设置 User-Agent 头（浏览器模拟）
- 部分接口需要 Referer 头
- URL中的 `_` 参数是毫秒级时间戳（防缓存）
- 盘中某些时段可能返回 `{"data": null}`（正常，非错误）
- 连续请求间隔 >= 500ms

---

## 四、通用调用模式 — 1+2架构实现

### 4.1 完整调用流程

```
                     ┌─────────────┐
                     │  请求数据    │
                     └─────┬───────┘
                           ▼
                    ┌──────────────┐
                    │ 检查本地缓存  │
                    └──────┬───────┘
                           ▼
              ┌───────────┴───────────┐
              │ 缓存新鲜?              │
              │ (TTL范围内)            │
              └───────────┬───────────┘
                    │           │
                   是           否
                    ▼           ▼
            ┌──────────┐  ┌─────────────┐
            │ 返回缓存  │  │ 调用主API    │
            │ 标注[C]   │  │ (腾讯)       │
            └──────────┘  └──────┬──────┘
                                 ▼
                    ┌────────────────────┐
                    │ 主API成功?          │
                    └────────┬───────────┘
                        │         │
                       是         否
                        ▼         ▼
                ┌──────────┐  ┌─────────────┐
                │ 解析数据  │  │ 调用备API    │
                │ 更新缓存  │  │ (新浪)       │
                │ 标注[1]   │  └──────┬──────┘
                └──────────┘         ▼
                          ┌────────────────────┐
                          │ 备API成功?          │
                          └────────┬───────────┘
                              │         │
                             是         否
                              ▼         ▼
                      ┌──────────┐  ┌──────────────┐
                      │ 解析数据  │  │ 返回过期缓存  │
                      │ 更新缓存  │  │ 标注[C]+过期  │
                      │ 标注[B]   │  └──────┬───────┘
                      └──────────┘         ▼
                                    ┌──────────────┐
                                    │ 缓存可用?     │
                                    └──┬───────┬───┘
                                     是        否
                                      ▼         ▼
                              ┌──────────┐  ┌──────┐
                              │ 返回缓存  │  │ 报错  │
                              └──────────┘  └──────┘
```

### 4.2 1+2架构PowerShell实现

```powershell
function Get-StockDataWithFallback {
    param(
        [string[]]$StockCodes,
        [string]$CacheDir = (Join-Path $PSScriptRoot "data" "cache"),
        [int]$CacheTTLMinutes = 5
    )

    $cachePath = Join-Path $CacheDir "stock_quote_cache.json"
    $scriptName = "Get-StockDataWithFallback"

    # Step 1: 检查缓存
    $cacheData = Get-CacheData -CachePath $cachePath -TTLMinutes $CacheTTLMinutes
    if ($cacheData) {
        Write-Log -Level "INFO" -Message "缓存命中，直接返回[C]" -ScriptName $scriptName
        return $cacheData
    }

    # Step 2: 调用主API（腾讯）
    try {
        $data = Get-TencentStockPrice -StockCodes $StockCodes
        if ($data -and $data.Count -gt 0) {
            Write-Log -Level "INFO" -Message "主源[1]腾讯API成功，更新缓存" -ScriptName $scriptName
            Set-CacheData -CachePath $cachePath -Data $data
            return $data
        }
    } catch {
        Write-Log -Level "WARNING" -Message "主源[1]腾讯API失败: $($_.Exception.Message)" -ScriptName $scriptName
    }

    # Step 3: 调用备API（新浪）
    try {
        $data = Get-SinaStockPrice -StockCodes $StockCodes
        if ($data -and $data.Count -gt 0) {
            Write-Log -Level "INFO" -Message "备源[B]新浪API成功，更新缓存" -ScriptName $scriptName
            Set-CacheData -CachePath $cachePath -Data $data
            return $data
        }
    } catch {
        Write-Log -Level "WARNING" -Message "备源[B]新浪API也失败: $($_.Exception.Message)" -ScriptName $scriptName
    }

    # Step 4: 返回过期缓存（兜底）
    $expiredCache = Get-CacheData -CachePath $cachePath -TTLMinutes -1  # 忽略TTL
    if ($expiredCache) {
        Write-Log -Level "WARNING" -Message "主备均失败，返回过期缓存[C](已过期)" -ScriptName $scriptName
        return $expiredCache
    }

    # Step 5: 彻底失败
    Write-Log -Level "ERROR" -Message "所有数据源均失败，无缓存可用" -ScriptName $scriptName
    throw "数据获取失败: 主API、备API、本地缓存均不可用"
}
```

---

## 五、重试策略

### 5.1 标准重试函数

```python
import time
import logging

logger = logging.getLogger(__name__)

def api_retry(func, *args, max_retries=3, base_delay=1.0, **kwargs):
    """API调用带指数退避重试
    
    Args:
        func: 要调用的函数
        *args: 位置参数
        max_retries: 最大重试次数（含首次）
        base_delay: 基础延迟（秒），实际延迟 = base_delay * 2^attempt
        **kwargs: 关键字参数
    
    Returns:
        func的返回值
    
    Raises:
        最后一次的异常（重试耗尽后）
    """
    last_exception = None
    
    for attempt in range(1, max_retries + 1):
        try:
            logger.debug(f"API调用 尝试 {attempt}/{max_retries}")
            result = func(*args, **kwargs)
            return result
        except (TimeoutError, ConnectionError, OSError) as e:
            last_exception = e
            if attempt < max_retries:
                delay = base_delay * (2 ** (attempt - 1))  # 1s, 2s, 4s
                logger.warning(f"API调用失败 尝试{attempt}: {e} — 等待{delay}s后重试")
                time.sleep(delay)
            else:
                logger.error(f"API调用失败，已重试{max_retries}次: {e}")
        except Exception as e:
            # 非网络异常不重试（如数据解析错误）
            logger.error(f"API调用致命错误: {e}")
            raise
    
    raise last_exception
```

### 5.2 重试规则

- **网络超时 / 连接错误**：重试（3次，指数退避）
- **HTTP 429 (限流)**：重试且增加等待时间
- **HTTP 4xx (客户端错误)**：不重试（URL/参数错误）
- **HTTP 5xx (服务端错误)**：重试1次
- **数据解析错误**：不重试（数据格式变了，重试没用）
- **编码错误**：不重试，尝试换编码方式

---

## 六、频率控制

### 6.1 PowerShell实现

```powershell
# 全局频率控制
$script:LastAPICall = [datetime]::MinValue

function Wait-APIFrequency {
    param([int]$MinIntervalMs = 300)

    $elapsed = ([datetime]::Now - $script:LastAPICall).TotalMilliseconds
    if ($elapsed -lt $MinIntervalMs) {
        $waitMs = $MinIntervalMs - $elapsed
        Write-Log -Level "DEBUG" -Message "频率控制: 等待 ${waitMs}ms" -ScriptName "频率控制"
        Start-Sleep -Milliseconds $waitMs
    }
    $script:LastAPICall = [datetime]::Now
}

# 使用
Wait-APIFrequency -MinIntervalMs 300
$response = Invoke-WebRequest -Uri $url -UseBasicParsing
```

### 6.2 Python实现

```python
import time

class APIRateLimiter:
    """API频率限制器"""
    
    def __init__(self, min_interval_ms: int = 300):
        self.min_interval = min_interval_ms / 1000.0
        self.last_call = 0.0
    
    def wait(self):
        """等待直到满足频率限制"""
        now = time.time()
        elapsed = now - self.last_call
        if elapsed < self.min_interval:
            wait_time = self.min_interval - elapsed
            logger.debug(f"频率控制: 等待 {wait_time*1000:.0f}ms")
            time.sleep(wait_time)
        self.last_call = time.time()

# 全局单例
rate_limiter = APIRateLimiter(min_interval_ms=300)
```

### 6.3 各API频率限制表

| API | 最小间隔 | 说明 |
|:----|:-------:|:-----|
| 腾讯 qt.gtimg.cn | 300ms | 频繁调用会暂时封IP |
| 新浪 hq.sinajs.cn | 300ms | 相对宽松 |
| 东方财富 push2 | 500ms | 反爬策略较严 |

---

## 七、缓存集成

### 7.1 缓存数据结构

```json
{
  "meta": {
    "created_at": "2026-05-23 15:30:00",
    "source": "tencent_api[1]",
    "ttl_minutes": 5,
    "stock_count": 500
  },
  "data": {
    "sh600519": {
      "code": "sh600519",
      "name": "贵州茅台",
      "price": 1850.50,
      "change_pct": 2.35,
      "volume": 12500000
    }
  }
}
```

### 7.2 缓存新鲜度判断

```powershell
function Test-CacheFreshness {
    param(
        [string]$CachePath,
        [int]$TTLMinutes = 5
    )

    if (-not (Test-Path $CachePath)) {
        return $false
    }

    $lastWrite = (Get-Item $CachePath).LastWriteTime
    $age = [datetime]::Now - $lastWrite

    if ($age.TotalMinutes -gt $TTLMinutes) {
        Write-Log -Level "INFO" -Message "缓存已过期: ${age.TotalMinutes:F1}分钟 > ${TTLMinutes}分钟TTL" -ScriptName "缓存"
        return $false
    }

    return $true
}
```

### 7.3 缓存TTL对照表

| 数据类型 | TTL | 原因 |
|:---------|:--:|:-----|
| 实时行情 | 5分钟 | 盘中价格持续变化 |
| 板块资金流 | 10分钟 | 变化速度较慢 |
| 财务数据 | 24小时 | 每日更新一次 |
| 龙虎榜 | 收盘后固定 | 当日不变 |
| K线数据 | 15分钟(盘中) / 收盘后到次日 | 盘中更新慢 |

---

## 八、错误码与异常处理

### 8.1 腾讯API异常返回

```powershell
# 正常返回包含股票数据
v_sh600519="1~贵州茅台~..."

# 异常返回（停牌/无效代码）
v_shxxxxxx=""  # 空字符串 — 可能是无效代码或停牌

# 特殊情况
# 腾讯API返回的股票数据中某字段为空字符串 — 该字段置null而非报错
```

### 8.2 新浪API异常返回

```powershell
# 正常返回
hq_str_sh600519="贵州茅台,1850.50,..."

# 异常返回（停牌）
hq_str_sh600519=""  # 空

# 异常返回（无效代码）
# 返回无此代码的行，或返回全空值
```

### 8.3 东方财富异常返回

```json
// 正常
{"rc":0, "data": {"diff": [...], "total": 100}}

// 盘中暂无数据（正常现象）
{"rc":0, "data": null}

// 错误
{"rc":-1, "message": "参数错误"}
```

### 8.4 异常分类处理

| 异常情况 | 分类 | 处理 |
|:---------|:----:|:-----|
| 网络超时 | ERROR → 重试 → 切换备源 | 重试3次 → 切新浪 |
| HTTP 4xx | ERROR → 不重试 | 检查URL/参数 |
| HTTP 5xx | ERROR → 重试1次 → 切换备源 | 短暂故障，等1秒重试 |
| 返回空数据 | WARNING | 标记"数据不可获取" |
| 返回格式变化 | ERROR | 记录原始返回，通知人工 |
| 编码错误 | WARNING | 尝试自动检测编码 |
| 限流(429) | ERROR → 重试 | 等待5秒后重试 |

---

> **文件版本**: v1.0 | **创建日期**: 2026-05-23 | **所属**: 铁律量化 · 红结知识库 · 03-API调用模式
