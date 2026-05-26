# 新安四层验证 — 每日数据管线自动化调度

> 验证人：新安 | 2026-05-25 | 闸门2验证

---

## 一、变更影响分析

| 评估维度 | 结论 |
|:---------|:-----|
| 修改文件 | 无（仅新增2个脚本） |
| 下游影响 | 无 — invoke_daily.ps1 通过 workflow_records.csv 与现有管线解耦 |
| 数据格式 | 无变更 — 只读 workflow_records.csv |
| API接口 | 无变更 — 不涉及任何API调用 |
| 评分引擎 | 无影响 |
| 交易引擎 | 无影响 |
| 报告生成 | 无影响 |

**影响范围：零破坏性影响。** 仅在现有系统外层增加调度触发机制。

## 二、代码验证

### invoke_daily.ps1 (28行)

| 检查项 | 结果 | 说明 |
|:-------|:----:|:-----|
| 语法 | PASS | PowerShell 5.1+ 兼容 |
| 路径解析 | PASS | 3x Split-Path 从 PSScriptRoot 到根目录，正确 |
| 幂等逻辑 | PASS | Line 16: Select-String 检查今日 daily_latest SUCCESS |
| 退出码 | PASS | 跳过=0, 调用管线=$LASTEXITCODE |
| 错误处理 | PASS | Test-Path 先检查 recordFile 存在性 |

### install_scheduler.ps1 (149行)

| 检查项 | 结果 | 说明 |
|:-------|:----:|:-----|
| 语法 | PASS | PowerShell 5.1+ 兼容 |
| 路径解析 | PASS | 使用 $PSScriptRoot 派生根目录（修复B2同类问题） |
| 前置检查 | PASS | Line 39-53: 模块可用性 + 脚本存在性 |
| 双触发器 | PASS | Line 99-100: Daily定时 + AtLogon(120s) |
| 幂等安装 | PASS | Line 85-89: 自动删除旧任务后重建 |
| 卸载支持 | PASS | Line 22-36: -Uninstall 完整支持 |
| 异常处理 | PASS | Line 114-128: try/catch 包裹任务注册 |
| S4U模式 | PASS | Line 111: 无需明文密码 |
| StartWhenAvailable | PASS | Line 106: 核心补跑机制 |
| MultipleInstances | PASS | Line 108: IgnoreNew 防止并发冲突 |

## 三、回归检查

| R编号 | 检查点 | 结果 |
|:-----:|:------|:----:|
| R01 | daily_workflow.ps1 未被修改 | PASS |
| R02 | 评分引擎未被修改 | PASS |
| R03 | 模拟交易引擎未被修改 | PASS |
| R04 | 数据采集模块未被修改 | PASS |
| R05 | 报告生成未被修改 | PASS |
| R06 | 缓存结构未变更 | PASS |
| R07 | workflow_records.csv 格式兼容 | PASS (仅追加读取) |
| R08 | is_market_open.ps1 未修改 | PASS |
| R09 | 1+2数据源架构未变更 | PASS |
| R10 | 红线规则文档未修改 | PASS |
| R11 | 白皮书版本未变更 | PASS |
| R12 | Golden Master 不受影响 | PASS |

**回归结论：零回归风险。** 所有核心链路(R01-R12)未被触及。

## 四、红线逐条审查

| 条款 | 检查 | 结果 |
|:-----|:-----|:----:|
| §1.1 编造数据 | 无数据输出 | N/A |
| §1.2 1+2架构 | 不涉及数据获取 | N/A |
| §1.3 禁止编造 | 无财务/行情数据 | N/A |
| §1.7 禁止删PDF | 不涉及文件删除 | N/A |
| §5.4 文档同步 | 工具脚本无需.docx | N/A |
| §9.2 单文件≤500行 | invoke 28行, install 149行 | PASS |
| §9.2 代码分级 | L1/L0 已标注 | PASS |

## 五、判定

- **Gate 2: PASS** — 代码实现符合设计，无回归影响，红线合规。
- 闸门状态：**通行**
