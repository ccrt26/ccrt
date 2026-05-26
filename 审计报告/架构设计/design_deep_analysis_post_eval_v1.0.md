# 深度分析后评估系统 — 架构设计

> **设计人**：情墨 | **日期**：2026-05-26 | **版本**：v1.0
> **pipeline_stage**: complete | **L级**：L1（涉及评分/策略评估逻辑，不涉及L2交易/风控执行）
> **关联文档**：深度分析后评估逻辑 v1.0 | 深度分析.md v1.1 | 重点股票次日后评估白皮书 v1.8

---

## 1. 需求摘要

为深度分析报告建立自动化后评估系统。每周五深度分析报告生成后，自动执行版本感知的多窗口后评估（T+5~T+120），覆盖A层55分（复用日报框架）+ B层45分（11项深度分析特有维度），产出快报/月报/季报三档PDF报告，驱动深度分析方法论的持续自我优化。

---

## 2. 架构总览

```
┌──────────────────────────────────────────────────────────────────┐
│  触发层                                                           │
│  Cron: Fri 21:00 (深度分析完成后30min) + 月末 + 季末               │
│  ↓                                                                │
│  Invoke-DeepEvalPipeline.ps1 (L1 编排器)                          │
│  ↓                                                                │
│  ┌──────────────┬──────────────────┬──────────────────────────┐  │
│  │ ① 解析层 L0  │ ② 计算层 L1      │ ③ 报告层 L1              │  │
│  │              │                  │                          │  │
│  │ Parse-       │ Measure-         │ New-DeepEvalReport.ps1   │  │
│  │ DeepAnalysis │ DeepEvalMetrics  │   ├── 快报HTML            │  │
│  │ Report.ps1   │ .ps1             │   ├── 月报HTML            │  │
│  │   ↓          │   ├── A层55分    │   ├── 季报HTML            │  │
│  │ JSON输出     │   ├── B层45分    │   └── Edge→PDF           │  │
│  │              │   ├── 多窗口计算 │                          │  │
│  └──────────────┤   └── 版本感知   │                          │  │
│                 │                  │                          │  │
│  ┌──────────────┴──────────────────┴──────────────────────────┘  │
│  │ ④ 知识层 L0                                                     │
│  │ Update-DeepEvalKnowledge.ps1                                   │
│  │   ├── 信号跟踪CSV    ├── 改进日志    ├── 优化建议JSON           │
│  │   ├── 条件规则库     ├── 失效归因    ├── 催化剂映射库            │
│  │   └── 知识蒸馏       └── 反刍验证                               │
│  └────────────────────────────────────────────────────────────────│
│  ↓                                                                │
│  输出: 评估数据JSON + 评估结果JSON + PDF报告 + 知识库更新           │
└──────────────────────────────────────────────────────────────────┘
```

---

## 3. 模块设计

### 3.1 模块清单

| # | 模块 | 文件 | L级 | 行数预算 | 说明 |
|:--|:----|:----|:---:|:------:|:-----|
| 1 | 编排器 | `Invoke-DeepEvalPipeline.ps1` | L1 | ≤300 | 入口脚本，周期判断，串行调度 |
| 2 | 报告解析器 | `Invoke-DeepAnalysisParser.ps1` | L0 | ≤150 | 调度Python解析器 |
| 3 | 报告解析器(Py) | `parse_deep_analysis_report.py` | L0 | ≤400 | Markdown→JSON核心解析 |
| 4 | 评估计算引擎 | `Measure-DeepEvalMetrics.ps1` | L1 | ≤500 | A+B层全维度计算 |
| 5 | 报告生成器 | `New-DeepEvalReport.ps1` | L1 | ≤400 | HTML生成+Edge PDF转换 |
| 6 | 知识库更新 | `Update-DeepEvalKnowledge.ps1` | L0 | ≤250 | CSV/JSON/日志写入 |
| 7 | 版本配置 | `deep_eval_versions.json` | L0 | ≤50 | 深度分析.md各版本检验标准 |

