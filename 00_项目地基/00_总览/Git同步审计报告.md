# Git 同步审计报告

> 审计日期: 2026-06-04 | 分支: `master`
> ⛔ 禁止 git add . / git commit / git push / git rm / git checkout / git reset

---

## 一、全局概览

| 指标 | 数值 |
|:-----|:-----|
| 已修改（tracked） | 67 文件 |
| 未跟踪（untracked） | ~242 文件 |
| tracked-but-ignored（.gitignore 生效前已跟踪） | **784 文件** |

---

## 二、已修改文件分类（67 files, +11,849 / -125,714 行）

### 2.1 项目制度·可提交候选（19 files）

```
.claude/agents/              (7 files — 角色定义，属项目制度)
.claude/commands/            (12 files — 命令定义，属项目制度)
.claude/knowledge/           (2 files — 深度分析铁律、角色边界宪章)
```

### 2.2 本地/运行时配置·需确认（2 files）

```
.claude/settings.json        ⚠️ 需人工确认后提交（含本地路径/环境偏好）
.claude/signal_alert.json    ⛔ 不应提交 — 运行时告警状态，非源码
```

### 2.3 应提交 — 项目核心代码/流程引擎（4 files）

```
CLAUDE.md
events/event_rules.yaml
scripts/log_utils.py
scripts/pipeline_engine.py
scripts/test_workflow.py
```

### 2.4 应提交 — 工程脚本与共享模块（7 files）

```
.claude/hooks/shared/pipeline_auth.py
代码文件/tools/batch_gen_daily_pdfs.py
代码文件/tools/daily_orchestrator.py
代码文件/tools/sync_report_json.py
代码文件/每日荐股/scripts/batch_data_collector.py
代码文件/每日荐股/scripts/daily_workflow.py
代码文件/监督机制/write_protection_hook.py
代码文件/监督机制/日报U检查流程.py
代码文件/监督机制/data_quality_tracker.md
代码文件/重点股票/Invoke-DailyReportParser.py
```

### 2.5 应提交 — 业务逻辑分析文档（4 files）

```
重点股票/分析逻辑/日报v3.6_schema.json
重点股票/分析逻辑/日报v3.6_字段字典.md
重点股票/分析逻辑/重点股票跟踪分析逻辑白皮书_v3.6.md
重点股票/基线/多瑞医药(301075)_baseline_2026W22.json
重点股票/基线/科大讯飞(002230)_baseline_2026W22.json
```

### 2.6 本轮不提交 — 需单独确认处理（20 files）

```
代码文件/数据/data_full.json
  # 132,765 行变更 — 运行时数据快照，本轮不提交，后续单独确认处理
  # ⛔ 不得 git checkout -- 恢复；未做出决定前保留工作区状态不变
代码文件/数据/tushare/daily_basic/      (10 files)
代码文件/数据/tushare/fina_indicator/   (1 file)
代码文件/数据/tushare/holder_number/    (1 file)
代码文件/数据/tushare/manifest.json
代码文件/数据/tushare/margin_detail/   (9 files)
```

### 2.7 不应提交 — 历史遗留已跟踪报告（2 files, 待 git rm --cached）

```
重点股票/股票报告/上海电气(601727)日报_20260526.html   # 2 行变更
重点股票/股票报告/上海电气(601727)日报_20260526.md    # 2 行变更
```

> `.gitignore` 已排除 `重点股票/股票报告/`，但这 2 个文件是旧提交遗留。**本次不提交**，后续 `git rm --cached`。

---

## 三、未跟踪文件分类（~242 files）

### 3.1 应提交 — 地基重构产出（~80 files）

```
00_项目地基/          # 完整地基目录（契约/schema/闸门/审计/总账/唤醒卡）
scripts/              # 新增 22 个闸门/工具脚本
统一解读/             # 统一解读协议
MEMORY.md
```

### 3.2 应提交 — 新增闸门脚本（22 files）

