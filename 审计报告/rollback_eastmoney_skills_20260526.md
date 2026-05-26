# 回滚方案 — 东方财富Skills MCP数据源[15]

> 日期：2026-05-26 | 关联部署：deploy_eastmoney_skills_20260526.md

---

## 回滚触发条件

| 级别 | 触发条件 | 响应时间 |
|:---:|:--------|:------:|
| L1 | Skills API连续失败≥3次/天 | 24h内 |
| L2 | API Key泄露 / MCP配置异常 / 返回数据错误 | 1h内 |
| L3 | 数据错误导致分析/交易结论偏差 | 立即 |

## 回滚步骤

### L1 软回滚（保留配置，停用备源）
```
1. 编辑 core.ps1 SourcePriority
2. 从Quote/Financial/FundFlow/Research/Macro/Sector数组中移除"Skills"
3. git commit -m "soft rollback: disable Skills[15] backup"
4. 降级路径自动恢复到接入前状态
```

### L2 硬回滚（删除MCP配置）
```
1. git revert <commit_hash>  # 回滚所有6个文件的变更
2. 确认 core.ps1 和知识库文档恢复到接入前版本
3. 删除 .claude/mcp_servers/eastmoney_skills.json（如revert未自动删除）
```

### L3 紧急回滚
```
git revert <commit_hash> --no-edit
# 无需--no-verify，允许pre-commit hook正常执行
```

## 回滚验证清单

- [ ] core.ps1 SourcePriority 不含"Skills"
- [ ] 玉夜巡检无[15]相关报错
- [ ] 评分引擎输出与接入前Golden Master一致
- [ ] 数据管线正常运行（batch_data_collector无新增错误）
- [ ] Claude Code不再加载eastmoney_skills MCP工具
