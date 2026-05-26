# Git自动提交机制 — 架构设计

> **设计人**：情墨 | **日期**：2026-05-26 | **版本**：v1.0
> pipeline_stage: complete | finance_confirmed: true | **L级**：L0（工具/基础设施，不涉及策略/风控/交易逻辑）

---

## 1. 需求摘要

**问题**：项目自动化流程（每日荐股/深度分析/日报/后评估/数据管线）产出大量文件，但全链路无 `git add` + `git commit` 步骤，导致456个文件长期漂在工作区外。2026-05-26全量基线入库后，需建立长效机制防止再次堆积。

**目标**：在每个关键产出节点末尾，自动将产出文件纳入Git版本管理。

---

## 2. 架构决策

### ADR：集中式共享模块 vs 脚本内嵌 vs 定时批量提交

| 方案 | 优点 | 缺点 | 结论 |
|:-----|:-----|:-----|:----:|
| A. 集中式共享模块 | 统一消息格式/安全门禁/单点维护 | 各脚本需显式调用 | **✅ 采纳** |
| B. 脚本内嵌git命令 | 零依赖 | 消息格式不一致/无法统一管控 | 否决 |
| C. 定时cron批量提交 | 零侵入 | 丢失上下文/commit message无意义/可能提交半成品 | 否决 |

**决策**：方案A。新建 `代码文件/tools/git_autocommit.ps1` 作为共享模块，各产出节点末尾调用。

---

## 3. 模块设计

### 3.1 核心模块 [L0]

**文件**：`代码文件/tools/git_autocommit.ps1`

**接口契约**：

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|:-----|:----:|:----:|:-----|:-----|
| `-Module` | string | ✅ | — | 产出模块名，用于commit message：`daily_pick` / `deep_analysis` / `daily_brief` / `post_eval` / `data_pipeline` / `pipeline_eng` |
| `-Paths` | string[] | ✅ | — | 要提交的文件/目录路径列表（相对于项目根目录） |
| `-Message` | string | ✅ | — | 变更摘要（一行，≤72字符） |
| `-DryRun` | switch | ❌ | false | 仅显示将要提交的内容，不实际执行 |
| `-SkipHook` | switch | ❌ | false | 跳过pre-commit hook（仅紧急修复用，需日志记录） |

**返回值**：
```json
{"success": true/false, "commit_hash": "abc1234", "files_count": 5, "error": ""}
```

**执行流程**：
```
1. 验证 -Paths 均在项目根目录下（防路径穿越）
2. git status --short -- <paths> → 无变更则跳过（返回 success=true, files_count=0）
3. git add -- <paths>
4. git diff --cached --stat → 记录文件清单到日志
5. git commit -m "auto: <Module> — <Message> [YYYYMMDD]"
6. 返回结果JSON
```

**安全约束**：
- `-Paths` 必须通过路径白名单校验（仅允许项目内路径，禁止 `../`）
- `-SkipHook` 使用时写入告警日志
- 不提交 `.env` / `credentials.*` / `settings.local.json`（E5规则）
- commit message 始终带 `auto:` 前缀，可追溯

### 3.2 日志 [L0]

**文件**：`临时报告/git_autocommit.log`

每行一条JSON记录：`{timestamp, module, commit_hash, files_count, dry_run, skip_hook}`

---

## 4. 集成点

### 4.1 各产出节点的调用位置

| 节点 | Module值 | 调用时机 | 典型Paths |
|:-----|:---------|:--------|:---------|
| 每日荐股分析 | `daily_pick` | 报告HTML/PDF生成完成后 | `每日荐股/股票报告/`, `每日荐股/事后评估/records.csv` |
| 周度深度分析 | `deep_analysis` | 六章报告+HTML+PDF生成完成后 | `重点股票/深度分析/` |
| 日报生成 | `daily_brief` | 每只股票日报输出后（批量） | `重点股票/股票报告/` |
| 后评估 | `post_eval` | 评估报告+数据更新后 | `每日荐股/评估报告/`, `重点股票/次日评估/`, `历史数据/02_评估数据/` |
| 数据管线 | `data_pipeline` | 数据采集/评分完成后 | `历史数据/`, `代码文件/数据/` |
| Pipeline工程 | `pipeline_eng` | 每个阶段交付物产出后 | `审计报告/`, `代码文件/` (需pipeline_token验证) |

