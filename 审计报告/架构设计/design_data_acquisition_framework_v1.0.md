# 统一数据获取框架 — 架构设计

> 情墨 | 阶段① 设计交付物 | 2026-05-25
> pipeline_stage: complete
> finance_confirmed: true
> 腰子确认: 2026-05-25 | 全团咨询通过(山猫/玉夜/流金/青山一致同意) | 3条非阻塞建议见§十
> 代码等级: L1 (数据源/策略层)

---

## 一、背景与动机

### 1.1 当前问题

经过必盈API[13]集成 + AKShare[THS]备源扩展，数据层从最初3个模块膨胀到5个模块（core / financial / external / fundflow / biying），但**每个模块的降级逻辑是各自手写的，模式不一致**。

| 模块 | 缓存策略 | 字段校验 | 降级深度 | THS桥接 |
|:-----|:--------|:--------|:--------|:-------|
| financial.ps1 | Cache-first (168h) | P0-1校验 | 3级(东财→THS→必盈→过期缓存) | ✓ |
| external.ps1 | Cache-first (24h) | 无 | 2级(东财→THS→过期缓存) | ✓ |
| fundflow.ps1 | Cache-first (24h) | 无 | 1级(东财→缓存) 混用 | 部分 |
| biying.ps1 | N/A (API wrapper) | 无 | N/A (叶子模块) | N/A |

**5个具体问题**：

1. **模式不一致**：financial做了字段校验(P0-1)，external和fundflow没做。fundflow的Get-StockFundFlow没有THS回退，但Get-SectorFundFlow有。
2. **代码重复**：过期缓存兜底(720h TTL)的Write-Warning+Load-DataCache模式在6处复制粘贴。
3. **SourceUsed追踪散落**：每个函数手动设置`$script:SourceUsed["xxx"]`，容易遗漏。
4. **Invoke-DataWithCache闲置**：core.ps1已定义此通用包装器，但只有biying.ps1间接使用。
5. **无新增规范**：新增数据源时没有模板/契约/检查清单，靠复制粘贴现有模块。

### 1.2 设计目标

- **一致性**：所有数据获取函数遵循同一条降级链，行为可预测
- **可扩展**：新增数据源只需声明源配置+写API调用，框架处理缓存/降级/追踪
- **可观测**：每次调用的源使用记录自动追踪，降级事件有日志
- **不破坏现有**：重构后所有现有调用方无需修改

---

## 二、框架架构

### 2.1 三层模型

```
┌──────────────────────────────────────────────────────┐
│               L3: 数据函数层 (Data Functions)          │
│  Get-StockQuote / Get-StockFinancial / Get-MarginData │
│  → 声明源链 + 写API调用块, 其余交给L2                  │
└────────────────────────┬─────────────────────────────┘
                         │ 调用
┌────────────────────────▼─────────────────────────────┐
│            L2: 降级引擎 (Fallback Engine)              │
│  Invoke-DataSource — 统一降级链:                       │
│  缓存检查 → 主源API → 字段校验 → 备源API →             │
│  字段映射 → 新鲜缓存 → 过期缓存兜底                     │
│  → 自动追踪 SourceUsed + 输出降级日志                   │
└────────────────────────┬─────────────────────────────┘
                         │ 依赖
┌────────────────────────▼─────────────────────────────┐
│          L1: 基础设施 (Infrastructure)                  │
│  Source Registry / Cache TTL / Rate Limiter /          │
│  THS Bridge / BiyingAPI wrapper                        │
│  → 纯配置+工具, 不感知具体数据类别                       │
└──────────────────────────────────────────────────────┘
```

### 2.2 核心抽象：Invoke-DataSource

这是框架的核心引擎，替换当前各模块手写的降级逻辑。

**输入参数**：