**总行数预算**：≤2050行（符合单文件500行红线，拆分为7个模块）

### 3.2 模块详细设计

#### 3.2.1 编排器 — Invoke-DeepEvalPipeline.ps1 [L1]

```
参数：
  -Date <string>        目标深度分析报告日期 YYYYMMDD（默认：上周五）
  -Mode <string>        评估模式：Quick/Monthly/Quarterly（默认：Quick）
  -StockCodes <string[]> 股票代码列表（默认：从配置读取全部重点股票）

流程：
  1. 确定目标日期（上周五）
  2. 检查目标深度分析报告是否存在
  3. 调用 Invoke-DeepAnalysisParser → 评估数据JSON
  4. 调用 Measure-DeepEvalMetrics → 评估结果JSON
  5. 按Mode调用 New-DeepEvalReport → PDF报告
  6. 调用 Update-DeepEvalKnowledge → 知识库更新
  7. 若Mode=Monthly → 额外调用月度报告+中循环检查
  8. 若Mode=Quarterly → 额外调用季度报告+大循环+联合升级

接口契约（模块间JSON协议）：
  输入: 深度分析报告 .md 文件路径
  中间: 评估数据_深度分析_{date}.json (§4.2.1 Schema)
  中间: 评估结果_深度分析_{date}.json (含A+B层全部计算结果)
  输出: 快报/月报/季报 .pdf
```

#### 3.2.2 报告解析器 — Invoke-DeepAnalysisParser.ps1 [L0] + parse_deep_analysis_report.py [L0]

```
职责：
  - 读取深度分析报告Markdown
  - 正则提取方法论版本声明
  - 提取六维评分 + 综合评分
  - 提取市场判断（regime/phase/style）
  - 提取行业判断五维
  - 提取催化剂表（级别/类别/状态/概率/影响/来源）
  - 提取三情景EPS（乐观/中性/悲观）
  - 提取Wyckoff阶段定位
  - 提取五红旗判定
  - 提取止损位/仓位建议
  - 提取情景概率分布
  - 提取公司类型判定
  - 提取幻觉防范标注（⚠️标记）
  - 提取数据源状态（8源可用性）
  - 提取33个基础信号(S01-S33)
  - 输出 JSON → 评估数据_深度分析_{date}.json

提取规则（详见深度分析后评估逻辑 §4.2.2）：
  - methodology_version: 正则 /方法论版本: 深度分析\.md v([\d.]+)/
  - scores.*: 正则 评分表解析（§七）
  - market_judgment: 正则 /市场阶段判断.*?(牛|熊|震荡)/
  - catalysts[]: 正则表格解析（§一.4）
  - valuation_scenarios: 正则 表格解析（§五.2）
  - wyckoff_stage: 正则 /Wyckoff阶段.*\|.*(Accumulation|Markup|Distribution|Markdown)/
  - five_red_flags: 🟢/🟡/🔴 符号解析（§六.4）
  - company_type: 正则 /(价值型|成长型|周期型|混合型)/

Python选型理由：
  - Markdown表格解析：Python的re+状态机比PowerShell字符串处理更可靠
  - JSON序列化：Python json.dumps(ensure_ascii=False) 原生支持中文
  - 与现有 Invoke-DailyReportParser.py 保持技术栈一致

L0理由：
  - 纯数据提取，无评分/策略/风控逻辑
  - 单文件≤400行
  - 无接口变更
```

#### 3.2.3 评估计算引擎 — Measure-DeepEvalMetrics.ps1 [L1]

