# 设计文档：git_autosweep.py macOS迁移修复

**设计日期**: 2026-05-29
**设计者**: 情墨
pipeline_stage: complete
finance_confirmed: N/A（纯工程工具，不涉及金融逻辑）
**代码等级**: L0（工具/数据层，不涉及策略/风控/交易）

---

## 0. 问题诊断

| 断点 | 现状 |
|:-----|:-----|
| 定时任务 | `73cfe6cb` 每小时:07触发，运行 `python3 代码文件/tools/git_autosweep.py` |
| 目标脚本 | **不存在**（仅有 `_win32_legacy/代码文件/tools/git_autosweep.ps1`） |
| 上次成功提交 | `5c3a336` 2026-05-28 07:29 |
| 当前积压 | 大量未提交变更（.claude/配置、临时报告/脚本、代码文件/等） |

**根因**：PowerShell→Python迁移时遗漏了 `git_autosweep.py`，定时任务指向空文件，每小时静默失败。

## 1. 方案设计

### 1.1 核心思路

从 `_win32_legacy/代码文件/tools/git_autosweep.ps1` 移植核心逻辑到 Python，针对 macOS 环境简化。

### 1.2 与旧设计的关系

本设计是 [design_git_autosync_v1.0.md](design_git_autosync_v1.0.md) 的 macOS 适配版。原设计中的 PowerShell hook 修改方案（pipeline-auth.ps1 / pre-commit-check.ps1）在 macOS 上已废弃——这些 hook 文件已被删除（git status 确认为 D）。

### 1.3 新增文件

| 文件 | L级 | 行数上限 | 说明 |
|:-----|:----:|:-------:|:-----|
| `代码文件/tools/git_autosweep.py` | L0 | ≤180 | 独立脚本，不依赖项目模块 |

### 1.4 不变更文件

- `代码文件/tools/git_autocommit.py` — 不修改，autosweep 独立运行
- `.claude/scheduled_tasks.json` — cron 任务已正确指向 `git_autosweep.py`，无需修改

## 2. 脚本设计

### 2.1 接口

```
python3 代码文件/tools/git_autosweep.py [--dry-run] [--skip-push]
```

| 参数 | 类型 | 必填 | 说明 |
|:-----|:----:|:----:|:-----|
| `--dry-run` | flag | 否 | 仅显示分类结果，不实际提交 |
| `--skip-push` | flag | 否 | 提交但不推送 |

**返回值**: JSON → stdout，退出码 0=成功/无变更，1=错误

### 2.2 执行流程

```
1. 文件锁检查 (.claude/sweep.lock, 10分钟过期)
2. git status --porcelain → 获取所有变更
3. 分类器:
   ├─ auto: .json/.jsonl/.csv/.txt/.log/.md/.pdf/.docx/.html
   │        或路径匹配 AutoCommitPaths（.claude/、临时报告/、历史数据/等）
   └─ pipeline: .py/.ps1/.psm1 且在代码文件/或模拟交易/核心目录下
4. E5敏感文件检查 → 拦截 .env/credentials/等
5. PDF删除拦截 → unstage 被删除的 .pdf 文件（红线§1.7）
6. auto 文件 → git add + git commit --no-verify
7. pipeline 文件 → 检查 pipeline_active.json 令牌 → 有活跃令牌才提交
8. git push origin（单级推送，macOS 网络稳定）
9. 写日志 → 临时报告/git_autocommit.log（JSONL 格式）
10. 释放锁 → 输出 JSON 结果
```

### 2.3 分类规则（与 PS1 一致）

**AUTO-COMMIT 路径前缀**:
```
.claude/、临时报告/、历史数据/、审计报告/、重点股票/股票报告/、
重点股票/深度分析/、重点股票/次日评估/、重点股票/预判记录/、
重点股票/消息面数据/、每日荐股/股票报告/、每日荐股/评估报告/、
模拟交易/持仓记录/、模拟交易/每日快照/、模拟交易/绩效报告/、
项目成员/、CLAUDE.md
```