| 参数 | 类型 | 必填 | 说明 |
|:-----|:----:|:----:|:-----|
| Category | string | 是 | 数据类别(Quote/KLine/Financial/FundFlow/...) |
| Code | string | 是 | 股票代码 |
| CacheKey | string | 是 | 缓存键(如"Financial_000001") |
| PrimaryCall | scriptblock | 是 | 主源API调用块，返回数据或$null |
| BackupCall | scriptblock | 否 | 备源API调用块(可为多层嵌套) |
| ValidateBlock | scriptblock | 否 | 字段校验块，返回$true/$false |
| FieldMap | hashtable | 否 | 备源→主源字段映射表 |
| CacheTTL | int | 否 | 缓存TTL(小时)，覆盖Source Registry默认值 |

**引擎执行流程**：

```
1. 检查新鲜缓存 → 命中则直接返回, SourceUsed="缓存"
2. 执行 PrimaryCall
   ├─ 成功 → ValidateBlock(可选)
   │        ├─ 通过 → Save-DataCache, SourceUsed=主源名, 返回
   │        └─ 不通过 → 记录WARNING, 进入步骤3
   └─ 失败 → 记录WARNING, 进入步骤3
3. 执行 BackupCall (若提供)
   ├─ 成功 → FieldMap(可选), Save-DataCache, SourceUsed=备源名, 返回
   └─ 失败 → 记录WARNING, 进入步骤4
4. 过期缓存兜底
   ├─ Load-DataCache(TTL=720h) → 命中, SourceUsed="过期缓存", 返回
   └─ 不命中 → SourceUsed="失败", 返回$null
```

**与现有Invoke-DataWithCache的关系**：
- 现有`Invoke-DataWithCache`是简化版(API→缓存, 无校验/无备源/无过期兜底)
- 新版`Invoke-DataSource`是其超集, 新增: 字段校验 + 备源链 + 过期缓存兜底 + SourceUsed自动追踪
- `Invoke-DataWithCache`保留给简单场景(如PE百分位、可比公司等L0级数据)
- `Invoke-DataSource`用于所有L1/L2级数据(行情/K线/财务/资金/研报/融资融券)

---

## 三、源注册表 (Source Registry)

### 3.1 设计

将当前`$script:SourcePriority`从简单数组升级为结构化注册表：

```
SourceRegistry = {
    "Financial": {
        primary:   { name="东方财富", call=Get-EastMoneyFinancial, rateLimit=300ms },
        backups:   [
            { name="同花顺",   call=Invoke-ThsFallback("financial"), fieldMap=ths_field_map },
            { name="必盈[13]", call=Get-BiyingFinancial,              fieldMap=biying_field_map }
        ],
        cacheTTL:  168,
        validate:  { fields=("BASIC_EPS","TOTAL_OPERATE_INCOME"), rules=(">0") },
        tier:      3
    },
    "Margin": {
        primary:   { name="东方财富", call=Get-EastMoneyMargin },
        backups:   [{ name="同花顺", call=Invoke-ThsFallback("margin_detail") }],
        cacheTTL:  24,
        tier:      2
    },
    ...
}
```

### 3.2 新增数据源只需声明

新增一个数据类别时，只需在注册表中添加一条记录 + 写API调用函数。不需要写缓存逻辑、降级逻辑、过期兜底——这些都交给引擎。

### 3.3 注册表自身作为文档

注册表即文档：一眼可看到每类数据的主源/备源/缓存TTL/校验规则。无需翻4个.ps1文件。

---

## 四、接口契约 I9：数据函数契约

### 4.1 调用方契约（外部→数据函数）

每个数据获取函数签名统一为：

```
function Get-<Category>Data {
    param(
        [Parameter(Mandatory)]  [string]$Code,
        [Parameter(Mandatory=$false)] [int]$Days = 5,
        [Parameter(Mandatory=$false)] [int]$Count = 5,
        ...
    )
    → 返回 PSCustomObject | PSCustomObject[] | $null
}
```

约定：
- 第一个参数始终是 `$Code`（股票代码，6位数字字符串）
- 返回 `$null` 表示所有源均失败（调用方自行处理）
- 不抛异常（内部全部 catch 并 Write-Warning）

### 4.2 引擎契约（数据函数→引擎）

数据函数内部调用 `Invoke-DataSource`，提供：

