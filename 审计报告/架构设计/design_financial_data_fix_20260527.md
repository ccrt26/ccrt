# 设计文档: 财务管线数据质量修复

> **pipeline_stage: complete**
> **阶段**: ①架构设计 | **设计者**: 情墨 | **日期**: 2026-05-27
> **任务**: 修复财务管线EPS口径矛盾、多字段缺失(BPS/毛利率/现金流/商誉)、RevenueTTM异常
> **代码分级**: L1（策略/评分相关）| **影响范围**: `batch_data_collector.ps1` (1文件), `financial.ps1` (1文件)

---

## 一、问题诊断（5项根因）

### 问题1: EPS口径矛盾 — AVERAGE vs TTM

**文件**: `batch_data_collector.ps1:429-431`
**根因**:
```powershell
$eps = ($epsVals | Measure-Object -Average).Average   # ← 存的是季度均值！
```
管线`EPS`字段存储的是4个季度的**均值**（如科大讯飞0.1578/4=0.03945），不是TTM求和。
`Get-ScenarioEPS`函数（financial.ps1:205-208）正确地用SUM计算TTM EPS，但主采集器未调用此逻辑。
PE字段来自行情API（使用不同EPS口径），与EPS字段不匹配→PE值完全不可靠。

**影响**: 8只标的全部PE值偏离真实值2-4x。深度分析需手工加总逐季EPS后重算PE。

### 问题2: BPS缺失 — 字段名不匹配

**文件**: `batch_data_collector.ps1:434-436`
**根因**:
```powershell
$bpsVal = $fin[0].BPS
if (-not $bpsVal) { $bpsVal = $fin[0].NAPS }
```
东方财富API `RPT_LICO_FN_CPD` 返回的字段名可能为`NAPS`（每股净资产），但部分股票响应中两个字段均为null。需增加备选字段名`TOTAL_EQUITY`（总权益）/`SHAREHOLDERS_EQUITY`兼容不同API版本。

**影响**: 德力佳/多瑞医药/盈峰环境 BPS=null → PB估值无法计算。

### 问题3: RevenueTTM异常 — 单位/口径混淆

**文件**: `batch_data_collector.ps1:439-447`
**根因**: `TOTAL_OPERATE_INCOME`在东方财富API中返回单位为**元**。4季度求和后除以1e8转为亿元，但部分季度可能存在：
- (a) 一次性的营业外收入混入 → 虚增
- (b) API字段在不同版本中单位不一致（元 vs 万元）
- (c) 部分公司披露口径差异（合并报表 vs 母公司）

**影响**: 科大讯飞RevenueTTM=602.8亿（实际约233亿）→ PS=1.83 vs 实际PS≈4.7。

### 问题4: 毛利率/现金流/商誉缺失

**文件**: `batch_data_collector.ps1:460-463` + `batch_data_collector.ps1:478`

| 缺失字段 | 当前处理 | 根因 |
|:--------|:--------|:-----|
| GrossMargin | 试3个字段名→全null | API `RPT_LICO_FN_CPD`不返回毛利率字段。需从RPT_DMSK_FN_INCOME（利润表详细）端点获取 |
| CFPS(经营现金流) | 仅THS备源 | 东方财富主源此端点不含现金流数据 |
| 商誉(Goodwill) | **从未采集** | 采集脚本未实现商誉字段 |
| 扣非EPS | **从未采集** | 采集脚本未实现扣非EPS字段 |

### 问题5: PE字段不可靠

**文件**: `batch_data_collector.ps1:506`
**根因**: `PE = $q.PE` 直接从行情API获取，使用腾讯/新浪的静态PE计算方法（可能与TTM口径不同）。不标注数据源，导致PE与EPS字段自相矛盾。

---

## 二、修复方案设计

### 2.1 数据流修复

