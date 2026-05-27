# 深度分析后评估架构重构 — 方法论级别 → 设计 v2.0

> **情墨产出** | pipeline_stage: complete | finance_confirmed: true | 2026-05-27T22:00
> 代码等级: **L1** (策略/评分管线 — 后评估架构)

## 一、问题定义

当前 `Invoke-DeepEvalPipeline.ps1` 是**单股票模式**，与白皮书设计矛盾：

| | 当前（错误） | 白皮书要求 |
|:--|:-----------|:---------|
| 评估对象 | 单只股票深度分析报告 | **深度分析v1.2方法论框架** |
| 数据范围 | 1只股票MD | **全部重点股票** (§1.1) |
| 产出 | 每只1份PDF | **1份综合PDF** — 评估方法论有效性 |
| 核心问题 | "这只股票判断对吗？" | **"分析框架有效吗？"** (§1.1) |

腰子全团确认：**必须评估方法论整体，非单一股票。产出应为每周1份综合报告。**

## 二、影响范围

| 文件 | 等级 | 变更类型 | 说明 |
|:---|:----|:----|:-----|
| `Invoke-DeepEvalBatch.ps1` | L1 | **新建** | 批量编排器：扫描→解析→聚合→生成 |
| `New-DeepEvalReport.ps1` | L0 | 修改 | 新增 `-Batch` 模式：跨股票方法论报告 |
| `Invoke-DeepEvalPipeline.ps1` | L1 | 保留不动 | 保留单股票模式用于调试，标注为L0辅助 |
| `Invoke-DeepAnalysisParser.ps1` | L0 | 不变 | 复用 |
| `Measure-DeepEvalMetrics.ps1` | L1 | 不变 | 复用 |
| `.claude/scheduled_tasks.json` | — | 新增 | 周五21:00调度 |

## 三、数据流（新架构）

```
每周五20:30 深度分析产出 (全部8只MD)
   ↓ 周五21:00 触发
Invoke-DeepEvalBatch.ps1 ← 新脚本
   │
   ├─[1] 扫描 深度分析报告/*/ 下最新报告
   ├─[2] foreach 股票:
   │     ├─ Invoke-DeepAnalysisParser.ps1 → 评估数据_{code}_{date}.json
   │     └─ Measure-DeepEvalMetrics.ps1 → 评估结果_{code}_{date}.json
   ├─[3] 跨股票聚合:
   │     ├─ 各维度均值/方差/排名
   │     ├─ 系统性偏差检测
   │     └─ → 聚合结果_{date}.json
   └─[4] New-DeepEvalReport.ps1 -Batch → 1份综合PDF
           ↓
   深度分析后评估报告_YYYYMMDD.pdf  [产出]
```

## 四、变更方案

### 4.1 New-DeepEvalReport.ps1 — 新增Batch模式

在现有参数基础上新增：
```powershell
param(
    # 现有参数不变...
    [switch]$Batch,                    # 方法论级别综合报告
    [string]$BatchAggregatePath = ""   # 跨股票聚合JSON路径
)
```

Batch模式生成不同HTML模板：
- 方法论有效性总评（A层55分+ B层45分跨股票汇总）
- 各维度跨股票对比表（8只×11维度矩阵）
- 系统性偏差检测（估值偏差一致性、Wyckoff准确率等）
- 框架优化建议（基于跨股票统计规律）
- 白皮书版本升级建议

### 4.2 Invoke-DeepEvalBatch.ps1 — 新脚本 (~200行)

```
流程:
1. 扫描 $rootDir/重点股票/深度分析/深度分析报告/*/ 下最新MD
2. foreach 找到的报告:
   a. 运行 Invoke-DeepAnalysisParser.ps1
   b. 运行 Measure-DeepEvalMetrics.ps1
   c. 收集结果到数组
3. 跨股票聚合计算:
   - A层: 信号有效/维度有效/阈值/框架 → 均值±标准差
   - B层: B1-B11 各维度 → 均值±标准差
   - 系统性偏差: 估值预测一致性偏差、方向偏差
   - 排名: 各维度最佳/最差标的
4. 写聚合JSON → 聚合结果_{date}.json
5. 调用 New-DeepEvalReport.ps1 -Batch -BatchAggregatePath ...
6. AUTOCOMMIT
```

### 4.3 聚合JSON Schema

```json
{
  "meta": {
    "eval_date": "20260530",
    "stock_count": 8,
    "methodology_version": "v1.2",
    "report_window": "T+5"
  },
  "stocks_summary": [
    {"code": "600114", "name": "东睦股份", "total_score": 54, "rating": "B", ...},
    ...
  ],
  "cross_stock_analysis": {
    "framework_effectiveness": {
      "composite_mean": 58.3,
      "composite_std": 12.1,
      "effective_stocks": 6,
      "weak_stocks": 2
    },
    "dimension_matrix": {
      "B1_catalyst": {"mean": 3.2, "std": 1.1, "best": "601727", "worst": "301075"},
      ...
    },
    "systematic_bias": {
      "valuation_bias_pct": "+12%",
      "direction_accuracy": "75%",
      "wyckoff_accuracy": "62%"
    }
  },
  "suggestions": [...]
}
```

## 五、接口契约

| 接口 | 方向 | 格式 | 说明 |
|:-----|:----|:-----|:-----|
| Parser → Metrics | 复用现有 | eval_data JSON | 不变 |
| Metrics → Batch | 复用现有 | eval_result JSON | 不变 |
| Batch → Report | **新增** | aggregate JSON | 跨股票聚合结果 |
| Report → PDF | 复用现有 | Edge headless | 输出路径不变 |

## 六、风险评估

| 风险 | 概率 | 影响 | 缓解 |
|:---|:---|:---|:---|
| 某只股票无深度分析报告 | 高 | 低 | 跳过该股票，标注 `[SKIP]`，降低聚合置信度 |
| 聚合JSON过大 | 低 | 低 | 8只×11维≈200条数据，JSON<50KB |
| 新报告模板不完善 | 中 | 低 | 先产出Quick版（≤500字），月度迭代丰富 |
| 调度时间与深度分析冲突 | 低 | 中 | 深度分析20:30完成，后评估21:00触发，间隔30min |

## 七、需求→代码核对清单

| # | 需求 | 文件 | 验证方法 |
|:--|:-----|:-----|:-----|
| 1 | 批量编排器扫描全部深度分析报告 | Invoke-DeepEvalBatch.ps1 | 运行→确认N只股票被解析 |
| 2 | 跨股票聚合输出JSON | Invoke-DeepEvalBatch.ps1 | JSON schema验证 |
| 3 | Batch模式生成方法论级别PDF | New-DeepEvalReport.ps1 | PDF内容含跨股票汇总表 |
| 4 | 命名符合管理规范 | 全部 | `深度分析后评估报告_YYYYMMDD.pdf` |
| 5 | 单股票管线保留不删 | Invoke-DeepEvalPipeline.ps1 | 仍可独立运行 |
| 6 | PDF可打开≥5KB | — | 文件检查 |
| 7 | 周五调度注册 | scheduled_tasks.json | 验证cron表达式 |

---

> 情墨+腰子勾签：________ / ________ | 日期：2026-05-27