```
职责：
  A层计算（55分）：
    §2.2 评分方向校准：Spearman ρ(综合评分, T+5/T+10/T+20/T+40收益)
    §2.3 维度有效性：六维 Spearman ρ(T+20为主) + 区分度 + ICIR
    §2.4 信号有效性：S01-S44 多窗口胜率 + 期望收益 + 偏度 + MaxDD
    §2.5 阈值有效性：四分段 T+20收益对比 + 单调性检查
    §2.6 框架一致性：评分-结论一致率 + 置信度校准 + 多期稳定性

  B层计算（45分）：
    B1: 催化剂落地状态 + 影响幅度验证
    B2: 市场阶段方向正确率(T+20) + 阶段定位(T+60)
    B3: 行业判断五维验证(T+60，≥5次后启用)
    B4: 幻觉防范真阳性率(T+60，首次财报后启用)
    B5: 数据源可用率 + 降级频率
    B6: Brier Score 情景概率校准(T+20)
    B7: Spearman ρ(红旗数, T+20回撤)
    B8: 止损位触及率 + 假突破率
    B9: 三情景MAPE(T+60/T+120，首次财报后启用)
    B10: Wyckoff阶段正确率(T+20) + 转换提前识别率(T+40)
    B11: 公司类型错判率(T+60，≥5次后启用)

  多窗口数据源：
    T+5/T+10/T+20/T+40: 从行情管线获取累计收益
    T+60/T+120: 从后续深度分析报告或财报数据获取

  版本感知：
    读取 deep_eval_versions.json → 按报告版本加载对应检验标准
    若当前版本 > 报告版本 → 输出跨版本差距标记

  输入: 评估数据_深度分析_{date}.json + 历史评估结果JSON + 行情数据
  输出: 评估结果_深度分析_{date}.json

L1理由：
  - 包含评分有效性判断逻辑（Spearman/ICIR/胜率阈值判定）
  - 涉及策略评估方法论（维度权重合理性判断）
  - 不涉及L2（无风控否决/交易执行/止损触发逻辑）
  - 评估≠交易，判断"分析方法好不好"≠"该不该买卖"
```

#### 3.2.4 报告生成器 — New-DeepEvalReport.ps1 [L1]

```
职责：
  快报模式（Quick，每周五）：
    - 生成HTML ≤500字摘要
    - 含：评分方向校准 + 催化剂落地 + T+5方向验证 + 止损位状态 + 异常标记
    - Edge headless → PDF
    - 输出: 深度分析报告/深度分析后评估快报_{date}.pdf

  月报模式（Monthly，每月末）：
    - 完整A+B层评估表
    - 综合得分 + 维度排名 + 信号排名
    - 历史趋势图（CSV数据驱动的ASCII或简单HTML chart）
    - 优化建议清单
    - 跨版本差距追踪
    - 输出: 深度分析报告/深度分析后评估月报_{YYYYMM}.pdf

  季报模式（Quarterly，每季度末）：
    - 月度报告全部内容
    - T+60/T+120长窗口验证
    - 方法论演进效果评估
    - 失败案例深度解剖
    - 外部知识融合
    - 版本升级建议
    - 输出: 深度分析报告/深度分析后评估季报_{YYYYQ#}.pdf

  样式规范：
    - 品牌色 #1a1a2e / #16213e（复用报告样式基线v1.2）
    - 涨 #e74c3c / 跌 #27ae60
    - Edge headless --print-to-pdf（复用现有 gen_eval_pdf.ps1 模式）
    - 清理中间HTML（--KeepHtml开关保留）

L1理由：报告内容涉及策略评估结论，非纯数据展示。
```

#### 3.2.5 知识库更新 — Update-DeepEvalKnowledge.ps1 [L0]

