# 原文登记目录

## 用途

此目录存放外部文献的原文登记文件。
文件命名格式：`SRC-YYYYMMDD-NNN.md`

## 登记规则

1. 每篇外部文献登记为一个文件，状态为 `RAW_RECEIVED`
2. 只登记：标题、来源、发布日期、版本、URL 或 PDF 路径
3. 不做总结、不写卡片、不做金融判断

## YAML frontmatter 要求

```yaml
---
doc_type: source
source_id: SRC-YYYYMMDD-NNN
title:
source:
publish_date:
version:
url_or_path:
status: RAW_RECEIVED
---
```

## 使用限制

- raw 文件不得直接加载到角色启动上下文
- raw 文件不得进入 active_index.json
- raw 文件只作为原文登记存档