### 4.2 调用示例

```powershell
# 深度分析报告产出后
git_autocommit.ps1 -Module "deep_analysis" `
  -Paths @("重点股票/深度分析/") `
  -Message "东睦股份(600114)周度深度分析报告"
```

---

## 5. 不自动提交的场景

| 场景 | 原因 |
|:-----|:-----|
| AI对话中的临时文件 | 由人工/AI手动commit |
| `.claude/` 运行时文件（sessions/projects/telemetry） | .gitignore已排除 |
| `临时报告/` 一次性脚本 | 临时调试用，不应入库（已存在的除外） |
| pre-commit hook校验失败 | hook阻断=不应强行提交 |

---

## 6. 与现有机制的关系

| 现有机制 | 关系 |
|:---------|:-----|
| pre-commit hook (Check A-F) | git_autocommit 提交时自动触发hook校验 |
| pipeline_engine.ps1 | pipeline_eng module调用需配合pipeline_token验证 |
| .gitignore | git_autocommit 遵循.gitignore规则，不提交排除文件 |
| E5禁止文件检查 | git_autocommit 内置E5规则，拒绝提交敏感文件 |

---

## 7. 需求→实现核对清单

> 情墨+腰子勾签后放行

| # | 需求 | 实现位置 | 情墨 | 腰子 |
|:--|:-----|:--------|:----:|:----:|
| 1 | 共享git提交模块 | `代码文件/tools/git_autocommit.ps1` | ☐ | ☐ |
| 2 | 统一commit message格式 | §3.1 -Message参数 + auto:前缀 | ☐ | ☐ |
| 3 | 6个集成点接入 | §4.1 各节点调用 | ☐ | ☐ |
| 4 | 安全路径校验 | §3.1 路径白名单+防穿越 | ☐ | ☐ |
| 5 | 不提交敏感文件 | §3.1 E5规则 | ☐ | ☐ |
| 6 | 无变更时静默跳过 | §3.1 执行流程步骤2 | ☐ | ☐ |
| 7 | 操作日志 | §3.2 git_autocommit.log | ☐ | ☐ |
| 8 | Dry-run模式 | §3.1 -DryRun参数 | ☐ | ☐ |

---

## 8. 架构自检（情墨12项清单）

| 编号 | 审查项 | 结果 | 备注 |
|:----:|:-------|:----:|:-----|
| CH1 | 模块边界清晰 | ✅ | 单一职责：git add+commit包装 |
| CH2 | 接口完整 | ✅ | 参数类型/必填/默认值/返回值均已定义 |
| CH3 | 1+2架构 | ✅ | 不涉及数据获取 |
| CH4 | 第三方依赖 | ✅ | 无新增依赖，纯git CLI |
| CH5 | 循环依赖 | ✅ | 底层工具，无上游依赖 |
| CH6 | 单点故障 | ✅ | git失败只影响版本管理，不影响业务产出 |
| CH7 | 反模式 | ✅ | 不触发AP-01~AP-07 |
| CH8 | 影响范围 | ✅ | 新增文件，不影响现有模块 |
| CH9 | API超时 | ✅ | 不涉及API调用 |
| CH10 | 回退方案 | ✅ | 删除git_autocommit.ps1+移除调用即可回退 |
| CH11 | 通知关联 | ✅ | 需通知红结(编码)+红枫(部署)+新安(抽查) |
| CH12 | 红线合规 | ✅ | 不涉及数据编造/PDF删除/文档同步 |
