# 资金流多源备份架构设计 — 四源降级链

> 情墨 | 阶段① 设计交付物 | 2026-05-25
> pipeline_stage: complete
> 代码等级: L1 (数据源/策略层)

---

## 一、背景与问题

### 1.1 当前缺口

`Get-StockFundFlow`（个股资金流向日K线）当前是 **1+0 架构**，无备源：

| 层级 | 源 | 5/25状态 |
|:----:|:---|:--------|
| 主源 | 东方财富[9] push2.eastmoney.com | 全量503 |
| 备源 | — | **不存在** |
| 兜底 | data_cache | 无历史缓存 |

`fundflow.ps1:16-41` 调用 `Invoke-DataSource` 时未传 `-BackupCall`。THS桥接仅有 `sector_fund_flow`（行业级），无个股资金流。必盈免费版明确不含此接口（`core.ps1:31`）。

### 1.2 目标

接入4家商业API作为个股资金流的降级备源链，将 FundFlow 数据类别从 1+0 升级为 1+4+1（主源 + 4备源 + 缓存兜底）。

---

## 二、目标架构

### 2.1 降级链

```
Get-StockFundFlow(Code, Days=5)
  │
  ├─[1] 缓存检查 (TTL=24h)
  │
  ├─[2] 主源: 东方财富[9] push2.eastmoney.com
  │     └─ 失败/503 → 降级
  │
  ├─[3] 备源1: 迪雅数据 [B1] (699元/年, 500次/天免费)
  │     └─ 失败 → 降级
  │
  ├─[4] 备源2: 麦蕊智数 [B2] (799元/年, 300次/天免费)
  │     └─ 失败 → 降级
  │
  ├─[5] 备源3: 智兔数服 [B3] (899元/年, 1000次/天免费, 无需注册)
  │     └─ 失败 → 降级
  │
  ├─[6] 备源4: StockTV [B4] (999元/年, 200次/天免费)
  │     └─ 失败 → 降级
  │
  └─[7] 过期缓存兜底 (TTL=720h, IsStale标记)
```

### 2.2 设计决策：引擎不扩展，BackupCall内链

**决策**：不修改 `Invoke-DataSource` 引擎签名。4备源链在 `-BackupCall` scriptblock 内部实现顺序尝试。

**理由**：
1. **零引擎变更风险**。`Invoke-DataSource` 是 L1 核心引擎，5/25刚上线v1.0。当前 `-BackupCall` 参数已支持任意 scriptblock，嵌套链完全在其能力范围内。
2. **隔离性好**。4个备源中任一故障不影响其他。每个备源的异常被独立捕获。
3. **未来可收敛**。若多源备份模式在 ≥3 个数据类别复用，再抽象 `-BackupChain` 参数到引擎层。当前仅 FundFlow 一个类别需要，不过早抽象。

```
-BackupCall {
    # 备源链: 迪雅 → 麦蕊 → 智兔 → StockTV
    $chain = @(
        @{Name="迪雅数据[B1]"; Call={ Invoke-DiyaFundFlow -Code $Code -Days $Days }},
        @{Name="麦蕊智数[B2]"; Call={ Invoke-MaireiFundFlow -Code $Code -Days $Days }},
        @{Name="智兔数服[B3]"; Call={ Invoke-ZhituFundFlow -Code $Code -Days $Days }},
        @{Name="StockTV[B4]"; Call={ Invoke-StockTVFundFlow -Code $Code -Days $Days }}
    )
    foreach ($b in $chain) {
        try {
            $result = & $b.Call
            if ($result -and $result.Count -gt 0) {
                $script:SourceUsed["FundFlow"] = $b.Name
                return $result
            }
        } catch { Write-Warning "[资金流] $($b.Name) 失败: $_" }
    }
    return $null
}
```

---

## 三、备源API详细设计

### 3.1 统一桥接模式

每个备源一个独立Python桥接脚本，遵循THS桥接的已有模式：

```
代码文件/每日荐股/scripts/
  stock_data_fetcher_diya.py      # 迪雅数据桥接
  stock_data_fetcher_mairei.py    # 麦蕊智数桥接
  stock_data_fetcher_zhitu.py     # 智兔数服桥接
  stock_data_fetcher_stocktv.py   # StockTV桥接
```

