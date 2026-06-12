# F-GIT-SYNC-ROOT-FIX G2 技术方案

**日期**: 2026-06-13
**流程编号**: F-GIT-SYNC-ROOT-FIX-20260613

---

## 修复点清单

| # | 修复点 | 文件 | 操作 |
|:--|:-------|:-----|:------|
| 1 | autosweep 阻挡规则过严 | `代码文件/tools/git_autosweep.py` | `AUTO_COMMIT_BLOCKED`: `.claude/commands/` → 仅挡 `.json\|.local\|.secret\|.token\|.key`；`.claude/agents/` → 仅挡敏感扩展名 |
| 2 | .gitignore 补全 | `.gitignore` | 追加 `.claude/signal_deep_analysis.json`, `health.json`, `score_history_index.json` |
| 3 | 停止跟踪运行时 signal | `.claude/signal_deep_analysis.json` | `git rm --cached` |
| 4 | 重装 launchd autosweep | launchd plist | `generate_launchd.py --install git_autosweep` |
| 5 | 精准 stage 32 个文件 | — | 按 G1 允许范围 |
| 6 | 验证 | — | py_compile / pytest / git_guard / plist |