| 脚本 | 用途 |
|:-----|:------|
| `scripts/build_canonical_report.py` | canonical 构建 |
| `scripts/check_canonical_report_shadow.py` | 影子校验 |
| `scripts/check_report_golden_diff.py` | Golden Diff |
| `scripts/check_canonical_pipeline_gate.py` | 发布前总闸门 |
| `scripts/check_canonical_render_diff.py` | 渲染 diff |
| `scripts/render_report_from_canonical.py` | canonical 渲染 |
| `scripts/run_canonical_shadow.py` | E1 执行器 |
| `scripts/check_baseline_authority.py` | Baseline 权威 |
| `scripts/check_numeric_source_consistency.py` | 数值一致性 |
| `scripts/check_freshness_degradation.py` | 新鲜度 |
| `scripts/check_md_sidecar_consistency.py` | MD/sidecar 一致性 |
| `scripts/check_daily_data_completeness.py` | 日报数据完整性 |
| `scripts/check_daily_p0_template_pollution.py` | P0 模板污染 |
| `scripts/check_daily_release_gate.py` | 发布闸门 |
| `scripts/check_daily_report_style.py` | 报告样式 |
| `scripts/check_deep_collaborative_interpretation.py` | 深度分析协作解读 |
| `scripts/check_report_authority_lineage.py` | 报告权威口径 |
| `scripts/check_runtime_entry_authority.py` | 运行时入口权威 |
| `scripts/eval_backfill.py` | 后评估回填 |
| `scripts/eval_hook_backfill_refs.py` | eval_hook 引用回填 |
| `scripts/knowledge_evolution.py` | 知识库进化 |
| `scripts/knowledge_registry_check.py` | 知识库注册表检查 |
| `scripts/resolve_current_baseline.py` | 基线解析器 |

### 3.3 ⛔ 禁止提交 — 敏感文件（1 file）

```
.claude/auth_tokens.json          # ⛔ 包含鉴权 Token，永远不得提交
```

> **操作建议：** 确认 `.gitignore` 已有 `.claude/settings.local.json`，但无 `auth_tokens.json`。建议追加到 `.gitignore`（当前不执行）。

### 3.4 不应提交 — 需用户确认是否为 GitHub Pages 发布物（10 dirs）

```
docs/daily_reports/000967/20260603/
docs/daily_reports/002230/20260603/
docs/daily_reports/300450/20260603/
docs/daily_reports/300736/20260603/
docs/daily_reports/301075/20260603/
docs/daily_reports/600114/20260603/
docs/daily_reports/601689/20260603/
docs/daily_reports/601727/20260603/
docs/daily_reports/603019/20260603/
docs/daily_reports/603092/20260603/
```

> ⚠️ **需用户确认** — 若 `docs/daily_reports/` 是 GitHub Pages 发布物，则必须提交；否则不应提交。当前未做决定。

### 3.5 不应提交 — 运行时新鲜度报告（2 files）

```
重点股票/次日评估/freshness_report_20260603.json
重点股票/次日评估/freshness_report_20260604.json
重点股票/分析逻辑/interpretation_schema.json
```

### 3.6 已在 .gitignore 中，不会意外提交

`代码文件/数据/tushare/`、`代码文件/数据/data_full*.json` 等已在 `.gitignore` 中，不会意外提交。

---

## 四、Tracked-but-ignored 历史遗留文件（784 files）

这些文件被 `.gitignore` 排除，但因为 **在添加 .gitignore 前已被 git tracked**，所以 `git status` 不显示它们，但它们仍存在于仓库历史中。

| 类别 | 数量 | 建议 |
|:-----|:----:|:-----|
| `代码文件/数据/tushare/*` | ~120 | ⚠️ 不应在 repo 中，建议 `git rm --cached` |
| `_win32_legacy/临时报告/*.ps1` | ~7 | 旧 Windows 调度脚本，建议 `git rm --cached` |
| `临时报告/`（深度分析/PDF/HTML） | ~40 | 临时生成产物，建议 `git rm --cached` |
| `logs/checklist/*` | ~60+ | 流程日志，不建议提交 |
| `历史数据/` | ~大量 | 运行时数据，不应跟踪 |
| `保护机制/` | ~少量 | 设计文档 |
| `模拟交易/` | ~少量 | 运行时数据 |
| `审计报告/` | ~80+ | 已迁移到 00_项目地基，旧路径可清理 |
| `统一解读/` | ~少量 | 已迁移到 00_项目地基 |
| 其他 | ~654 | `.claude/knowledge/`、`金融铁律/`、`项目成员/` 等设计文档 |

