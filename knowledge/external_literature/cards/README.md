# 文献卡片目录

## 用途

此目录存放外部文献的文献卡片。
文件命名格式：`CARD-YYYYMMDD-NNN.md`

## 产出规则

- 文献卡片由主责角色（金融团队成员）产出
- 阿黑不得写文献卡片
- 程序不得写文献卡片
- AI 不得替金融团队写文献卡片

## YAML frontmatter（必填）

```yaml
---
doc_type: literature_card
source_id: SRC-YYYYMMDD-NNN
card_id: CARD-YYYYMMDD-NNN
title:
source:
publish_date:
version:
url_or_path:
material_type:           # 参见 POLIY_角色主责路由_v1.0.md 路由表
primary_role:            # 主责角色
support_roles: []        # 支撑角色（非必填）
reading_scope:           # 阅读范围（长文献必填）
status: CARD_DRAFTED     # 初始状态
evidence_level:          # 证据等级：high/medium/low
valid_until:             # 有效期（YYYY-MM-DD）
review_date:             # 复审日期（YYYY-MM-DD）
finance_owner: 腰子      # 固定为腰子
finance_aligned: false   # 腰子统一口径后改为 true
validated: false         # 项目验证后改为 true
confirmed_roles: []      # 确认角色（ACTIVE 前必填）
created_date:            # 创建日期（YYYY-MM-DD）
updated_date:            # 更新日期（YYYY-MM-DD）
---
```

## 正文必含章节

1. **核心结论** — 文献的关键发现或结论
2. **适用范围** — 该文献适用的场景/标的/市场
3. **适用条件** — 使文献结论成立的前提条件
4. **不适用条件** — 文献结论不成立或需要谨慎的情景
5. **对哪些角色有参考价值** — 各角色应关注的要点
6. **可能转化方向**
   - 参数候选
   - 反例候选
   - 核心知识候选
7. **风险提示** — 使用该文献的潜在风险
8. **复审要求** — 何时需要复审、复审关注点
