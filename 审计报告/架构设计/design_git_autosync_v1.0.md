# 设计文档：Git自动同步机制

**设计日期**: 2026-05-27
**设计者**: 情墨
pipeline_stage: complete
finance_confirmed: true
**代码等级**: L1（修改 pre-commit 安全基础设施 + 新增工具脚本）

---

## 1. 现状诊断

### 1.1 已有资产

| 组件 | 位置 | 作用 |
|:-----|:-----|:-----|
| `git_autocommit.ps1` | `代码文件/tools/` | 手动调用的提交工具，支持 DryRun/SkipHook |
| `pre-commit-check.ps1` | `.claude/hooks/` | git pre-commit hook，6项检查(A-F) |
| `pipeline-auth.ps1` | `.claude/hooks/shared/` | Check F 共享授权模块 |
| `write_protection_hook.ps1` | `代码文件/监督机制/` | Write/Edit 前置拦截 |

### 1.2 断点三重

| 断点 | 症状 | 根因 |
|:-----|:-----|:-----|
| **触发缺失** | 无文件变动→自动提交的链路 | 没有 PostToolUse hook、没有定期 sweep cron |
| **阻拦过宽** | 日志16次 FAILED，全部因 Check F 拦截 | `ProtectedPaths = ^代码文件[\\/]` 太粗，数据/日志被当作代码拦截 |
| **推送缺失** | commit 成功后也不 push | `git_autocommit.ps1` 只做 add+commit，无 push 逻辑 |

### 1.3 当前积压