每个桥接脚本：
- 接受 CLI 参数：`python stock_data_fetcher_<name>.py fund_flow --code 000001 --days 5`
- 输出 JSON 到 stdout（UTF-8）
- 返回格式与东方财富[9]对齐：

```json
[
  {"Date": "2026-05-25", "MainNetInflow": 1234567.0, "SuperLargeIn": 500000.0, "LargeIn": 300000.0, "SmallIn": -200000.0},
  ...
]
```

### 3.2 各源字段映射

**目标字段（东方财富格式）**：

| 目标字段 | 类型 | 说明 |
|:---------|:----:|:-----|
| Date | string | yyyy-MM-dd |
| MainNetInflow | double | 主力净流入(元) |
| SuperLargeIn | double | 超大单净流入(元) |
| LargeIn | double | 大单净流入(元) |
| SmallIn | double | 小单净流入(元) |

**迪雅数据**（接口结构与必盈高度相似）：

| 迪雅字段 | → 目标字段 | 备注 |
|:---------|:-----------|:----|
| date | Date | 日期格式待确认 |
| main_net_inflow / zljlr | MainNetInflow | 字段名待API文档确认 |
| super_large / cdd | SuperLargeIn | |
| large / dd | LargeIn | |
| small / xd | SmallIn | |

**麦蕊智数**（Python SDK 完善）：

| 麦蕊字段 | → 目标字段 |
|:---------|:-----------|
| trade_date | Date |
| main_net_flow | MainNetInflow |
| huge_order_flow | SuperLargeIn |
| big_order_flow | LargeIn |
| small_order_flow | SmallIn |

**智兔数服**（免费额度最大，无需注册）：

| 智兔字段 | → 目标字段 |
|:---------|:-----------|
| 待API文档确认 | — |

**StockTV**（多市场，REST API）：

| StockTV字段 | → 目标字段 |
|:------------|:-----------|
| 待API文档确认 | — |

> **注**：迪雅和麦蕊的字段映射基于用户提供的覆盖率描述推断。实际字段名需在红结编码阶段通过API文档/免费测试确认。智兔和StockTV需要在编码前获取API文档。所有映射不确性在闸门2编码阶段消解。

### 3.3 调用规范

每个桥接的 PowerShell 调用包装：