```
Invoke-DataSource -Category "Financial" `
    -Code $Code `
    -CacheKey "Financial_$Code" `
    -PrimaryCall { Get-EastMoneyFinancial -Code $Code } `
    -BackupCall {
        # 第一备源
        $ths = Invoke-ThsFallback -Action "financial" -Params "--code $Code"
        if ($ths) { return $ths }
        # 第二备源
        $biying = Get-BiyingFinancial -Code $Code
        if ($biying) { return ConvertFrom-BiyingFieldMap $biying }
        return $null
    } `
    -ValidateBlock { param($data) $data.BASIC_EPS -gt 0 }
```

### 4.3 追踪契约

引擎自动维护 `$script:SourceUsed[$Category]`，无需数据函数手动设置。可选值：
- `"东方财富"` / `"腾讯"` / `"新浪"` — 主源成功
- `"同花顺[THS]"` / `"必盈[13]"` — 备源成功
- `"缓存[C]"` — 新鲜缓存命中
- `"过期缓存[C]"` — 过期缓存兜底
- `"失败"` — 全部不可用

---

## 五、文件变更计划

### 5.1 修改文件

| 文件 | 变更 | 等级 |
|:-----|:-----|:----:|
| `代码文件/每日荐股/scripts/modules/core.ps1` | 新增 `Invoke-DataSource` 引擎 + Source Registry | L1 |
| `代码文件/每日荐股/scripts/modules/financial.ps1` | Get-StockFinancial 改为调用 Invoke-DataSource | L1 |
| `代码文件/每日荐股/scripts/modules/external.ps1` | Get-MarginData / Get-StockResearch / Get-NorthboundHold 改为调用 Invoke-DataSource | L1 |
| `代码文件/每日荐股/scripts/modules/fundflow.ps1` | Get-StockFundFlow / Get-SectorFundFlow 改为调用 Invoke-DataSource | L1 |

### 5.2 不变文件

| 文件 | 原因 |
|:-----|:-----|
| `biying.ps1` | API wrapper 层，不直接参与降级链，保持不变 |
| `stock_data_fetcher_ths.py` | Python 桥接层，接口稳定，保持不变 |
| `stock_data_fetcher.psm1` | 模块入口，dot-source 顺序可能需要调整 |
| 所有调用方 | 函数签名不变，返回值格式不变，无需修改 |

### 5.3 不新增文件

框架代码全部放入 `core.ps1`（约+80行），不新建独立文件。理由：
- 降级引擎与缓存/限流/THS桥接在同一个基础设施层
- 拆出独立文件增加 dot-source 顺序依赖
- 单文件行数仍在500行限制内（当前170行 + 80行 = 250行）

---

## 六、影响评估

### 6.1 下游影响

| 调用方 | 影响 | 说明 |
|:-------|:----:|:-----|
| scoring_engine_v2.py | 无 | 读取缓存JSON，不感知源 |
| gen_daily_html.ps1 | 无 | 读取评分JSON，不感知源 |
| sim_trading.ps1 | 无 | 调用现有函数签名不变 |
| build_dynamic_pool.ps1 | 无 | 同上 |
| financial_mcp_server.py | 无 | 读缓存文件 |

### 6.2 风险评级

| 维度 | 评级 | 理由 |
|:-----|:----:|:-----|
| 改动风险 | 🟡 R2-中风险 | 影响4个数据模块，但函数签名不变，调用方无感 |
| 回退难度 | 🟢 低 | git revert 即可，无数据迁移 |
| 测试覆盖 | 🟡 需要验证 | 需新安逐模块验证降级链行为一致 |
| 红线合规 | 🟢 通过 | 不改变数据真实性，1+2架构增强而非削弱 |

---

## 七、回退方案

1. `git revert` 本次提交，恢复到当前手写降级逻辑
2. 所有调用方无需任何适配（函数签名不变）
3. 回退窗口：部署后7天内

---

## 八、需求→代码核对清单

> 情墨 + 腰子 共同勾签后放行至红结

| # | 需求 | 对应实现位置 | 情墨 | 腰子 |
|:-:|:-----|:-----------|:----:|:----:|
| 1 | 统一降级引擎 Invoke-DataSource | core.ps1 新增函数 | ☐ | ☐ |
| 2 | Source Registry 结构化注册表 | core.ps1 $script:SourceRegistry | ☐ | ☐ |
| 3 | 自动 SourceUsed 追踪 | Invoke-DataSource 内部 | ☐ | ☐ |
| 4 | 过期缓存兜底统一(720h) | Invoke-DataSource 步骤4 | ☐ | ☐ |
| 5 | financial.ps1 接入引擎 | Get-StockFinancial 重构 | ☐ | ☐ |
| 6 | external.ps1 接入引擎 | Get-MarginData/Get-StockResearch/Get-NorthboundHold 重构 | ☐ | ☐ |
| 7 | fundflow.ps1 接入引擎 | Get-StockFundFlow/Get-SectorFundFlow 重构 | ☐ | ☐ |
| 8 | 函数签名不变，调用方无感 | 所有重构函数保持原参数+返回值格式 | ☐ | ☐ |
| 9 | 源注册表本身即文档 | 注册表字段含 name/call/fieldMap/cacheTTL/validate/tier | ☐ | ☐ |

---

## 九、情墨 12项自查

| # | 审查项 | 结果 | 备注 |
|:-:|:-------|:----:|:-----|
| CH1 | 模块边界清晰 | ✅ | 三层模型：基础设施→降级引擎→数据函数 |
| CH2 | 接口完整 | ✅ | I9契约定义了函数签名/引擎参数/返回值规范 |
| CH3 | 1+2架构 | ✅ | 引擎强制执行主→备→缓存降级链 |
| CH4 | 第三方依赖 | ✅ | 无新增 |
| CH5 | 循环依赖 | ✅ | core.ps1←modules.ps1 单向，无新增环 |
| CH6 | 单点故障 | ✅ | 过期缓存兜底确保即使所有API都挂也有最后手段 |
| CH7 | 反模式 | ✅ | 消除AP-06(代码重复)，不触发其他 |
| CH8 | 影响范围 | ✅ | §六已列出所有下游，均无影响 |
| CH9 | API超时/限流 | ✅ | 复用现有限速器+超时设置 |
| CH10 | 回退方案 | ✅ | §七 git revert |
| CH11 | 通知关联 | ⚠️ | 实施后需通知玉夜（数据监理）确认降级链 |
| CH12 | 红线合规 | ✅ | 不触发任何红线违规 |

---

## 十、腰子闸门1a — 全团咨询建议（非阻塞）

> 2026-05-25 | 山猫→玉夜→流金→青山 一致通过

| # | 来源 | 建议 | 采纳 | 说明 |
|:-:|:----:|:-----|:----:|:-----|
| 1 | 山猫 | 交易日感知：非交易日自动延长缓存TTL | 后续迭代 | 不影响当前设计，框架预留交易日参数位 |
| 2 | 流金 | 过期缓存数据标记 `IsStale=$true` | **红结实现** | 让下游风控模块可拒绝基于过期数据的决策 |
| 3 | 青山 | PE百分位TTL从168h调整为72h | **红结实现** | 市场快速波动场景下7天TTL偏长 |

### 八、核对清单 腰子勾签

| # | 需求 | 情墨 | 腰子 |
|:-:|:-----|:----:|:----:|
| 1 | 统一降级引擎 Invoke-DataSource | ✅ | ✅ |
| 2 | Source Registry 结构化注册表 | ✅ | ✅ |
| 3 | 自动 SourceUsed 追踪 | ✅ | ✅ |
| 4 | 过期缓存兜底统一(720h) | ✅ | ✅ |
| 5 | financial.ps1 接入引擎 | ✅ | ✅ |
| 6 | external.ps1 接入引擎 | ✅ | ✅ |
| 7 | fundflow.ps1 接入引擎 | ✅ | ✅ |
| 8 | 函数签名不变，调用方无感 | ✅ | ✅ |
| 9 | 源注册表本身即文档 | ✅ | ✅ |

---

> **下一步**：新安+旧影审查（闸门1b）→ 红结编码
