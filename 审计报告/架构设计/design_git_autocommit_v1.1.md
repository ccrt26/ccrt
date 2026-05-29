# Git自动提交机制 — 架构设计 v1.1

> **设计人**：情墨 | **日期**：2026-05-26 | **版本**：v1.1
> pipeline_stage: complete | finance_confirmed: true | **L级**：L0（工具/基础设施，不涉及策略/风控/交易逻辑）
> **基于**：[v1.0](design_git_autocommit_v1.0.md)

---

## 0. v1.0→v1.1 变更摘要

**v1.0问题**：git_autocommit只覆盖6个管线产出节点（daily_pick/deep_analysis/daily_brief/post_eval/data_pipeline/pipeline_eng），以下两类变更长期漂在工作区：

| 类别 | 典型文件 | v1.0状态 |
|:-----|:--------|:-------:|
| 工程源码变更 | `代码文件/`下.ps1/.py脚本 | ❌ 无覆盖 |
| 项目配置变更 | `CLAUDE.md`, `.claude/agents/`, `.claude/commands/`, `.claude/knowledge/` | ❌ 无覆盖 |
| 管线配置变更 | `.claude/pipeline_active.json`, `.claude/scheduled_tasks.lock` | ❌ 无覆盖 |

**v1.1方案**：新增`engineering`模块值 + 日终安全网（功能已整合到 `git_autosweep.py`，不再使用独立 `git_sweep.ps1`），确保任何未提交变更在每日工作流结束时自动入库。

---

## 1. 变更范围

### 1.1 修改文件

| 文件 | 变更 | L级 | 说明 |
|:-----|:----:|:----:|:-----|
| `代码文件/tools/git_autocommit.py` | 改1行 | L0 | ValidateSet新增`engineering` |
| `代码文件/每日荐股/scripts/daily_workflow.py` | 改2行 | L1 | 末尾调用git_sweep |

### 1.2 新增文件

| 文件 | L级 | 说明 |
|:-----|:----:|:-----|
| `代码文件/tools/git_autosweep.py` | L1 | 日终安全网+自动清扫(已整合原git_sweep.ps1功能)，325行 |

### 1.3 受影响但无需修改

| 文件 | 原因 |
|:-----|:-----|
| `代码文件/监督机制/pipeline_engine.py` | git_sweep通过daily_workflow调用，不直接改pipeline_engine |
| 其他管线产出脚本 | 已有git_autocommit调用点不变 |

---

## 2. 核心设计：git_sweep.ps1

### 2.1 设计理念

**"安全网"模式**：不追求在每个工程阶段精准提交，而是在每日工作流结束时统一清扫。好处：
- 零侵入：不修改各管线阶段脚本的现有逻辑
- 不漏网：任何变更（无论来源）都会被捕获
- 可追溯：commit message带日期，日志JSON记录

### 2.2 接口契约

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|:-----|:----:|:----:|:-----|:-----|
| `-Module` | string | ❌ | `engineering` | 传递给git_autocommit的模块名 |
| `-DryRun` | switch | ❌ | false | 仅显示将要提交的内容 |

**返回值**：git_autocommit的JSON返回值透传，无变更时返回 `{"success": true, "commit_hash": "", "files_count": 0}`

### 2.3 执行流程

```
1. git -c core.quotepath=false status --short
2. 若无输出 → 返回 CLEAN (success=true, files=0)
3. 若有输出 → 调用 git_autocommit.ps1 -Module "engineering" -Paths @(".") -Message "daily sweep"
4. 透传git_autocommit的返回值
```

### 2.4 安全约束

- 复用git_autocommit的E5检查（敏感文件拦截）
- 复用git_autocommit的路径验证
- 遵循.gitignore（git status自动排除）
- git_autocommit失败不阻塞管线（版本管理失败 ≤ 业务产出失败）
- 日志写入同一文件 `临时报告/git_autocommit.log`

---

## 3. 集成点

### 3.1 daily_workflow.ps1 调用位置

在 `daily_workflow.ps1` 末尾（所有产出节点完成后、脚本退出前）插入：

```powershell
# 日终安全网：提交所有未入库变更
$sweepScript = Join-Path $PSScriptRoot "..\..\tools\git_sweep.ps1"
if (Test-Path $sweepScript) {
    & $sweepScript
}
```

### 3.2 调用时机