```
职责：
  - 更新信号有效性跟踪CSV（追加行）
    路径: 重点股票/深度分析/后评估逻辑/逻辑积累/指标有效性跟踪.csv
  - 更新改进日志MD（追加条目）
    路径: 重点股票/深度分析/后评估逻辑/逻辑积累/改进日志.md
  - 更新优化建议JSON（合并去重）
    路径: 重点股票/深度分析/后评估逻辑/逻辑积累/优化建议.json
  - 更新催化剂映射库（B1数据积累）
    路径: 重点股票/深度分析/后评估逻辑/逻辑积累/催化剂映射.json
  - 更新条件规则库（中循环触发）
    路径: 重点股票/深度分析/后评估逻辑/逻辑积累/条件规则/
  - 失效归因写入（中循环触发）
    路径: 重点股票/深度分析/后评估逻辑/逻辑积累/失效归因/
  - 元评估数据采集
    路径: 重点股票/深度分析/后评估逻辑/逻辑积累/元评估/

L0理由：纯数据写入，无分析逻辑，无接口变更。
```

#### 3.2.6 版本配置 — deep_eval_versions.json [L0]

```json
{
  "versions": {
    "v1.0": {
      "release_date": "2026-05-26",
      "mandatory_chapters": 9,
      "checklist_items": 12,
      "required_signals": ["S01-S33"],
      "has_sub_sector_drilldown": false,
      "has_catalyst_mandatory": false,
      "has_valuation_matrix": false,
      "has_anti_hallucination": false,
      "has_fundflow_3day": false,
      "has_price_tier_5level": false,
      "scoring_weights": {
        "fundamental": 20, "technical": 20, "fund_flow": 15,
        "sector": 18, "valuation": 12, "risk_control": 15
      }
    },
    "v1.1": {
      "release_date": "2026-05-26",
      "mandatory_chapters": 9,
      "checklist_items": 15,
      "required_signals": ["S01-S44"],
      "has_sub_sector_drilldown": true,
      "has_catalyst_mandatory": true,
      "has_valuation_matrix": true,
      "has_anti_hallucination": true,
      "has_fundflow_3day": true,
      "has_price_tier_5level": true,
      "scoring_weights": {
        "fundamental": 20, "technical": 20, "fund_flow": 15,
        "sector": 18, "valuation": 12, "risk_control": 15
      },
      "scoring_weights_sector_frenzy": {
        "fundamental": 17.5, "technical": 20, "fund_flow": 15,
        "sector": 25, "valuation": 9.5, "risk_control": 15
      },
      "new_vs_v1_0": [
        "子赛道三步下钻(§一.3)",
        "催化剂强制识别≥2条(§一.4)",
        "估值方法选择矩阵(价值/成长/周期三分法)",
        "AI幻觉防范(§0.4)",
        "资金面3日/5日连续趋势+结构维度(§六.3)",
        "价格梯队五层+多源交叉验证(§八.3)"
      ]
    }
  }
}
```

---

## 4. 数据流设计

### 4.1 数据流图

```
深度分析报告 .md (每周五产出)
  │
  ├── 版本声明行: > 方法论版本: 深度分析.md vX.X
  │
  ▼
[Invoke-DeepAnalysisParser]  ─── deep_eval_versions.json (版本检验标准)
  │
  ▼
评估数据_深度分析_{date}.json (单次报告结构化数据)
  │
  ├── 历史评估数据 (评估数据_深度分析_*.json) ──┐
  ├── 历史评估结果 (评估结果_深度分析_*.json) ──┤
  ├── 行情数据 (后续T+5~T+120收益)            ├── 跨期累积
  ├── 后续财报数据 (实际EPS)                   │
  └── 催化剂公告数据                           │
  │                                            │
  ▼                                            │
[Measure-DeepEvalMetrics] ◄────────────────────┘
  │
  ▼
评估结果_深度分析_{date}.json (含A+B层全部计算结果)
  │
  ├──► [New-DeepEvalReport] ──► 快报/月报/季报 .pdf
  │
  └──► [Update-DeepEvalKnowledge]
        ├── 信号跟踪CSV
        ├── 改进日志MD
        ├── 优化建议JSON
        ├── 催化剂映射库
        ├── 条件规则库
        └── 元评估数据
```

### 4.2 与日报后评估的数据交换

