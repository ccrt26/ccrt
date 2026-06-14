# F-GIT-UPLOAD-CLOSURE G6 放行归档记录

**日期**: 2026-06-12
**审计人**: 阿黑
**流程类型**: F-FIX / F-GATE
**前驱**: G0 ✅ → G1 ✅ → G2 ✅ → G3 ✅ → G4 ✅ → G5 ✅

> ⚠️ **历史 Git 上传收口归档记录，不适用于当前 ROLE_砺石最小字段预留_FIX 流程。**
> 本文件记载 F-GIT-UPLOAD-CLOSURE（GitHub 上传积压清理）的 G6 放行记录。
> F-ROLE-LISHI-METHOD-REVIEW-FIX-20260612 的 G6 放行以 `ROLE_砺石最小字段预留_FIX_G6放行归档记录` 为准。
> 不得作为当前砺石字段预留的 G6 放行依据。

---

## 提交信息

| 字段 | 值 |
|:-----|:---|
| Commit Hash | `8f7d2dab` |
| 提交时间 | 2026-06-12 16:07:43 +0800 |
| 消息 | `fix(git): close upload backlog and restore guarded autosweep` |
| 变更文件 | 392 files |
| (+) 新增 | 42,961 |
| (-) 删除 | 454,166 |

## 推送结果

```bash
git push origin codex-github-upload-guard
```
✅ `ab06c752..8f7d2dab codex-github-upload-guard -> codex-github-upload-guard`

---

## 最终判定 PASS 条件检查

| # | 条件 | 结果 |
|:--|:-----|:-----|
| 1 | 工作区无未处理上传积压，或仅剩 ignore 的本地运行时文件 | ✅ PASS — 294 → 7（剩余为其他流程新文件） |
| 2 | 运行时数据已从 Git 跟踪中剥离，但本地文件仍保留 | ✅ PASS — `data_full.json` `tushare/` `git_autocommit.log` 已 `git rm --cached` |
| 3 | autosweep 已从 report-only 改为 commit+push | ✅ PASS — `git_autosweep.py` 参数改为 `--commit --push` |
| 4 | git_guard 不再因 291 个积压 BLOCK | ✅ PASS — 7 个变更，降为 WARN |
| 5 | 无真实密钥 | ✅ PASS — 敏感扫描无真实密钥 |
| 6 | 所有 Python 语法通过 | ✅ PASS — 31 个 staged .py 全部通过 |
| 7 | push 成功 | ✅ PASS — `git push` 成功 |

---

## 产物清单

| 阶段 | 产物路径 |
|:-----|:---------|
| G0 | `临时报告/F-GIT-UPLOAD-CLOSURE-G0_scope_20260612.md` |
| G1 | `临时报告/F-GIT-UPLOAD-CLOSURE-G1_boundary_20260612.md` |
| G2 | `临时报告/F-GIT-UPLOAD-CLOSURE-G2_plan_20260612.md` |
| G4 | `临时报告/F-GIT-UPLOAD-CLOSURE-G4_selfcheck_20260612.md` |
| G5 | `00_项目地基/08_审计与验收/F-GIT-UPLOAD-CLOSURE-G5旧影复查报告_20260612.md` |
| G6 | `00_项目地基/08_审计与验收/F-GIT-UPLOAD-CLOSURE-G6放行归档记录_20260612.md` |

## 修复文件清单

| 文件 | 修复内容 |
|:-----|:---------|
| `00_项目地基/07_知识进化/.../build_qingshan_literature_card_to_rule_candidate_flow_v1_0.py` | 坏脚本语法修复（raw string delimiter） |
| `代码文件/tools/git_autosweep.py` | 新增 `is_git_ignored()`，阻止自动提交 ignore 命中的运行时数据 |
| `代码文件/每日荐股/scripts/generate_launchd.py` | autosweep 参数改为 `--commit --push` |
| `00_项目地基/08_审计与验收/*VALIDATOR-FIX-v1.0.1_G*_v1.0.1.md` (3 files) | 版本号重命名 `_v1.0.md` → `_v1.0.1.md`（通过 pre-commit 检查） |
