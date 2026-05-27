# 架构设计：清理冗余分析逻辑

> pipeline_stage: complete | 版本: v1.0 | 日期: 2026-05-27 | 执行者: 情墨
> finance_confirmed: true | 腰子确认: 2026-05-27 | 全团(山猫/玉夜/流金/青山)一致通过
> 任务: cleanup_redundant_analysis_logic

## 一、变更概述

删除8个冗余/废弃文件，消除与正式分析逻辑（白皮书定义）的潜在冲突。所有删除项均通过依赖分析验证——无活跃代码引用、无调度入口、无工作流调用。

## 二、删除清单（按风险降序）

### L0级（纯工具/废弃副本，零运行时影响）

| # | 文件路径 | 大小 | 删除理由 | 引用检查结果 |
|:--|:--------|:----|:--------|:-----------|
| 1 | `代码文件/每日荐股/分析逻辑/scoring_engine_v2_legacy.py` | 2359行/98KB | 评分引擎完整副本，与 `engine/` 包功能重复。有独立 `main()` 入口可产出不同评分结果 | 仅 `_split_v2.py` 引用（该文件同步删除）；`审计报告/依赖分析_评分引擎.md` 文档引用（不阻碍删除） |
| 2 | `代码文件/每日荐股/分析逻辑/_split_v2.py` | 拆分工具 | 将旧大文件拆分到 `engine/` 子模块的工具，已完成使命。重新运行会覆盖现有 engine/ 文件 | 仅 `审计报告/缺陷台账.md` 和 `临时报告/中断影响评估` 历史记录引用 |
| 3 | `代码文件/每日荐股/scripts/gen_daily_html_deprecated.ps1` | 24.7KB | 废弃版报告生成器，与当前 `gen_daily_html.ps1` 仅输出文件名不同 | **零引用** |
| 4 | `代码文件/每日荐股/scripts/gen_doc_v2_deprecated.ps1` | 43.8KB | 与当前 `gen_doc_v2.ps1` **逐字节完全相同** | **零引用** |
| 5 | `代码文件/tools/md_to_docx_deprecated.py` | 5.2KB | 与当前 `md_to_docx.py` 功能重复 | **零引用** |
| 6 | `代码文件/每日荐股/分析逻辑/eus_simulation.py` | ~300行 | 重复 `calc_ma()` 函数，第10行硬编码PowerShell语法到Python中，脚本**不可运行** | 仅 `.claude/agents/情墨-知识库/01-项目模块全景.md` 文档条目引用 |
| 7 | `代码文件/重点股票/分析逻辑/gen_doc.ps1` | ~418行 | 硬编码v1.2白皮书内容（六维权重/评分阈值均过时）。自身注释标注"遗留硬编码版本"。正版入口为 `重点股票/分析逻辑/gen_doc.ps1`(薄包装器→build_docx.ps1) | 仅文档/审计报告引用，无活跃工作流调用 |
| 8 | `_gen_html.py` | ~50行 | 根目录临时硬编码脚本（特定股票+日期），非正式流水线工具 | **零引用** |

## 三、附加修复

### CLAUDE.md 白皮书版本引用过期
- **行48**: 重点股票跟踪分析引用 `v3.4` → 修正为 `v3.5`（最新文件已存在）
- **行53**: 模拟交易引用 `v1.7` → 修正为 `v1.6`（v1.7 文件不存在）

### 文档同步更新
- `.claude/agents/情墨-知识库/01-项目模块全景.md` — 移除 `eus_simulation.py` 和 `gen_doc.ps1` 条目

## 四、代码分级

全部8项均为 **L0级**（工具/废弃副本删除）：
- 不改变任何函数签名/接口/数据格式
- 不涉及评分/交易/风控逻辑变更
- 不影响白皮书定义的任何分析流程
- 删除后无任何活跃代码引用断裂

## 五、回滚方案

所有文件通过 git revert 一键恢复：
```bash
git revert <cleanup-commit-hash>
```
无需数据库回滚、无需配置变更、无需重启服务。

## 六、需求→代码核对清单

- [ ] 删除 scoring_engine_v2_legacy.py — 不影响 engine/ 包评分
- [ ] 删除 _split_v2.py — 不影响 engine/ 模块结构
- [ ] 删除 gen_daily_html_deprecated.ps1 — 不影响 gen_daily_html.ps1 报告生成
- [ ] 删除 gen_doc_v2_deprecated.ps1 — 不影响 gen_doc_v2.ps1
- [ ] 删除 md_to_docx_deprecated.py — 不影响 md_to_docx.py
- [ ] 删除 eus_simulation.py — 不影响白皮书v2.9 §五 EUS公式
- [ ] 删除 代码文件/重点股票/分析逻辑/gen_doc.ps1 — 不影响 build_docx.ps1 正版生成
- [ ] 删除 _gen_html.py — 无依赖
- [ ] CLAUDE.md 版本引用修正 — 重点股票v3.5, 模拟交易v1.6
- [ ] 模块全景文档同步移除已删除条目
- [ ] git commit 后验证 `git status` 清洁
