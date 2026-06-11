# 项目验证目录

## 用途

此目录存放文献卡片的项目验证记录。
文件命名格式：`VAL-YYYYMMDD-NNN.md`

## 验证规则

1. 文献进入 REFERENCE_ONLY 后，启动项目验证
2. 验证记录由执行验证的角色产出
3. 验证完成后必须设置 `validated: true`
4. 验证结论决定文献进入哪个候选层

## YAML frontmatter

```yaml
---
doc_type: validation
source_id: SRC-YYYYMMDD-NNN
card_id: CARD-YYYYMMDD-NNN
val_id: VAL-YYYYMMDD-NNN
validated: false
validation_date:
validator_role:
conclusion:               # param_valid / counterexample / core_knowledge
---
```

## 正文建议章节

1. 验证方法
2. 验证数据说明
3. 验证结果
4. 是否符合文献结论
5. 是否发现异常
6. 候选方向建议
