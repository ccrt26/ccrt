# 设计记录 — 审计体系重整 (RUN-20260531-232502-c215cb)

> 日期: 2026-06-01 | 流程: NEW_REQUIREMENT | 最终阶段: audit (completed)

## 目标

将审计体系分为事前阻断型和事后发现型两类。事前阻断型不通过不得进入下一步、不得覆盖正式目录、不得上传web。

## 交付清单

| ID | 交付物 | 类型 |
|:---|:------|:-----|
| A1 | 审计点分流表 (23项事前阻断 + 16项事后发现) | 新文档 |
| A2 | pre-commit-check.py Check I (阿黑越权) + Check J (正式报告目录) | 代码变更 |
| A3 | release_gate.py 6闸门聚合 | 新脚本 |
| A4 | 正式报告目录从AUTOCOMMIT移除→PROTECTED_PATHS | 配置变更 |
| A5 | audit_scan.py 新增7e (高Token无run记录) | 代码变更 |
| A6 | 正式报告目录保护规则 | 新文档 |

## 角色签章链

情墨(design) → 腰子(review_1a) → 山猫/信鸽/玉夜/流金/青山(consult) → 旧影+新安(review_1b) → 红结(coding) → 新安(verify) → 红枫(deploy) → 旧影(deploy_verify) → 旧影(audit)