```
日报后评估                            深度分析后评估
  │                                       │
  ├── 行情管线 (共享) ◄───────────────────┤
  ├── 财务管线 (共享) ◄───────────────────┤
  ├── 33信号定义 (共享) ◄─────────────────┤
  │                                       │
  ├── 中循环结果 ──► 条件规则库 ◄── 中循环结果
  ├── 大循环 ──► 联合知识蒸馏 ◄── 大循环
  └── 月度全量 ──► 联合外部知识融合 ◄── 季度全量
```

---

## 5. 文件结构

```
重点股票/深度分析/
├── 深度分析逻辑/
│   ├── 深度分析.md                          (方法论 v1.1)
│   └── 深度分析后评估逻辑.md                  (后评估方法论 v1.0)
│
├── 后评估逻辑/
│   ├── 深度分析后评估逻辑.md                  (本文档的配套方法论)
│   ├── deep_eval_versions.json               (版本配置 L0)
│   ├── 逻辑积累/
│   │   ├── 指标有效性跟踪.csv
│   │   ├── 改进日志.md
│   │   ├── 优化建议.json
│   │   ├── 催化剂映射.json
│   │   ├── 元评估/
│   │   ├── 条件规则/
│   │   ├── 失效归因/
│   │   ├── 知识代谢/
│   │   └── 知识蒸馏/
│   └── 归档/                                 (旧版本白皮书)
│
├── 后评估报告/
│   └── (中间JSON，评估数据+评估结果)
│
├── 深度分析报告/
│   ├── 深度分析后评估快报_{YYYYMMDD}.pdf      (每周产出)
│   ├── 深度分析后评估月报_{YYYYMM}.pdf        (每月产出)
│   └── 深度分析后评估季报_{YYYYQ#}.pdf        (每季产出)
│
代码文件/深度分析/
├── Invoke-DeepEvalPipeline.ps1               (L1 编排器)
├── Invoke-DeepAnalysisParser.ps1             (L0 解析器壳)
├── parse_deep_analysis_report.py             (L0 解析器核心)
├── Measure-DeepEvalMetrics.ps1               (L1 评估引擎)
├── New-DeepEvalReport.ps1                    (L1 报告生成)
└── Update-DeepEvalKnowledge.ps1              (L0 知识库)
```

---

## 6. 关键技术决策

### 6.1 PowerShell vs Python 分工

| 场景 | 选择 | 理由 |
|:-----|:---:|:-----|
| Markdown解析+JSON输出 | **Python** | 正则+表格解析更可靠，中文JSON原生支持 |
| 数值计算(Spearman/Brier/MAPE) | **PowerShell** | 无numpy依赖，纯数学运算PS可胜任；复用现有Get-SpearmanR |
| HTML报告生成 | **PowerShell** | 字符串拼接+here-string，PS更灵活 |
| PDF转换 | **PowerShell** | 复用现有 Edge headless 模式 |
| 文件IO/知识库 | **PowerShell** | 项目统一约定，复用现有CSV/JSON写模式 |

### 6.2 为什么不引入numpy/pandas

- 项目当前无numpy依赖，Spearman ρ已有纯PS实现（`run_keystock_evaluation.ps1:78-114`）
- Brier Score和MAPE公式简单，纯数学计算
- 引入pandas将增加环境复杂度，与项目"轻量化"原则冲突

### 6.3 与日报后评估的代码复用

| 复用项 | 来源 | 方式 |
|:-------|:----|:----|
| `Get-SpearmanR` | run_keystock_evaluation.ps1:78-114 | 抽取为lib函数 `lib/math_utils.ps1` |
| `Get-ICIR` | run_keystock_evaluation.ps1:117-124 | 同上 |
| Edge PDF转换模式 | tools/gen_eval_pdf.ps1 | 内联到New-DeepEvalReport.ps1 |
| CSS品牌样式 | run_keystock_evaluation.ps1:873-907 | 复用CSS变量 |

### 6.4 调度方式

