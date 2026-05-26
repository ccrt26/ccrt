# 回滚方案 — git_autocommit.ps1

> **回滚对象**：`代码文件/tools/git_autocommit.ps1` | **L级**：L0  
> **日期**：2026-05-26 | **执行人**：红枫

## 回滚触发条件

| 条件 | 严重度 |
|:-----|:------:|
| git_autocommit 导致 pre-commit hook 误阻断 | P1 |
| git_autocommit 提交了敏感文件（E5规则失效） | P0 |
| git_autocommit 导致 git 仓库损坏 | P0 |
| 日志文件过大（>10MB/日） | P2 |

## 回滚步骤

```
1. 删除或重命名 git_autocommit.ps1
   mv 代码文件/tools/git_autocommit.ps1 代码文件/tools/git_autocommit.ps1.disabled

2. 零影响 — 未被任何脚本引用（Phase 1手动调用），
   删除后不影响任何现有流程

3. 如需清除历史自动commit：
   git log --oneline --grep="auto:" | 审查后决定是否 revert
```

## 恢复时间

< 1分钟。删除文件即可完全回退。

> gate: PASS
