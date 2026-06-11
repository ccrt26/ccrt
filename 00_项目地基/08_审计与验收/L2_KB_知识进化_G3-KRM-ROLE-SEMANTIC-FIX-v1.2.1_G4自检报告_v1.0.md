# G4 自检报告：G3-KRM-ROLE-SEMANTIC-FIX-v1.2.1

> 日期：2026-06-11

## 检查结果

| 序号 | 检查项 | 结果 | 详情 |
|:----:|:-------|:----|:------|
| 1 | KRM README v1.2.1 | ✅ PASS | |
| 2 | README 包含 sources/legacy_role_kb | ✅ PASS | |
| 3 | 角色目录无旧版残留 | ✅ PASS | 残留迁移至 legacy_refs |
| 4 | 每个角色有 07_深度读取触发器 | ✅ PASS | 6/6 存在 |
| 5 | 每个角色 = 9 个必需文件 | ✅ PASS | 玉夜:9, 青山:9, 流金:9, 信鸽:9, 山猫:9, 腰子:9 |
| 6 | manifest 可解析 | ✅ PASS | v1.2.1, 135 entries |
| 7 | manifest sha256 全部 64 位 | ✅ PASS | |
| 8 | manifest path 全部存在 | ✅ PASS | |
| 9 | source_fulltext 区分 role/shared | ✅ PASS | role=64, shared=5 |
| 10 | 六角色旧库全文 64 文件 | ✅ PASS | |
| 11 | 未删除旧库 | ✅ PASS | 6 个旧目录均保留 |
| 12 | 未改生产入口 | ✅ PASS | |
| 13 | 未创建越界 adapter | ✅ PASS | 仅 2 个预期适配器 |

## 结论

G4 自检：PASS