```
daily_workflow.ps1 执行流程:
  数据采集 → 评分引擎 → 报告生成 → 各节点git_autocommit → git_sweep(安全网) → 退出
```

git_sweep在最后执行，此时：
- 各管线产出节点已通过各自的git_autocommit提交了产出文件
- 剩余未提交的 = 工程变更/配置变更/遗漏的产出文件 → git_sweep统一清扫

---

## 4. 与v1.0的关系

| v1.0机制 | v1.1变化 |
|:---------|:--------|
| 6个管线产出模块 | 不变，继续使用 |
| Module ValidateSet | 新增`engineering`值 |
| git_autocommit.log | 不变，engineering模块日志写入同一文件 |
| E5检查 | 不变，git_sweep复用git_autocommit的E5检查 |
| .gitignore遵循 | 不变 |

---

## 5. 不自动提交的场景（与v1.0一致）

| 场景 | 原因 |
|:-----|:-----|
| `.claude/` 运行时文件（sessions/projects/telemetry） | .gitignore已排除 |
| E5敏感文件（.env, credentials.*等） | git_autocommit内置拦截 |
| pre-commit hook校验失败 | hook阻断=不应强行提交（autosweep后台清扫使用--no-verify跳过hook，因其处理的是非代码数据文件） |

---

## 6. 架构自检（情墨12项清单）

| 编号 | 审查项 | 结果 | 备注 |
|:----:|:-------|:----:|:-----|
| CH1 | 模块边界清晰 | ✅ | git_sweep单一职责：清扫未提交变更 |
| CH2 | 接口完整 | ✅ | 参数+返回值+错误处理已定义 |
| CH3 | 1+2架构 | ✅ | 不涉及数据获取 |
| CH4 | 第三方依赖 | ✅ | 无新增依赖 |
| CH5 | 循环依赖 | ✅ | git_sweep → git_autocommit → git CLI，无环 |
| CH6 | 单点故障 | ✅ | git_sweep失败不影响业务产出 |
| CH7 | 反模式 | ✅ | 不触发AP-01~AP-07 |
| CH8 | 影响范围 | ✅ | 仅改git_autocommit.ps1(1行) + daily_workflow.ps1(2行) + 新增git_sweep.ps1 |
| CH9 | API超时 | ✅ | 不涉及API调用 |
| CH10 | 回退方案 | ✅ | 删除git_sweep.ps1 + 移除daily_workflow中的调用 + 还原git_autocommit ValidateSet |
| CH11 | 通知关联 | ⚠️ | 需通知：红结(编码)+新安(验证)+红枫(部署)+千光(daily_workflow维护者) |
| CH12 | 红线合规 | ✅ | 不涉及数据编造/PDF删除/文档同步 |

---

## 7. 需求→代码核对清单

> 情墨+腰子勾签后放行

| # | 需求 | 实现位置 | 情墨 | 腰子 |
|:--|:-----|:--------|:----:|:----:|
| 1 | git_autocommit新增engineering模块 | `代码文件/tools/git_autocommit.py` ValidateSet行 | ☐ | ☐ |
| 2 | git_sweep日终安全网脚本 | `代码文件/tools/git_sweep.ps1` (新增) | ☐ | ☐ |
| 3 | daily_workflow末尾调用git_sweep | `代码文件/每日荐股/scripts/daily_workflow.py` 末尾 | ☐ | ☐ |
| 4 | engineering模块日志写入 | 复用git_autocommit.log | ☐ | ☐ |
| 5 | E5安全检查复用 | git_sweep→git_autocommit内置E5 | ☐ | ☐ |

---

## 8. 新增功能评估（A1-A10）

| 编号 | 评估项 | 结论 |
|:----:|:-------|:-----|
| A1 | 模块归属 | 工具层（`代码文件/tools/`） |
| A2 | 文件策略 | 新增1个(git_sweep.ps1)，修改2个(git_autocommit.ps1, daily_workflow.ps1) |
| A3 | 接口定义 | git_sweep: -Module(可选) -DryRun(可选) → JSON |
| A4 | 下游影响 | daily_workflow.ps1调用方 |
| A5 | 数据源 | 不涉及 |
| A6 | 第三方依赖 | 无 |
| A7 | 反模式 | 无触发 |
| A8 | 循环依赖 | 无 |
| A9 | 红线合规 | 通过 |
| A10 | 回退方案 | 删除git_sweep.ps1 + 移除daily_workflow调用 + 还原ValidateSet |
