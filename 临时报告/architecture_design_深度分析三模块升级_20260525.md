# 深度分析三模块升级 — 架构设计文档

> **阶段**: ① 情墨架构设计 | **日期**: 2026-05-25
> **需求来源**: 腰子（豆包反馈优化→6项中3项E类需求）
> **设计人**: 情墨 | **审核**: 待新安 | **确认**: 待腰子

---

## 一、需求概述

腰子提出3个E类需求，涉及深度分析报告的数据采集和估值分析能力升级：

| 编号 | 需求 | 优先级 | 核心目标 |
|:---:|:------|:---:|:--------|
| R1 | 财务数据管线补充 | P0 | 深度分析时拉取资产负债率/流动比率/速动比率/有息负债/应收周转/存货周转 |
| R2 | 估值模块升级 | P1 | 三情景EPS预测 + 可比公司估值表 + 多方法交叉验证 |
| R3 | 资金面数据补充 | P1 | 龙虎榜 + 北向资金持仓变化 + 机构调研记录 |

---

## 二、现有架构分析

### 2.1 数据流现状

```
[东方财富API] → financial.ps1/Get-StockFinancial → JSON缓存 → AI读取 → 报告
[东方财富API] → fundflow.ps1/Get-StockFundFlow   → JSON缓存 → AI读取 → 报告
[东方财富API] → fundflow.ps1/(北向资金stub)       → JSON缓存 → AI读取 → 报告
```

### 2.2 关键发现

**R1**: `financial.ps1` 已使用 `columns=ALL` 拉取东方财富API全字段，
代码第32行已检查 `DEBT_ASSET_RATIO`，说明资产负债率数据**已在API响应中**，
只是没有提取和透传。其他字段（流动比率、速动比率等）需确认API返回字段名后补充提取。

**R2**: 当前深度分析报告的估值部分由AI手工计算（单点PE估值 + Q1年化EPS），
没有自动化三情景模型。可比公司数据需要新增API查询（东方财富行业成分股 + 财务指标）。

**R3**: `fundflow.ps1` 第140行已有北向资金API注释，但实现为stub。
龙虎榜和机构调研需要新增API端点。

---

## 三、模块等级标注

| 模块 | 等级 | 理由 | 审核路径 |
|:-----|:---:|:-----|:--------|
| 财务比率提取 (R1) | **L0** | 纯数据提取，不改逻辑，不改接口签名 | 红结自查 + 新安常规 |
| 资金面API新增 (R3) | **L0** | 新增数据源，不改变评分/交易/风控逻辑 | 红结自查 + 新安常规 |
| 三情景估值模型 (R2) | **L1** | 影响估值分析结论，属策略/评分维度 | 情墨复审 + 新安全量 + Golden Master |
| 可比公司查询 (R2) | **L0** | 纯数据查询，不改变评分逻辑 | 红结自查 + 新安常规 |

> L1模块（三情景估值）走完整L1审核路径，其余L0模块红结自查即可。

---

## 四、详细设计

### 4.1 R1: 财务数据管线补充

**现状**:
```powershell
# financial.ps1: Get-StockFinancial 已拉取全字段
$url = "...columns=ALL&filter=(SECUCODE=%22${encoded}%22)..."
# 第32行已验证 DEBT_ASSET_RATIO 存在
if ([double]$latest.DEBT_ASSET_RATIO -eq 0) { $hasDataIssue = $true }
```

**设计**: 新增 `Get-FinancialRatios` 函数，从已有API响应中提取偿债+运营指标。

**新增字段**（从东方财富API `RPT_LICO_FN_CPD` 报告提取）:

| 指标 | API字段名 | 计算方式 | 单位 |
|:-----|:---------|:--------|:---:|
| 资产负债率 | DEBT_ASSET_RATIO | 直接提取 | % |
| 流动比率 | CURRENT_RATIO | 直接提取（或 流动资产/流动负债） | 倍数 |
| 速动比率 | QUICK_RATIO | 直接提取（或 (流动资产-存货)/流动负债） | 倍数 |
| 有息负债率 | INTEREST_DEBT / TOTAL_ASSETS | 有息负债/总资产 | % |
| 应收账款周转率 | OPERATE_INCOME / ACCOUNTS_RECEIVABLE | 营收/应收账款 | 次 |
| 存货周转率 | OPERATE_COST / INVENTORY | 营业成本/存货 | 次 |

