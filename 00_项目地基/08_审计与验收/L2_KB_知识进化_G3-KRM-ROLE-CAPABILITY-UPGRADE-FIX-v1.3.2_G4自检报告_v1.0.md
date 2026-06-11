# G4 自检报告：G3-KRM-ROLE-CAPABILITY-UPGRADE-FIX-v1.3.2

> 日期：2026-06-11

| # | 检查项 | 结果 | 详情 |
|:-:|:-------|:----|:------|
| 1 | 脚本已使用 splitlines() | ✅ PASS | 全部替换，无残留 split("\\n") |
| 2 | bad_evidence_lines = 0 | ✅ PASS | 行号全部有效 |
| 3 | all evidence line within range | ✅ PASS | splitlines() 统一口径 |
| 4 | active 规则 = 118 | ✅ PASS | 六角色全部达标 |
| 5 | draft = 0 | ✅ PASS | 无草稿 |
| 6 | source coverage 64/64 | ✅ PASS | 100% |
| 7 | manifest sha256/line 准确 | ✅ PASS | 4 条目均正确 |
| 8 | 未改旧库/角色 .md | ✅ PASS | |
| 9 | 未改生产入口 | ✅ PASS | |

**G4 自检结论：PASS**
