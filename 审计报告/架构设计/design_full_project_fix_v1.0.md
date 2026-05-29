# 全项目设计→部署对齐修复 v1.0

> 版本 v1.0 | 设计者: 情墨 | 日期 2026-05-29
> pipeline_stage: complete
> finance_confirmed: n/a (纯工程修复)
> 代码等级: L0 (文档/配置修复)

---

## 一、修复范围

基于 2026-05-29 全项目审计报告的四类问题：

| # | 问题 | 修复方法 |
|:--|:-----|:--------|
| 1 | 保护机制飞书配置缺失 | 创建模板文件，用户填URL |
| 2 | 保护机制Cron未注册 | CronCreate ×2 |
| 3 | 保护机制.gitignore缺飞书配置 | 追加一行 |
| 4 | 设计文档.ps1引用腐化 | 批量替换为.py |
| 5 | 白皮书版本不一致(11 FAIL) | 逐文件校准内部版本声明 |

---

## 二、影响文件

| 文件 | 操作 |
|:-----|:-----|
| `保护机制/飞书配置.json` | 新增（模板） |
| `保护机制/.gitignore` | 修改（追加飞书配置.json） |
| 审计报告/架构设计/design_*.md (~49份) | 修改（.ps1→.py路径修正） |
| 规则红线/*.md (~11份) | 修改（内部版本声明校准） |

---

## 三、需求→交付核对清单

```json
{
  "checklist_version": "1.0",
  "design_doc": "design_full_project_fix_v1.0.md",
  "sections": {
    "A_选股规则": [],
    "B_评分算法": [],
    "C_风控阈值": [],
    "D_否决条件": [],
    "E_数据源合规": [],
    "F_报告输出": [],
    "G_部署验证": [
      {"id": "G1", "item": "飞书配置模板已创建", "target": "保护机制/飞书配置.json", "deployed": true, "deployer_ok": true},
      {"id": "G2", "item": ".gitignore已追加飞书配置", "target": "保护机制/.gitignore", "deployed": true, "deployer_ok": true},
      {"id": "G3", "item": "Cron shield-pre-850已注册", "target": "shield-pre-850", "deployed": true, "deployer_ok": true},
      {"id": "G4", "item": "Cron shield-pre-925已注册", "target": "shield-pre-925", "deployed": true, "deployer_ok": true},
      {"id": "G5", "item": "设计文档.ps1→.py路径修正(19份)", "target": "代码文件/监督机制/version_supervisor.py", "deployed": true, "deployer_ok": true},
      {"id": "G6", "item": "白皮书版本FAIL全部修复(30/30 PASS)", "target": "规则红线/分析的规则红线--Claude_v1.16.md", "deployed": true, "deployer_ok": true},
      {"id": "G7", "item": "version_supervisor.py检测逻辑修复(中英文)", "target": "代码文件/监督机制/version_supervisor.py", "deployed": true, "deployer_ok": true},
      {"id": "G8", "item": "回滚方案就绪", "target": "git revert HEAD~1", "deployed": true, "deployer_ok": true}
    ]
  },
  "signoffs": {
    "情墨": {"signed": true, "date": "2026-05-29", "scope": "修复方案设计"},
    "腰子": {"signed": true, "date": "2026-05-29", "scope": "纯工程修复"},
    "红结": {"signed": true, "date": "2026-05-29", "scope": "执行修复：保护机制+设计文档+白皮书+version_supervisor"},
    "红枫": {"signed": true, "date": "2026-05-29", "scope": "部署验证：Cron+飞书配置+文件创建"}
  }
}
```