**接口契约**:
```powershell
function Get-FinancialRatios {
    param([string]$Code, [int]$Quarters = 1)
    # 返回 PSCustomObject:
    #   DebtAssetRatio, CurrentRatio, QuickRatio,
    #   InterestBearingDebtRatio, ARTurnover, InventoryTurnover,
    #   Source (数据源标记)
}
```

**1+2合规**: 主源=东方财富（已有），备源=同花顺THS（已有降级路径），缓存兜底=168h TTL。

**改动范围**:
- `代码文件/每日荐股/scripts/modules/financial.ps1` — 新增函数约40行
- 不改变 `Get-StockFinancial` 签名，向后兼容

**影响评估**: 零影响。新增函数，不改变现有接口。

---

### 4.2 R2: 估值模块升级

**设计分为两部分**: 2a(三情景EPS模型) + 2b(可比公司查询)

#### 4.2a 三情景EPS预测模型

**算法设计**:
```
基线EPS = TTM_EPS（最近4季度）
季节因子 = 历年(H1_EPS占比, H2_EPS占比) 的中位数

乐观情景: FY2026E_EPS = TTM_EPS × (1 + 近3年营收增速中位数) × 乐观乘数1.15
中性情景: FY2026E_EPS = TTM_EPS × (1 + 近3年营收增速中位数 × 0.7) × 中性乘数1.0
悲观情景: FY2026E_EPS = TTM_EPS × (1 + max(0, 近3年营收增速中位数) × 0.3) × 悲观乘数0.85

未来PE = 当前价 / FY2026E_EPS
```

**说明**: 此函数为**辅助计算工具**，输出三情景数字供AI在报告中引用。
**不替代AI判断**——AI可以基于行业/公司具体信息调整情景假设。

**接口契约**:
```powershell
function Get-ScenarioEPS {
    param([string]$Code)
    # 返回 PSCustomObject:
    #   TTM_EPS, RevenueGrowth3Y_Median,
    #   Scenario_Optimistic (EPS, PE, GrowthRate),
    #   Scenario_Neutral (EPS, PE, GrowthRate),
    #   Scenario_Pessimistic (EPS, PE, GrowthRate)
}
```

**代码等级**: L1 — 估值结论影响投资决策，需情墨复审 + Golden Master验证。

#### 4.2b 可比公司估值查询

**数据源**: 东方财富行业成分股API + 财务指标API
```
# 步骤1: 获取同行业成分股
RPT_STOCKINDUSTRY_COMPONENT → 同申万二级行业股票列表
# 步骤2: 批量获取估值指标
RPT_LICO_FN_CPD → PE/PB/ROE/营收增速 等
```

**接口契约**:
```powershell
function Get-ComparableValuation {
    param([string]$Code, [int]$TopN = 5)
    # 返回 PSCustomObject[]:
    #   Code, Name, PE_TTM, PB, ROE, RevenueYoY, MktCap
}
```

**代码等级**: L0 — 纯数据查询。

**改动范围**:
- `代码文件/每日荐股/scripts/modules/financial.ps1` — 新增 `Get-ScenarioEPS` (~50行) + `Get-ComparableValuation` (~40行)
- 不改变现有接口

---

### 4.3 R3: 资金面数据补充

**新增三个API查询函数**:

#### 4.3a 龙虎榜查询

```
API: datacenter.eastmoney.com
reportName: RPT_DAILY_BILLBOARD_DETAILS
参数: SECUCODE, 最近N个交易日
返回: 上榜日期, 席位名称, 买入金额, 卖出金额, 净买入, 上榜原因
```

```powershell
function Get-BillboardDetail {
    param([string]$Code, [int]$Days = 20)
    # 返回 PSCustomObject[]:
    #   TradeDate, SecuName, BuyAmount, SellAmount, NetAmount, Reason
}
```

#### 4.3b 北向资金持仓变化（补全已有stub）

```
API: eastmoney RPT_MUTUAL_HOLDSTOCKNORTH_STA
参数: SECUCODE
返回: 持股数量, 持股市值, 占总股本%, 占流通股%, 近1月/1周变化
```

```powershell
function Get-NorthboundDetail {
    param([string]$Code)
    # 补全 fundflow.ps1 第140行的stub实现
}
```

#### 4.3c 机构调研记录

```
API: datacenter.eastmoney.com
reportName: RPT_ORG_INVESTIGATION
参数: SECUCODE, 最近N条记录
返回: 调研日期, 调研机构数, 机构类型, 调研内容摘要
```