- **107 个未提交文件**（含 代码文件/数据/*.json、临时报告/、.claude/ 配置、每日荐股脚本等）
- 最近成功 commit 的只有深度分析（用了 SkipHook 绕过）

---

## 2. 方案设计

### 2.1 核心思路

```
文件变更 → 分类器 → 自动提交通道（数据/日志/报告） → git push
                  → 管线通道（代码文件，走§七流程）
```

**一条规则定生死**：`代码文件/` 下的 `.ps1/.py/.psm1/.bat` → 管线保护；其他一切 → 自动提交。

### 2.2 文件分类矩阵

```
AUTO-COMMIT (无需管线，自动提交+推送):
  .claude/**           M类元操作
  临时报告/**          对话日志/临时产出
  历史数据/**          历史快照
  审计报告/**          审计/设计文档
  重点股票/股票报告/**  日报产出
  重点股票/深度分析/**  深度分析产出
  重点股票/次日评估/**  后评估产出
  重点股票/预判记录/**  预判记录
  重点股票/消息面数据/** 事件数据
  每日荐股/股票报告/**  荐股报告
  每日荐股/评估报告/**  评估数据
  模拟交易/持仓记录/**  持仓快照
  模拟交易/每日快照/**  交易快照
  模拟交易/绩效报告/**  绩效报告
  项目成员/**          团队名册
  CLAUDE.md           项目指令
  *.log               日志文件
  *.json              数据文件(代码文件/数据/)
  *.jsonl             数据文件(代码文件/数据/)
  *.csv               数据文件
  *.txt               报告文本

PIPELINE-REQUIRED (必须走§七流程):
  代码文件/**/*.ps1    脚本
  代码文件/**/*.py     Python
  代码文件/**/*.psm1   模块
  代码文件/**/*.bat    批处理
  模拟交易/交易引擎/**  交易核心
  模拟交易/否决审查/**  风控否决
  模拟交易/分析/**      交易分析
  模拟交易/共享模块/**  交易共享
  模拟交易/展示/**      交易展示
  模拟交易/工具/**      交易工具
```

### 2.3 新增组件

#### A. `git_autosweep.ps1` — 自动清扫脚本（新建）

- **位置**: `代码文件/tools/git_autosweep.py`
- **等级**: L0（工具/数据层）
- **逻辑**:
  1. `git status --porcelain` 获取所有变更
  2. 按 §2.2 分类矩阵拆分文件
  3. AUTO-COMMIT 文件 → `git add` + `git commit --no-verify`（绕过 pre-commit hook，因为数据文件不需要管线检查）
  4. PIPELINE 文件 → 调用现有 `git_autocommit.ps1`（不 SkipHook，让 hook 正常检查）
  5. commit 成功后 → `git push` 到所有远程

#### B. 修改 `pipeline-auth.ps1` — 增加 AutoCommit 路径白名单

- **修改点**: `ProtectedPaths` 前增加 `$script:AutoCommitPaths`
- **新增逻辑**: `Test-PipelineAuthorization` 第一步先检查是否 AutoCommit 路径 → 是则直接返回 Authorized
- **效果**: 即使手动 `git commit`（不用 --no-verify），数据文件也能通过 Check F

#### C. 修改 `pre-commit-check.ps1` — Check F 增加 AutoCommit 豁免

- **修改点**: Check F 开头检查 staged files 是否全部属于 AutoCommit 路径 → 是则跳过管线检查
- **效果**: 双重保险，数据文件提交绝不被拦截

#### D. 新增定时任务 — 每小时自动清扫

- **类型**: CronCreate durable
- **cron**: `7 */1 * * *`（每小时第7分钟）
- **prompt**: "执行 git_autosweep.ps1 清扫未提交变更并推送到 GitHub"

#### E. Push 策略（复用 memory 中的代理回退规则）

```
1. git push origin (github.com 直连)
2. 失败 → git push ip-ssh (20.205.243.166 直连)
3. 失败 → git push api-origin (api.github.com)
4. 全部失败 → 记录到 git_autocommit.log，下次 sweep 重试
```

### 2.4 修改影响分析

| 文件 | 变更类型 | 影响范围 | 风险 |
|:-----|:---------|:--------|:----:|
| `.claude/hooks/shared/pipeline-auth.py` | 修改 | Check F + write_protection_hook | 中：安全基础设施 |
| `.claude/hooks/pre-commit-check.py` | 修改 | 所有 git commit | 中：git hook |
| `代码文件/tools/git_autosweep.py` | 新建 | 无现有文件 | 低：独立新文件 |
| `.claude/scheduled_tasks.json` | CronCreate 写入 | 定时任务 | 低 |

---

## 3. 设计决策

- **分类依据选扩展名而非路径**：`代码文件/数据/` 下的 `.json` 自动提交，但 `代码文件/每日荐股/scripts/` 下的 `.ps1` 管线保护。扩展名分类比路径分类更精确、更不容易被绕过。
- **AUTO-COMMIT 用 --no-verify**：数据/日志/报告不需要版本一致性检查（Check A）、不需要 docx 同步检查（Check C）。跳过整个 hook 比在 hook 里逐条豁免更简洁，也避免 Check F 的"假阳性拦截"。
- **每小时而非实时**：Claude Code 没有 PostToolUse hook。实时文件监听不可行。每小时清扫足够覆盖所有变更，且不会因频繁提交污染 git log。
- **不改动 write_protection_hook.ps1**：写保护 hook 阻止的是"未经授权的写入"，不是"未经授权的提交"。两者独立。数据文件的写入不需要管线授权，这已经由现有逻辑处理（AutoCommit 路径不在 ProtectedPaths 中）。
- **push 放在 sweep 脚本里，不放 post-commit hook**：git post-commit hook 在 Windows 上不稳定，且每个 commit 都 push 太频繁。sweep 脚本一次清扫、一次 push，干净。

---

## 4. 数据流

```
┌─────────────────────────────────────────────────────────┐
│                    git_autosweep.ps1                     │
│                                                         │
│  git status --porcelain                                 │
│         │                                               │
│         ▼                                               │
│  ┌─────────────┐     ┌──────────────────┐               │
│  │ .ps1/.py等  │     │ .json/.md/.log等  │               │
│  │ 代码文件     │     │ 数据/报告/配置    │               │
│  └──────┬──────┘     └────────┬─────────┘               │
│         │                     │                         │
│         ▼                     ▼                         │
│  ┌──────────────┐    ┌──────────────────┐               │
│  │ 检查管线令牌  │    │ git add + commit │               │
│  │ active+红结?  │    │ --no-verify      │               │
│  └──────┬───────┘    └────────┬─────────┘               │
│         │                     │                         │
│         ▼                     │                         │
│  ┌──────────────┐             │                         │
│  │ git commit   │             │                         │
│  │ (hook正常)   │             │                         │
│  └──────┬───────┘             │                         │
│         │                     │                         │
│         └──────────┬──────────┘                         │
│                    ▼                                    │
│           ┌───────────────┐                             │
│           │  git push     │                             │
│           │  (3级回退)    │                             │
│           └───────────────┘                             │
└─────────────────────────────────────────────────────────┘
```

---

## 5. 边界情况

| 场景 | 处理 |
|:-----|:-----|
| 无变更 | 静默退出，不产生空 commit |
| 只有管线文件变更但无活跃管线 | 跳过管线文件，仅提交自动文件；管线文件留在工作区等待管线启动 |
| push 全部失败 | 记录日志，commit 保留在本地，下次 sweep 重试 push |
| sweep 正在运行中再次触发 | 文件锁 `sweep.lock`，发现已有进程则退出 |
| merge conflict | 跳过 push，记录 WARN 日志 |
| 大文件（>500KB PDF） | 正常提交；pre-commit E4 检查为 WARN 不阻断 |

---

## 6. 需求→代码核对清单

| 编号 | 检查项 | 条款 | 情墨勾 | 腰子勾 |
|:----:|:------|:----:|:-----:|:-----:|
| R1 | 数据/报告/配置自动提交不被管线拦截 | §2.2 | ☐ | ☐ |
| R2 | 代码文件(.ps1/.py/.psm1/.bat)仍受管线保护 | §2.2 | ☐ | ☐ |
| R3 | 每小时定时清扫正常运行 | §2.3-D | ☐ | ☐ |
| R4 | commit 后自动 push 到 GitHub | §2.3-E | ☐ | ☐ |
| R5 | 不产生空 commit | §5 | ☐ | ☐ |
| R6 | 不修改 write_protection_hook 行为 | §3 | ☐ | ☐ |
| R7 | 代理回退 push 策略 | §2.3-E | ☐ | ☐ |
| R8 | sweep 并发锁 | §5 | ☐ | ☐ |

---

> 下一步：闸门1b PASS → 红结编码实现
