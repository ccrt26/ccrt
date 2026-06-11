# 已废弃知识目录

## 用途

此目录存放已废弃的外部文献知识。

## 废弃规则

1. 只能从 ACTIVE 状态进入 DEPRECATED
2. 废弃必须有明确原因说明
3. 废弃内容不得出现在 active_index.json 中
4. 废弃内容不得加载到角色启动上下文
5. 废弃记录在 `expired_index.json` 中保留

## YAML frontmatter 附加字段

```yaml
---
deprecated_date:
deprecated_reason:
replaced_by:            # 如被替代，填写替代文献 card_id
---
```