```
修复前:
  API[3] → BASIC_EPS → avg(EPS) → EPS字段(均值)  ← 错误
  API[3] → BPS/NAPS(仅2个字段名) → BPS字段       ← 不足
  API[3] → TOTAL_OPERATE_INCOME → sum → RevenueTTM ← 无校验
  无 → GrossMargin/CFPS/Goodwill/DEDUCTED_EPS → null ← 缺失

修复后:
  API[3] → BASIC_EPS → sum → EPS_TTM字段(新)     ← 修正
  API[3] → BASIC_EPS → avg → EPS_Quarterly        ← 保留(数组不变)
  API[3] → BPS/NAPS/TOTAL_EQUITY/... → BPS字段    ← 增强
  API[3] → TOTAL_OPERATE_INCOME → sum → validity_check → RevenueTTM ← 增加校验
  API[3a](新增) → GROSS_PROFIT_MARGIN → GrossMargin  ← 新增端点
  同花顺[THS] → CFPS(已有逻辑) → CFPS              ← 保留
  API[3a] → GOODWILL → Goodwill字段(新)             ← 新增
  API[3] → DEDUCTED_EPS → DeductedEPS字段(新)       ← 新增
```

### 2.2 数据库改动（data_full.json schema）

**新增字段**:

| 字段 | 类型 | 数据源 | 说明 |
|:-----|:----|:------|:-----|
| `EPS_TTM` | float | 东方财富[3]→自算 | TTM EPS = SUM(最近4Q EPS) |
| `EPS` | float | (保留) | 重命名语义为EPS_AvgQuarterly，保持向后兼容 |
| `Goodwill` | float | 东方财富[3a] 新端点 | 商誉(元) |
| `GoodwillToNA` | float | 自算 | 商誉/净资产比率(%) |
| `DeductedEPS` | float | 东方财富[3] | 扣非基本EPS |
| `AssetLiabilityRatio` | float | 东方财富[3] | 资产负债率(%)(已有但未输出到JSON) |

**修改字段**:

| 字段 | 当前 | 修复后 |
|:-----|:-----|:-----|
| `PE` | 行情PE(来源不明) | **PE_TTM = Price / EPS_TTM** (标签[3+自算])；`PE_Quote` 保留行情PE |
| `RevenueTTM` | 4Q求和无校验 | 4Q求和 + **有效性校验**(Rev/Cap<10→通过) + 异常标记 |

### 2.3 实现方案

#### 修改文件1: `代码文件/每日荐股/scripts/modules/financial.ps1`

**变更**: 新增 `Get-FinancialDetail` 函数，调用东方财富`RPT_DMSK_FN_INCOME`端点获取利润表详细数据（含毛利率/商誉）。

```
function Get-FinancialDetail {
    param([string]$Code, [int]$Quarters=1)
    # 新端点: RPT_DMSK_FN_INCOME (利润表详细)
    # 返回字段: GROSS_PROFIT_MARGIN, GOODWILL, DEDUCTED_EPS, ...
}
```

#### 修改文件2: `代码文件/每日荐股/scripts/batch_data_collector.py`

**变更1** (line 430): EPS改为TTM求和
```powershell
# 旧: $eps = ($epsVals | Measure-Object -Average).Average
# 新:
$epsTTM = ($epsVals | Measure-Object -Sum).Sum
$eps_avg_q = ($epsVals | Measure-Object -Average).Average
```

**变更2** (line 434-436): BPS字段名增强
```powershell
$bpsVal = $fin[0].BPS
if (-not $bpsVal) { $bpsVal = $fin[0].NAPS }
if (-not $bpsVal) { $bpsVal = $fin[0].TOTAL_EQUITY }      # 新增
if (-not $bpsVal) { $bpsVal = $fin[0].SHAREHOLDERS_EQUITY } # 新增
```

**变更3** (line 447后): RevenueTTM有效性校验
```powershell
# 新增: 营收合理性检查
$mktCapYi = [double]$q.MktCap
if ($revenueTTM -gt 0 -and $mktCapYi -gt 0) {
    $revYi = $revenueTTM / 1e8
    if ($revYi / $mktCapYi -gt 10) {  # PS<0.1 → 极可能异常
        Write-Warning "RevenueTTM异常: ${Code} Rev=${revYi}亿 MktCap=${mktCapYi}亿 PS=$([math]::Round($mktCapYi/$revYi,2))"
        # 标记但不丢弃——让下游判断
    }
}
```