```powershell
function Get-InstitutionVisit {
    param([string]$Code, [int]$Count = 5)
    # 返回 PSCustomObject[]:
    #   VisitDate, OrgCount, OrgTypes, Summary
}
```

**1+2合规**: 主源=东方财富。龙虎榜和机构调研无免费备源API → 标注"仅供参考"。
北向资金备源=同花顺THS。

**改动范围**:
- `代码文件/每日荐股/scripts/modules/fundflow.ps1` — 新增3个函数约120行
- 不改变现有 `Get-StockFundFlow` 和 `Get-SectorFundFlow` 接口

---

## 五、文件改动清单

| 文件 | 改动类型 | 行数估算 | 等级 | 执行者 |
|:-----|:---:|:---:|:---:|:-----:|
| `代码文件/每日荐股/scripts/modules/financial.ps1` | 新增函数 | +90行 | L0/L1 | 红结 |
| `代码文件/每日荐股/scripts/modules/fundflow.ps1` | 新增函数 | +120行 | L0 | 红结 |
| `代码文件/每日荐股/scripts/modules/core.ps1` | 新增源配置 | +5行 | L0 | 红结 |

**总改动**: 3文件，~215行新增代码，0行删除，0接口变更。

**单文件行数检查**:
- `financial.ps1`: 当前~60行 → 改动后~150行 ✅ 未超500行红线
- `fundflow.ps1`: 当前~144行 → 改动后~264行 ✅ 未超500行红线
- `core.ps1`: 当前~80行 → 改动后~85行 ✅ 未超500行红线

---

## 六、数据流设计（升级后）

```
深度分析报告数据流（升级后）:

[东方财富API]
  ├─ financial.ps1
  │   ├─ Get-StockFinancial (现有,不变)
  │   ├─ Get-FinancialRatios (NEW R1) → 偿债/运营指标
  │   ├─ Get-ScenarioEPS (NEW R2a)    → 三情景估值
  │   └─ Get-ComparableValuation (NEW R2b) → 同业对比
  │
  ├─ fundflow.ps1
  │   ├─ Get-StockFundFlow (现有,不变)
  │   ├─ Get-SectorFundFlow (现有,不变)
  │   ├─ Get-BillboardDetail (NEW R3a)    → 龙虎榜
  │   ├─ Get-NorthboundDetail (NEW R3b)   → 北向资金明细
  │   └─ Get-InstitutionVisit (NEW R3c)   → 机构调研
  │
  └─ [JSON缓存层] → AI(腰子团队)读取 → 深度分析报告
```

---

## 七、需求→代码核对清单

| 编号 | 检查项 | 对应条款 | 情墨勾 | 腰子勾 |
|:----:|:------|:------|:-----:|:-----:|
| C1 | 新增财务字段均来自东方财富API已有响应 | 红线§1.2 | ☐ | ☐ |
| C2 | 新增API均有1+2降级路径（或标注"仅供参考"） | 红线§1.2 | ☐ | ☐ |
| C3 | PE(TTM)计算使用本地公式(Price/EPS) | 红线§1.2 | ☐ | ☐ |
| C4 | 三情景EPS不替代AI判断，仅提供计算参考 | 白皮书v3.0 | ☐ | ☐ |
| C5 | 龙虎榜/机构调研标注"仅供参考"（无备源） | 红线§1.2 | ☐ | ☐ |
| C6 | 新增函数不改变现有接口签名 | 接口契约§2 | ☐ | ☐ |
| C7 | 单文件行数≤500 | 轻量化规范§9.2 | ☐ | ☐ |
| C8 | 缓存TTL符合数据更新频率 | 数据字典 | ☐ | ☐ |
| C9 | API调用间隔≥0.3秒 | 红线§3 | ☐ | ☐ |
| C10 | 所有输出字段标注数据源编号 | 红线§1.2 | ☐ | ☐ |

---

## 八、风险与权衡

| 风险 | 影响 | 缓解 |
|:-----|:---|:-----|
| 东方财富API部分字段返回null | 某些指标不可得 | 字段级降级，缺失标注"N/A" |
| 龙虎榜/机构调研API可能变更 | 新函数失效 | 独立函数，不影响现有管线 |
| 三情景EPS参数主观性 | 乐观/悲观乘数可能不合适 | 标注"仅供参考"，参数可配置 |
| 可比公司选取偏差 | 同行业公司业务差异大 | 申万二级行业分类，AI可调整 |

---

> **设计完成** | 流入 → 闸门1: 新安审查 + 腰子确认