```powershell
function Invoke-DiyaFundFlow {
    param([string]$Code, [int]$Days = 5)
    $script = Join-Path $PSScriptRoot "../stock_data_fetcher_diya.py"
    if (-not (Test-Path $script)) { return $null }
    try {
        $tmpFile = [System.IO.Path]::GetTempFileName()
        cmd /c "python `"$script`" fund_flow --code $Code --days $Days > `"$tmpFile`""
        if ((Test-Path $tmpFile) -and ((Get-Item $tmpFile).Length -gt 0)) {
            $raw = [System.IO.File]::ReadAllText($tmpFile, [System.Text.Encoding]::UTF8)
            Remove-Item $tmpFile -Force -ErrorAction SilentlyContinue
            if ($raw.Trim().Length -gt 0) {
                $parsed = $raw | ConvertFrom-Json
                if ($parsed -is [array] -and $parsed.Count -gt 0 -and $parsed[0].error) {
                    Write-Warning "迪雅返回错误: $($parsed[0].error)"
                    return $null
                }
                return $parsed
            }
        }
        Remove-Item $tmpFile -Force -ErrorAction SilentlyContinue
    } catch { Write-Warning "迪雅桥接失败: $_" }
    return $null
}
```

其他三个源的包装函数结构相同，仅名称和脚本路径不同。

---

## 四、SourceRegistry 更新

```powershell
FundFlow = @{
    Tier = 2
    CacheTTL = 24
    Primary = @{ Name = "东方财富[9]"; Call = $null }
    Backups = @(
        @{ Name = "迪雅数据[B1]"; Call = $null },
        @{ Name = "麦蕊智数[B2]"; Call = $null },
        @{ Name = "智兔数服[B3]"; Call = $null },
        @{ Name = "StockTV[B4]"; Call = $null }
    )
    Validate = $null
}
```

---

## 五、影响范围

### 5.1 变更清单

| 文件 | 操作 | 等级 | 预计行数 |
|:-----|:----:|:----:|:-------:|
| `scripts/modules/core.ps1` | 修改 SourceRegistry.FundFlow | L1 | +3行 |
| `scripts/modules/fundflow.ps1` | 修改 Get-StockFundFlow BackupCall + 4个包装函数 | L1 | +120行 |
| `scripts/stock_data_fetcher_diya.py` | **新增** 迪雅桥接 | L1 | ~60行 |
| `scripts/stock_data_fetcher_mairei.py` | **新增** 麦蕊桥接 | L1 | ~60行 |
| `scripts/stock_data_fetcher_zhitu.py` | **新增** 智兔桥接 | L1 | ~60行 |
| `scripts/stock_data_fetcher_stocktv.py` | **新增** StockTV桥接 | L1 | ~60行 |

### 5.2 下游影响

| 下游模块 | 影响 |
|:---------|:----:|
| scoring_engine_v2.py | ✅ 无影响（返回值格式不变） |
| batch_data_collector.ps1 | ✅ 无影响（函数签名不变） |
| build_dynamic_pool.ps1 | ✅ 无影响 |
| gen_daily_html.ps1 | ✅ 无影响 |
| sim_trading.ps1 | ✅ 无影响 |

### 5.3 回滚方案

`git revert` 单次提交即可。4个桥接脚本均为新增文件，不影响现有功能。

---

## 六、设计决策记录

| 决策 | 选择 | 备选 | 理由 |
|:-----|:----:|:-----|:-----|
| 备源调用模式 | BackupCall内链 | 扩展引擎-BackupChain | 零引擎变更, 仅FundFlow需要多源 |
| 桥接语言 | Python | PowerShell | 与THS桥接模式一致, 第三方API通常有Python SDK |
| 桥接粒度 | 每源一文件 | 单文件多源 | 故障隔离, 单源问题不波及其他 |
| 备源顺序 | 迪雅→麦蕊→智兔→StockTV | — | 用户指定: 按必盈相似度+免费额度排序 |
| API密钥管理 | 环境变量 | 配置文件 | 与必盈BIYING_LICENCE模式一致 |
| 字段映射 | 桥接层内部映射 | 引擎FieldMap | 每个源的字段名不同, 统一在桥接输出时对齐 |

---

## 七、风险与缓释

| 风险 | 概率 | 影响 | 缓释 |
|:-----|:----:|:----:|:-----|
| API字段名与文档不符 | 中 | 低 | 麦蕊有Python SDK可先验证字段；迪雅可免费测试 |
| 免费额度不足（4源均耗尽） | 低 | 低 | 备源仅东方财富故障时触发，常规日不消耗 |
| 桥接Python依赖冲突 | 低 | 中 | 每个桥接独立，不共享依赖；使用标准库+requests |
| 智兔/StockTV无Python SDK | 中 | 低 | REST API直接requests调用，无需SDK |

---

## 八、需求→代码核对清单

> 情墨+腰子共同勾签后放行至红结编码

| # | 需求 | 实现位置 | 情墨 | 腰子 |
|:--|:-----|:---------|:----:|:----:|
| F1 | 迪雅数据资金流可用作备源 | stock_data_fetcher_diya.py | ☐ | ☐ |
| F2 | 麦蕊智数资金流可用作备源 | stock_data_fetcher_mairei.py | ☐ | ☐ |
| F3 | 智兔数服资金流可用作备源 | stock_data_fetcher_zhitu.py | ☐ | ☐ |
| F4 | StockTV资金流可用作备源 | stock_data_fetcher_stocktv.py | ☐ | ☐ |
| F5 | 4源按序降级: 迪雅→麦蕊→智兔→StockTV | fundflow.ps1 BackupCall | ☐ | ☐ |
| F6 | 每个备源失败不阻断后续备源 | fundflow.ps1 try/catch | ☐ | ☐ |
| F7 | 返回值格式与东方财富[9]一致 | 各桥接脚本字段映射 | ☐ | ☐ |
| F8 | SourceUsed正确记录当前使用的备源名 | fundflow.ps1 | ☐ | ☐ |
| F9 | API密钥从环境变量读取 | 各桥接脚本 | ☐ | ☐ |
| F10 | 不改变Get-StockFundFlow函数签名 | fundflow.ps1 | ☐ | ☐ |
| F11 | 不改变下游调用方 | — | ☐ | ☐ |
| F12 | SourceRegistry.FundFlow.Backups更新 | core.ps1 | ☐ | ☐ |

---

> 情墨阶段①完成 | pipeline_stage: complete | 待腰子闸门1a确认
