# 索引文件目录

## 用途

此目录存放程序自动生成的索引文件，供角色启动上下文和知识检索系统读取。

## 索引文件列表

| 文件 | 用途 | 生成命令 |
|:-----|:-----|:---------|
| `sources_index.json` | 所有原文登记索引 | `knowledge_guard.py index` |
| `cards_index.json` | 所有文献卡片索引 | `knowledge_guard.py index` |
| `active_index.json` | 生效知识索引（角色启动上下文唯一入口） | `knowledge_guard.py index` |
| `pending_review.json` | 待验证、待确认、待复审内容 | `knowledge_guard.py index` |
| `expired_index.json` | 过期或即将过期内容 | `knowledge_guard.py index` |
| `violations.json` | lint 检查发现的违规项 | `knowledge_guard.py lint` |

## 关键规则

- **角色启动上下文只读 `active_index.json`**
- `active_index.json` 只收录 ACTIVE 且未过期内容
- `active_index.json` 不得加载 raw、cards、candidates、deprecated
- 索引文件由程序自动生成，不手工编辑