**变更4** (line 459-463): 毛利率从新端点获取
```powershell
# 优先从 Get-FinancialDetail 获取毛利率
$finDetail = Get-FinancialDetail -Code $s.Code -Quarters 1
if ($finDetail) {
    $grossMargin = $finDetail.GROSS_PROFIT_MARGIN
    $goodwill = $finDetail.GOODWILL
    $deductedEPS = $finDetail.DEDUCTED_EPS
}
# 回退到原有逻辑
if (-not $grossMargin) { ...原有3字段fallback... }
```

**变更5** (line 506): PE修正
```powershell
PE_Quote = if ($q.PE -and $q.PE -gt 0) { $q.PE } else { 0 }
PE_TTM   = if ($epsTTM -gt 0) { [math]::Round($q.Price / $epsTTM, 2) } else { 0 }
PE       = if ($PE_TTM -gt 0) { $PE_TTM } else { $PE_Quote }   # 优先TTM
```

**变更6** (line 556-565): 输出新增字段
```powershell
EPS          = $eps_avg_q          # 改为季度均值（保持兼容）
EPS_TTM      = $epsTTM             # 新增: TTM求和
EPS_Quarterly = $epsQuarterly
BPS          = $bps
Goodwill     = $goodwill           # 新增
GoodwillToNA = if ($bps -and $goodwill) { ... } # 新增
DeductedEPS  = $deductedEPS        # 新增
AssetLiabilityRatio = $debtRatio   # 新增(从财务比率已有数据)
```

### 2.4 兼容性

- **向后兼容**: `EPS`字段改为季度均值语义（本来就是均值），新增`EPS_TTM`承载TTM值
- **下游影响**: 评分引擎`scoring_engine_v2.py`当前使用`EPS`字段→需更新为`EPS_TTM`
- **报告影响**: 日报/深度分析使用`EPS_Quarterly`数组不受影响（语义不变）

---

## 三、风险评估

| 风险 | 等级 | 缓解 |
|:-----|:---:|:-----|
| API新端点不可用 | 中 | 保留3字段fallback逻辑，新端点失败时降级 |
| EPS_TTM与评分引擎不一致 | 低 | 评分引擎同步更新→新安回归验证 |
| 向后兼容破坏 | 低 | EPS改为语义正确版，增加EPS_TTM，下游逐步迁移 |

---

## 四、文件清单

| 文件 | 操作 | 等级 | 预估行数变化 |
|:-----|:----:|:---:|:--------:|
| `代码文件/每日荐股/scripts/modules/financial.ps1` | 新增函数 | L0 | +30行 |
| `代码文件/每日荐股/scripts/batch_data_collector.py` | 修改6处 | L1 | ~40行 |
| `代码文件/每日荐股/评分逻辑/scoring_engine_v2.py` | 适配EPS_TTM | L1 | ~5行 |

---

## 五、需求→代码核对清单

- [ ] 新增`Get-FinancialDetail`函数（financial.ps1）
- [ ] EPS改为TTM求和 + 保留Quarterly数组（batch_data_collector.ps1:429-431）
- [ ] BPS增加TOTAL_EQUITY/SHAREHOLDERS_EQUITY备选字段名（:434-436）
- [ ] RevenueTTM增加PS<0.1异常检测（:447后）
- [ ] 毛利率/扣非EPS/商誉从新端点获取（:459-463）
- [ ] PE改为PE_TTM优先 + PE_Quote保留（:506）
- [ ] JSON输出新增EPS_TTM/Goodwill/DeductedEPS/AssetLiabilityRatio字段（:556-565）
- [ ] 评分引擎适配EPS_TTM（scoring_engine_v2.py）
- [ ] 回归测试: 8只标的逐字段验证完整性

---

> **情墨签名**: ________ | **腰子签名**: ________
> **新安审查**: ________ | **旧影审查**: ________
