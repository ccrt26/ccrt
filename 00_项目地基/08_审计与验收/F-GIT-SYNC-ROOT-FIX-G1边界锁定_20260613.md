# F-GIT-SYNC-ROOT-FIX G1 边界锁定

**日期**: 2026-06-13
**流程编号**: F-GIT-SYNC-ROOT-FIX-20260613

---

## 允许提交

| 分类 | 路径 | 类型 |
|:-----|:-----|:------|
| 角色文档 | `.claude/agents/*.md` (4 files) | M/?? |
| 命令文档 | `.claude/commands/*.md` (2 files) | M/?? |
| 架构设计 | `00_项目地基/02_数据架构重设计/` (2 files) | M/?? |
| 权威注册表 | `00_项目地基/02_权威注册表/capability_registry.json` | M |
| 流程角色 | `00_项目地基/05_流程与角色/role_matrix.json` | M |
| 审计验收 | `00_项目地基/08_审计与验收/` (8 files) | ?? |
| 测试 | `tests/test_d04_fallback.py` | ?? |
| 数据代码 | `代码文件/数据/unified_data_source.py` | ?? |
| 脚本 | `代码文件/每日荐股/scripts/*.py` (4 files) | M/?? |
| l2_cache 文档 | `代码文件/数据/l2_cache/.gitkeep` + `README.md` | ?? |
| 团队名册 | `项目成员/团队名册_v1.9.*` (3 files) | M |

## 禁止提交（内容变更）

| 路径 | 处理方式 |
|:-----|:---------|
| `.claude/signal_deep_analysis.json` 内容变更 | `git rm --cached` 停止跟踪 |
| `代码文件/数据/l2_cache/*.db` / `*.db-*` | 已有 .gitignore 覆盖 |
| `代码文件/数据/l2_cache/backup/` | 已有 .gitignore 覆盖 |
| `代码文件/数据/l2_cache/health.json` | 追加到 .gitignore |
| `代码文件/数据/l2_cache/score_history_index.json` | 追加到 .gitignore |
| `代码文件/数据/l2_cache/operation_log.jsonl` | 追加到 .gitignore |
| `代码文件/数据/l2_cache/shadow_diff_log.jsonl` | 追加到 .gitignore |

## autosweep 阻挡规则修正

当前 `AUTO_COMMIT_BLOCKED` 中 `r'^\.claude/commands/'` 和 `r'^\.claude/agents/'` 一刀切阻挡所有文件，
应改为仅阻挡敏感文件（`.json` `.local` `.secret` `.token` `.key`），
放行 `.md` 文档的自动提交。