**PIPELINE 目录**:
```
代码文件/、模拟交易/交易引擎/、模拟交易/否决审查/、模拟交易/分析/、
模拟交易/共享模块/、模拟交易/展示/、模拟交易/工具/
```

**分类逻辑**: 先判断是否在 pipeline 目录 + 代码扩展名(.py/.ps1/.psm1) → 是=pipeline，否=auto

### 2.4 与原 PS1 的差异

| 项目 | PS1 原版 | Python 版 |
|:-----|:--------|:---------|
| 三级推送 | origin → ip-ssh → api-origin | 仅 origin（macOS 单网卡稳定） |
| 锁机制 | 文件时间戳 | 文件时间戳（同逻辑） |
| 日志 | JSONL → git_autocommit.log | 同格式，同路径 |
| E5 检查 | 内联正则 | 内联正则（复制自 git_autocommit.py） |
| PDF 拦截 | git reset HEAD | git restore --staged（macOS git 2.40+） |
| hook 依赖 | 无 | 无 |

## 3. 边界情况

| 场景 | 处理 |
|:-----|:-----|
| 无变更 | 静默退出，exit 0 |
| 锁未过期 | 跳过，exit 0（其他实例运行中） |
| 只有 pipeline 文件但无活跃令牌 | 跳过 pipeline 文件，auto 文件正常提交 |
| push 失败 | commit 保留本地，记录 WARN，下次 sweep 重试 |
| 所有文件被 E5 拦截 | 不提交，记录 BLOCKED 日志 |
| 空 commit（add 后无有效变更） | 跳过 commit，exit 0 |

## 4. Token 影响评估

| 维度 | 评估 |
|:-----|:-----|
| 新增模板体积 | 0（独立脚本，无模板输出） |
| 定时触发频率 | 每小时 :07，静默退出时零输出 |
| Cron prompt Token | 当前prompt 约150字，修复后无需修改 |
| API 调用次数 | 0（纯本地 git 操作） |
| 上下文消耗 | 0（cron 任务在后台运行，不占对话上下文） |

**结论：零 Token 增量。**

## 5. 架构自检（12项）

| 编号 | 审查项 | 结果 | 备注 |
|:----:|:-------|:----:|:-----|
| CH1 | 模块边界清晰 | ✅ | 单一职责：扫描→分类→提交→推送 |
| CH2 | 接口完整 | ✅ | 2个可选flag + JSON返回值 + 退出码 |
| CH3 | 1+2架构 | ✅ | 不涉及数据获取 |
| CH4 | 第三方依赖 | ✅ | 仅用 Python stdlib（subprocess, json, os, re, datetime, pathlib） |
| CH5 | 循环依赖 | ✅ | 独立脚本，无 import 项目模块 |
| CH6 | 单点故障 | ✅ | push 失败不影响 commit；脚本失败不影响业务 |
| CH7 | 反模式 | ✅ | 不触发 AP-01~AP-07 |
| CH8 | 影响范围 | ✅ | 新增单文件，不修改任何现有文件 |
| CH9 | API超时 | ✅ | 不涉及 API 调用 |
| CH10 | 回退方案 | ✅ | 删除 git_autosweep.py → 停用 cron 任务即可 |
| CH11 | 通知关联 | ✅ | 仅红结编码，无需通知其他角色 |
| CH12 | 红线合规 | ✅ | PDF删除拦截已内置；不涉及数据编造 |

## 6. 需求→代码核对清单

| # | 需求 | 情墨 | 腰子 |
|:--|:-----|:----:|:----:|
| R1 | 每小时自动扫描未提交文件 | ☐ | N/A |
| R2 | 数据/报告/配置自动提交+推送 | ☐ | N/A |
| R3 | 代码文件仅在有活跃管线令牌时提交 | ☐ | N/A |
| R4 | E5敏感文件拦截 | ☐ | N/A |
| R5 | PDF删除拦截（红线§1.7） | ☐ | N/A |
| R6 | 并发锁防重入 | ☐ | N/A |
| R7 | 无变更静默退出 | ☐ | N/A |
| R8 | JSON 输出+日志记录 | ☐ | N/A |

---

> 下一步：闸门1b PASS（新安+旧影审查） → 红结编码实现