| 触发 | 方式 | 配置 |
|:-----|:----|:-----|
| 每周五快报 | Claude Code CronCreate (durable) | `50 20 * * 5` (深度分析20:30完成后20min) |
| 每月末月报 | Claude Code CronCreate (durable) | `50 20 L * *` (月末最后一个工作日) |
| 每季末季报 | Claude Code CronCreate (durable) | `50 20 L 3,6,9,12 *` |

> **统一用CronCreate而非Windows Task Scheduler**：保持调度在项目边界内，与深度分析Command的调度方式一致。

---

## 7. 闸门设计

### 7.1 闸门1a：腰子设计确认

| 确认项 | 标准 |
|:------|:----|
| 后评估维度与方法论一致 | A+B层11维度与深度分析后评估逻辑v1.0完全对应 |
| 版本感知机制正确 | deep_eval_versions.json覆盖v1.0/v1.1差异 |
| 报告输出格式 | 三档PDF报告结构与§六规范一致 |

### 7.2 闸门1b：架构审查

| 审查项 | 标准 |
|:------|:----|
| L级标注正确 | 无L2模块（后评估不涉及交易/风控执行） |
| 单文件≤500行 | 7模块总预算2050行，单模块最大500行 |
| 接口契约完整 | 模块间JSON Schema定义清晰 |
| 无新增依赖 | 不引入numpy/pandas |
| 代码复用 | Spearman/ICIR/PDF转换复用现有实现 |
| 调度安全 | CronCreate durable，不阻塞主流程 |

### 7.3 闸门2：代码+验证

| 验证层 | 内容 |
|:------|:-----|
| 语法 | PowerShell Linter + Python flake8 |
| 数据 | 用600114东睦股份20260526深度分析报告做解析测试 |
| 逻辑 | Spearman/胜率/Brier手动验算 vs 脚本输出 |
| Golden Master | 第一份快报PDF与手动计算对比 |

---

## 8. 需求→代码核对清单

> 情墨+腰子共同勾签后放行。

| # | 需求点 | 对应模块 | 状态 |
|:--|:------|:--------|:---:|
| 1 | 版本感知前置读取 | Invoke-DeepAnalysisParser + deep_eval_versions.json | ☐ |
| 2 | 六窗口多时间尺度(T+5~T+120) | Measure-DeepEvalMetrics §多窗口计算 | ☐ |
| 3 | A层55分(维度/信号/阈值/一致性) | Measure-DeepEvalMetrics §A层 | ☐ |
| 4 | B层45分(11项特有维度) | Measure-DeepEvalMetrics §B层 | ☐ |
| 5 | 催化剂落地追踪(B1) | Measure-DeepEvalMetrics §B1 | ☐ |
| 6 | 情景概率Brier Score(B6) | Measure-DeepEvalMetrics §B6 | ☐ |
| 7 | 估值MAPE(B9) | Measure-DeepEvalMetrics §B9 | ☐ |
| 8 | 幻觉防范效果验证(B4) | Measure-DeepEvalMetrics §B4 | ☐ |
| 9 | 三档报告(快报/月报/季报) | New-DeepEvalReport | ☐ |
| 10 | PDF输出到指定路径 | New-DeepEvalReport §PDF转换 | ☐ |
| 11 | 四层学习循环(微/中/大/季度) | Update-DeepEvalKnowledge + 编排器 | ☐ |
| 12 | 与日报后评估大循环联合 | 编排器 §联合升级 | ☐ |
| 13 | 跨版本差距报告 | Measure-DeepEvalMetrics §版本感知 | ☐ |
| 14 | 深度分析报告强制版本声明 | (需修改深度分析Command模板) | ☐ |
| 15 | 所有数字标注数据源 | 报告生成器 §数据来源附录 | ☐ |

---

> **设计完成标记**: pipeline_stage: complete
> **下一步**: 腰子闸门1a确认 → 新安+旧影闸门1b审查