---

## 五、建议的提交拆分

> ⛔ **禁止 git add .** — 必须逐路径精确添加，防止误提交运行时数据。
> ⛔ 以下仅为建议，不实际执行。

### Commit 1：地基重构 — 00_项目地基 + MEMORY.md + 统一解读（~80 files）

```bash
git add 00_项目地基/
git add MEMORY.md
git add 统一解读/
```

### Commit 2：全部闸门脚本（~25 files）

```bash
git add scripts/check_baseline_authority.py \
       scripts/check_numeric_source_consistency.py \
       scripts/check_freshness_degradation.py \
       scripts/check_md_sidecar_consistency.py \
       scripts/check_report_authority_lineage.py \
       scripts/check_runtime_entry_authority.py \
       scripts/check_daily_data_completeness.py \
       scripts/check_daily_p0_template_pollution.py \
       scripts/check_daily_release_gate.py \
       scripts/check_daily_report_style.py \
       scripts/check_deep_collaborative_interpretation.py \
       scripts/build_canonical_report.py \
       scripts/check_canonical_report_shadow.py \
       scripts/check_report_golden_diff.py \
       scripts/check_canonical_pipeline_gate.py \
       scripts/check_canonical_render_diff.py \
       scripts/render_report_from_canonical.py \
       scripts/run_canonical_shadow.py \
       scripts/eval_backfill.py \
       scripts/eval_hook_backfill_refs.py \
       scripts/knowledge_evolution.py \
       scripts/knowledge_registry_check.py \
       scripts/resolve_current_baseline.py
```

### Commit 3：核心引擎修复（5 files）

```bash
git add CLAUDE.md \
       events/event_rules.yaml \
       scripts/log_utils.py \
       scripts/pipeline_engine.py \
       scripts/test_workflow.py
```

### Commit 4：项目制度与命令定义（19 files，确认后）

```bash
git add .claude/agents/ \
       .claude/commands/ \
       .claude/knowledge/ \
       .claude/hooks/shared/pipeline_auth.py
# .claude/settings.json  — 需人工确认后再添加
# .claude/signal_alert.json — 不应提交
```

### Commit 5：日报产出脚本 + 分析基线（10+ files）

```bash
git add 代码文件/tools/daily_orchestrator.py \
       代码文件/tools/batch_gen_daily_pdfs.py \
       代码文件/tools/sync_report_json.py \
       代码文件/每日荐股/scripts/daily_workflow.py \
       代码文件/每日荐股/scripts/batch_data_collector.py \
       代码文件/监督机制/write_protection_hook.py \
       代码文件/监督机制/日报U检查流程.py \
       代码文件/监督机制/data_quality_tracker.md \
       代码文件/重点股票/Invoke-DailyReportParser.py \
       重点股票/分析逻辑/ \
       重点股票/基线/
```

---

## 六、越权边界汇总

| 约束 | 状态 |
|:-----|:-----|
| 本次只审计、不提交 | ✅ 未执行任何 git add/commit |
| `auth_tokens.json` 未提交 | ✅ 在 untracked 中，明确标注禁止 |
| `data_full.json` 本轮不提交，后续单独确认 | ✅ 不使用 `git checkout --` 恢复 |
| `tushare/*` 未主动添加 | ✅ .gitignore 已排除 |
| `股票报告/*` 当前已 tracked 的 2 文件仅在 modified 中 | ✅ 已标识为不提交 |
| `docs/daily_reports/*` 待用户确认 | ✅ 标注需确认 |
| `settings.json` 需人工确认 | ✅ 标注后添加 |
| 784 tracked-but-ignored 未处理 | ✅ 仅审计，未 `git rm --cached` |
